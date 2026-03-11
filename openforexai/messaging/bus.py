"""Rule-based async event bus.

Architecture
------------
Two delivery modes coexist:

1. **Queue-based (agent-to-agent)**
   Agents register with ``register_agent(agent_id)`` and receive a personal
   ``asyncio.Queue``.  The routing table (JSON rules) determines which agents'
   queues receive each published message.

2. **Handler-based (legacy / infrastructure)**
   Infrastructure components (DataContainer, BrokerBase …) call
   ``subscribe(event_type, handler)`` as before.  When a routing rule targets
   ``"@handlers"`` the message is also delivered to all matching handlers.
   Handler-subscribers are always called regardless of routing rules when their
   ``event_type`` matches — this preserves full backward compatibility.

Routing
-------
On every ``publish()`` call the bus evaluates the routing table:

- If at least one rule matches → deliver to resolved agent queues.
- If a rule has ``"to": "@handlers"`` → also fan-out to handler-subscribers.
- If NO rule matches the event + sender combination → the message is dropped
  and a warning is emitted to the MonitoringBus.

Handler-subscribers bypass routing rules entirely (backward-compat): every
published message is checked against all registered handlers by event type,
just like the old EventBus.  Rules only gate queue-based (agent) delivery.

Hot-reload
----------
``await bus.reload_routing()`` atomically reloads the routing table from disk.
The bus can also subscribe to an ``EventType`` internally (no agent ID needed)
to trigger a reload when the OptimizationAgent or ManagementAPI fires a
``ROUTING_RELOAD_REQUESTED`` event.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from pathlib import Path
from typing import Awaitable, Callable

from openforexai.messaging.routing import RoutingTable
from openforexai.models.messaging import AgentMessage, EventType

_log = logging.getLogger(__name__)

Handler = Callable[[AgentMessage], Awaitable[None]]

# Maximum messages held per agent queue before backpressure kicks in
_AGENT_QUEUE_MAXSIZE = 1_000


class EventBus:
    """Rule-based async pub/sub bus.

    Quick-start::

        routing = RoutingTable()
        routing.load(Path("config/RunTime/event_routing.json5"))
        bus = EventBus(routing)

        # Register an agent (returns its personal queue)
        queue = bus.register_agent("OANDA-EURUSD-AA-TRD1")

        # Legacy handler subscribe (backward compat)
        bus.subscribe(EventType.M5_CANDLE_AVAILABLE, data_container._on_m5_candle)

        # Start dispatch (one long-running task)
        asyncio.create_task(bus.start_dispatch_loop())

        # Publish
        await bus.publish(AgentMessage(event_type=..., source_agent_id=..., payload={}))
    """

    def __init__(
        self,
        routing: RoutingTable | None = None,
        monitoring_bus=None,
    ) -> None:
        # Routing table (may be empty at start; hot-reload supported)
        self._routing: RoutingTable = routing or RoutingTable()
        self._monitoring = monitoring_bus

        # Queue-based agent registry: agent_id → asyncio.Queue
        self._agent_queues: dict[str, asyncio.Queue[AgentMessage]] = {}

        # Handler-based subscriptions (legacy): EventType → list[Handler]
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

        # Internal inbound queue (all published messages land here)
        self._inbound: asyncio.Queue[AgentMessage] = asyncio.Queue()

        self._running = False

    # ── Agent registration ────────────────────────────────────────────────────

    def register_agent(
        self,
        agent_id: str,
        maxsize: int = _AGENT_QUEUE_MAXSIZE,
    ) -> asyncio.Queue[AgentMessage]:
        """Register *agent_id* and return its personal delivery queue.

        If the agent was already registered the existing queue is returned.
        """
        if agent_id not in self._agent_queues:
            self._agent_queues[agent_id] = asyncio.Queue(maxsize=maxsize)
            _log.debug("Agent registered: %s", agent_id)
        return self._agent_queues[agent_id]

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent's delivery queue."""
        if agent_id in self._agent_queues:
            del self._agent_queues[agent_id]
            _log.debug("Agent unregistered: %s", agent_id)

    def registered_agents(self) -> list[str]:
        """Return a list of all currently registered agent IDs."""
        return list(self._agent_queues.keys())

    # ── Legacy handler API (backward compat) ──────────────────────────────────

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """Register a legacy async handler coroutine for *event_type*."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        try:
            self._handlers[event_type].remove(handler)
        except ValueError:
            pass

    # ── Publishing ────────────────────────────────────────────────────────────

    async def publish(self, message: AgentMessage) -> None:
        """Enqueue *message* for routing and delivery."""
        await self._inbound.put(message)

    # ── Dispatch loop ─────────────────────────────────────────────────────────

    async def start_dispatch_loop(self) -> None:
        """Run as a dedicated asyncio Task.

        Reads from the inbound queue, resolves targets via the routing table,
        and delivers messages to agent queues and/or legacy handlers.
        """
        self._running = True
        while self._running:
            try:
                message = await asyncio.wait_for(self._inbound.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            try:
                await self._dispatch(message)
            except Exception as exc:
                _log.exception("Unexpected error dispatching message %s: %s", message.id, exc)
            finally:
                self._inbound.task_done()

    def stop(self) -> None:
        self._running = False

    async def flush(self) -> None:
        """Drain and dispatch all currently-pending inbound messages.

        Intended for use in tests where no dispatch loop is running.
        """
        while not self._inbound.empty():
            try:
                message = self._inbound.get_nowait()
            except asyncio.QueueEmpty:
                break
            await self._dispatch(message)
            self._inbound.task_done()

    async def _dispatch(self, message: AgentMessage) -> None:
        event_val = message.event_type.value if hasattr(message.event_type, "value") else str(message.event_type)
        sender_id = message.source_agent_id

        # ── 0. Emit every bus message to monitoring ────────────────────────────
        self._emit_monitoring(
            "eventbus",
            "EVENT_BUS_MESSAGE",
            event=event_val,
            sender=sender_id,
            target=message.target_agent_id,
            correlation_id=str(message.correlation_id) if message.correlation_id else None,
            payload_keys=list(message.payload.keys()) if message.payload else [],
        )

        # ── 1. Legacy handlers (always evaluated, bypass routing rules) ────────
        handler_list = list(self._handlers.get(message.event_type, []))
        if handler_list:
            results = await asyncio.gather(
                *[h(message) for h in handler_list],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    _log.exception(
                        "Handler error for event %s from %s: %s",
                        event_val, sender_id, r,
                    )

        # ── 2. Direct targeting — bypasses routing table ───────────────────────
        if message.target_agent_id is not None:
            queue = self._agent_queues.get(message.target_agent_id)
            if queue is not None:
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    _log.warning(
                        "Agent queue full for %s — dropping direct event %s from %s",
                        message.target_agent_id, event_val, sender_id,
                    )
            else:
                _log.debug(
                    "Direct target %r not registered — dropping event %s",
                    message.target_agent_id, event_val,
                )
            return  # skip routing table for direct messages

        # ── 3. Routing-table resolution for queue-based delivery ───────────────
        target_ids, _has_handler_rule, matched = self._routing.resolve(
            event_val, sender_id, self._agent_queues  # type: ignore[arg-type]
        )

        if not matched and not handler_list:
            # No rule matched AND no handler registered — warn and discard
            self._warn_unmatched(event_val, sender_id, message)
            return

        for target_id in target_ids:
            queue = self._agent_queues.get(target_id)
            if queue is None:
                continue
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                _log.warning(
                    "Agent queue full for %s — dropping event %s from %s",
                    target_id, event_val, sender_id,
                )
                self._emit_monitoring(
                    "eventbus",
                    "AGENT_QUEUE_FULL",
                    agent_id=target_id,
                    event=event_val,
                    sender=sender_id,
                )

    # ── Hot-reload ────────────────────────────────────────────────────────────

    async def reload_routing(self) -> None:
        """Hot-reload the routing table from disk (thread-safe swap)."""
        try:
            self._routing.reload()
            _log.info(
                "Routing table hot-reloaded: %d rules", len(self._routing.rules)
            )
            self._emit_monitoring("eventbus", "ROUTING_RELOADED",
                                  rule_count=len(self._routing.rules))
        except Exception as exc:
            _log.error("Failed to reload routing table: %s", exc)
            self._emit_monitoring("eventbus", "ROUTING_RELOAD_FAILED", error=str(exc))

    def set_routing(self, routing: RoutingTable) -> None:
        """Replace the active routing table (used by ManagementAPI)."""
        self._routing = routing

    # ── Monitoring helpers ────────────────────────────────────────────────────

    def _warn_unmatched(
        self, event_val: str, sender_id: str, message: AgentMessage
    ) -> None:
        _log.debug(
            "No routing rule matched event=%r sender=%r — message discarded",
            event_val, sender_id,
        )
        self._emit_monitoring(
            "eventbus",
            "UNMATCHED_EVENT",
            event=event_val,
            sender=sender_id,
            message_id=str(message.id),
        )

    def _emit_monitoring(self, source: str, event_type_str: str, **kwargs) -> None:
        if self._monitoring is None:
            return
        try:
            from datetime import datetime, timezone
            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType

            # Map string to enum if possible, else use a generic type
            try:
                mtype = MonitoringEventType[event_type_str]
            except KeyError:
                # Use a safe fallback — many internal events don't have a
                # dedicated MonitoringEventType value
                return

            self._monitoring.emit(MonitoringEvent(
                timestamp=datetime.now(timezone.utc),
                source_module=source,
                event_type=mtype,
                payload=kwargs,
            ))
        except Exception:
            pass  # monitoring must never break the bus



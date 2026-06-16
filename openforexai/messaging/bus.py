"""Rule-based async event bus — single communication channel.

Architecture
------------
All inter-module communication goes through this bus. Every module registers
as a named member and receives its messages via a personal asyncio.Queue.

Delivery modes
--------------
1. **Response-future matching** (highest priority)
   When a message carries a ``correlation_id`` that matches a registered
   pending future, the future is resolved immediately and the message is NOT
   routed further. This is the mechanism for request-response patterns used
   by tools and the management API.

2. **Direct targeting**
   When ``target_agent_id`` is set, the message is delivered directly to that
   member's queue, bypassing the routing table.

3. **Routing-table resolution**
   All other messages are resolved via the routing table (JSON rules).

Routing
-------
- If at least one rule matches → deliver to resolved member queues.
- If NO rule matches → message is dropped with a warning to the MonitoringBus.
- ``@handlers`` is NOT a valid routing target — removed from this bus.

Routing-reload
--------------
When a ``ROUTING_RELOAD_REQUESTED`` event is dispatched, the bus reloads
its routing table from disk internally (no handler subscription needed).

Hot-reload is also available via ``await bus.reload_routing()`` or
``bus.set_routing(new_table)``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC

from openforexai.messaging.routing import RoutingTable
from openforexai.models.messaging import AgentMessage, EventType

_log = logging.getLogger(__name__)

# Maximum messages held per member queue before backpressure kicks in
_MEMBER_QUEUE_MAXSIZE = 1_000


class EventBus:
    """Rule-based async pub/sub bus.

    All inter-module communication must go through this bus.
    No ``subscribe()`` / handler-based delivery exists — every module must
    register as a named member via ``register_member()``.

    Quick-start::

        routing = RoutingTable()
        routing.load(Path("config/RunTime/event_routing.json5"))
        bus = EventBus(routing)

        # Register a module as a named bus member
        queue = bus.register_member("OANDA-EURUSD-AA-TRD1")

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
        self._routing: RoutingTable = routing or RoutingTable()
        self._monitoring = monitoring_bus

        # Member registry: member_id → asyncio.Queue
        self._agent_queues: dict[str, asyncio.Queue[AgentMessage]] = {}

        # Pending response futures: correlation_id → asyncio.Future
        # When a response message arrives with a matching correlation_id,
        # the future is resolved and the message is NOT routed further.
        self._pending_futures: dict[str, asyncio.Future] = {}

        # Internal inbound queue (all published messages land here)
        self._inbound: asyncio.Queue[AgentMessage] = asyncio.Queue()

        self._running = False

    # ── Member registration ───────────────────────────────────────────────────

    def register_member(
        self,
        member_id: str,
        maxsize: int = _MEMBER_QUEUE_MAXSIZE,
    ) -> asyncio.Queue[AgentMessage]:
        """Register a bus member and return its personal delivery queue.

        Any module (agent, service, adapter, EC) calls this once at startup.
        If already registered the existing queue is returned.
        """
        if member_id not in self._agent_queues:
            self._agent_queues[member_id] = asyncio.Queue(maxsize=maxsize)
            _log.debug("Member registered: %s", member_id)
        return self._agent_queues[member_id]

    # Keep legacy name as alias for backward compat during migration
    def register_agent(
        self,
        agent_id: str,
        maxsize: int = _MEMBER_QUEUE_MAXSIZE,
    ) -> asyncio.Queue[AgentMessage]:
        """Alias for ``register_member()`` — kept during migration."""
        return self.register_member(agent_id, maxsize)

    def unregister_member(self, member_id: str) -> None:
        """Remove a member's delivery queue."""
        if member_id in self._agent_queues:
            del self._agent_queues[member_id]
            _log.debug("Member unregistered: %s", member_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Alias for ``unregister_member()`` — kept during migration."""
        self.unregister_member(agent_id)

    def registered_agents(self) -> list[str]:
        """Return a list of all currently registered member IDs."""
        return list(self._agent_queues.keys())

    # ── Pending response futures ──────────────────────────────────────────────

    def register_response_future(
        self, correlation_id: str, future: asyncio.Future
    ) -> None:
        """Register a Future to be resolved when a message with *correlation_id* arrives.

        The message is consumed by the future and NOT delivered via routing.
        Call ``cancel_response_future()`` in a ``finally`` block to clean up
        if the caller times out before the response arrives.
        """
        self._pending_futures[correlation_id] = future

    def cancel_response_future(self, correlation_id: str) -> None:
        """Remove a pending future (call in finally after wait_for)."""
        self._pending_futures.pop(correlation_id, None)

    # ── Publishing ────────────────────────────────────────────────────────────

    async def publish(self, message: AgentMessage) -> None:
        """Enqueue *message* for routing and delivery."""
        await self._inbound.put(message)

    # ── Dispatch loop ─────────────────────────────────────────────────────────

    async def start_dispatch_loop(self) -> None:
        """Run as a dedicated asyncio Task.

        Reads from the inbound queue, resolves targets via the routing table,
        and delivers messages to member queues.
        """
        self._running = True
        while self._running:
            try:
                message = await asyncio.wait_for(self._inbound.get(), timeout=1.0)
            except TimeoutError:
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

        # ── 0. Routing-reload shortcut ────────────────────────────────────────
        if message.event_type == EventType.ROUTING_RELOAD_REQUESTED:
            await self.reload_routing()
            return

        is_debug = getattr(self._monitoring, "is_debug", False)
        include_payload = is_debug or event_val in {"llm_request", "llm_response"}

        # ── 1. Pending-future resolution (request-response pattern) ───────────
        cid = message.correlation_id
        if cid and cid in self._pending_futures:
            future = self._pending_futures.pop(cid)
            if not future.done():
                future.set_result(message.payload)
            self._emit_monitoring(
                "eventbus",
                event_val,
                event=event_val,
                message_id=str(message.id),
                sender=sender_id,
                target=message.target_agent_id or "(future)",
                correlation_id=cid,
                **({"payload": message.payload} if include_payload else {}),
            )
            return

        # ── 2. Direct targeting — bypasses routing table ───────────────────────
        if message.target_agent_id is not None:
            queue = self._agent_queues.get(message.target_agent_id)
            if queue is not None:
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    _log.warning(
                        "Member queue full for %s — dropping direct event %s from %s",
                        message.target_agent_id, event_val, sender_id,
                    )
            else:
                _log.debug(
                    "Direct target %r not registered — dropping event %s",
                    message.target_agent_id, event_val,
                )
            self._emit_monitoring(
                "eventbus",
                event_val,
                event=event_val,
                message_id=str(message.id),
                sender=sender_id,
                target=message.target_agent_id,
                correlation_id=cid,
                **({"payload": message.payload} if include_payload else {}),
            )
            return

        # ── 3. Routing-table resolution ────────────────────────────────────────
        target_ids, matched = self._routing.resolve(
            event_val, sender_id, self._agent_queues  # type: ignore[arg-type]
        )

        if not matched:
            self._warn_unmatched(event_val, sender_id, message)
            return

        self._emit_monitoring(
            "eventbus",
            event_val,
            event=event_val,
            message_id=str(message.id),
            sender=sender_id,
            target=target_ids[0] if len(target_ids) == 1 else (target_ids if target_ids else None),
            correlation_id=cid,
            **({"payload": message.payload} if include_payload else {}),
        )

        for target_id in target_ids:
            queue = self._agent_queues.get(target_id)
            if queue is None:
                continue
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                _log.warning(
                    "Member queue full for %s — dropping event %s from %s",
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
            from datetime import datetime
            from openforexai.models.monitoring import MonitoringEvent

            self._monitoring.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=source,
                event_type=event_type_str.lower(),
                payload=kwargs,
            ))
        except Exception:
            pass  # monitoring must never break the bus

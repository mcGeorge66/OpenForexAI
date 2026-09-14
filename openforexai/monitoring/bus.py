from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any

from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.ports.monitoring import AbstractMonitoringBus

# Event types that are automatically pinned to the protected buffer on arrival.
_AUTO_PIN_TYPES: frozenset[str] = frozenset({
    MonitoringEventType.SYSTEM_ERROR,
    MonitoringEventType.LLM_ERROR,
    MonitoringEventType.LLM_TURN_FAILED,
    MonitoringEventType.EC_RUN_FAILED,
    MonitoringEventType.TOOL_CALL_FAILED,
    MonitoringEventType.BROKER_ERROR,
    MonitoringEventType.BROKER_DISCONNECTED,
})

_log = logging.getLogger(__name__)

_INFO_MAX_STR_LEN = 2_000
_INFO_MAX_LIST_ITEMS = 20
_INFO_SUPPRESSED_EVENT_TYPES = {
    MonitoringEventType.ACCOUNT_STATUS_UPDATED,
    MonitoringEventType.BROKER_HTTP_REQUEST,
    MonitoringEventType.BROKER_HTTP_RESPONSE,
    MonitoringEventType.DATA_CONTAINER_ACCESS,
    MonitoringEventType.M5_CANDLE_FETCHED,
    MonitoringEventType.M5_CANDLE_QUEUED,
    MonitoringEventType.SYNC_CHECK_STARTED,
    MonitoringEventType.SYNC_CHECK_COMPLETED,
    MonitoringEventType.M5_CANDLE_SAVED,
}


def _normalize_detail_level(level: str | None) -> str:
    normalized = str(level or "INFO").strip().upper()
    return "DEBUG" if normalized == "DEBUG" else "INFO"


class MonitoringBus(AbstractMonitoringBus):
    """In-process monitoring event bus with HTTP-accessible ring buffer.

    Any component can call ``emit()`` synchronously.  The event is put into
    every subscriber queue without blocking.  If a queue is full the event is
    dropped for that subscriber (the system is never back-pressured).

    Additionally, the last ``RING_BUFFER_SIZE`` events are kept in a ring
    buffer accessible via ``recent_events(since=...)``.  This powers the
    ``GET /monitoring/events`` HTTP endpoint for the console monitor.

    Typical usage::

        bus = MonitoringBus()
        queue = bus.subscribe()           # returns an asyncio.Queue
        ...
        bus.emit(MonitoringEvent(...))    # fire-and-forget

        # In monitoring consumer:
        event = await queue.get()

        # HTTP polling (for console monitor):
        events = bus.recent_events(since=last_timestamp)

    The queue is bounded (default 10 000 events).  Old events are dropped
    when a slow consumer falls behind.
    """

    DEFAULT_QUEUE_SIZE = 1_000
    RING_BUFFER_SIZE   = 1_000

    def __init__(self, detail_level: str = "INFO") -> None:
        self._subscribers: list[asyncio.Queue[MonitoringEvent]] = []
        self._ring: deque[MonitoringEvent] = deque(maxlen=self.RING_BUFFER_SIZE)
        self._detail_level = _normalize_detail_level(detail_level)
        # Protected buffer: survives ring-buffer eviction until manually unpinned.
        self._protected: dict[str, MonitoringEvent] = {}  # event_id → event (insertion order)
        self._auto_pinned_ids: set[str] = set()           # subset of _protected that was auto-pinned
        # Last time each agent completed a cycle (keyed by agent_id string).
        self._agent_last_active: dict[str, datetime] = {}
        # Bus events delivered to an agent since it last started working:
        # agent_id → event_type → (count, timestamp of the newest one).
        # Cleared whenever the agent reacts, so a non-empty entry means
        # "this arrived and nothing happened yet" — the basis for staleness
        # detection that follows the agent's real triggers instead of a clock.
        self._agent_pending_triggers: dict[str, dict[str, tuple[int, datetime]]] = {}

    # ── Subscription management ───────────────────────────────────────────────

    def subscribe(self, maxsize: int = DEFAULT_QUEUE_SIZE) -> asyncio.Queue[MonitoringEvent]:
        """Register a new consumer and return its dedicated queue.

        Call ``unsubscribe(queue)`` when the consumer disconnects.
        """
        q: asyncio.Queue[MonitoringEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[MonitoringEvent]) -> None:
        """Remove *q* from the subscriber list."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    # ── Emission ──────────────────────────────────────────────────────────────

    def emit(self, event: MonitoringEvent) -> None:
        """Publish *event* to all subscribers and ring buffer.  Never raises, never blocks."""
        prepared = self._prepare_event(event)
        if prepared is None:
            return
        self._ring.append(prepared)
        # Auto-pin error events so they survive ring-buffer eviction.
        event_id = str(prepared.id)
        if str(prepared.event_type) in _AUTO_PIN_TYPES:
            self._protected[event_id] = prepared
            self._auto_pinned_ids.add(event_id)
        # Track agent activity for staleness detection.
        if str(prepared.event_type) == MonitoringEventType.AGENT_INPUT_BUILT:
            agent_id = prepared.payload.get("agent_id")
            if agent_id:
                self._agent_last_active[str(agent_id)] = prepared.timestamp
                # The agent reacted — anything delivered before this point is handled.
                self._agent_pending_triggers.pop(str(agent_id), None)
        elif str(prepared.event_type) == MonitoringEventType.AGENT_TRIGGER_SKIPPED:
            # A logged skip (divider not reached, llm busy, outside session,
            # paused) proves the agent saw the trigger and decided — that is
            # healthy, not a stall. Only triggers it never processed at all
            # should remain pending.
            agent_id = prepared.payload.get("agent_id")
            if agent_id:
                self._agent_pending_triggers.pop(str(agent_id), None)
        elif prepared.source_module == "eventbus":
            self._record_delivery(prepared)
        for q in list(self._subscribers):
            try:
                q.put_nowait(prepared)
            except asyncio.QueueFull:
                pass
            except Exception:
                pass  # never let monitoring break the main system

    def _record_delivery(self, prepared: MonitoringEvent) -> None:
        """Note that a bus event was delivered to one or more agents.

        The bus reports a single target as a string and a fan-out as a list;
        both are handled. Only the event type and a count are kept — enough to
        answer "did trigger X arrive and go unanswered?" without holding any
        payload.
        """
        payload = prepared.payload or {}
        event_type = payload.get("event")
        target = payload.get("target")
        if not event_type or not target:
            return
        targets = target if isinstance(target, list) else [target]
        for raw in targets:
            agent_id = str(raw or "").strip()
            if not agent_id or agent_id.startswith("("):  # "(future)" placeholder
                continue
            per_agent = self._agent_pending_triggers.setdefault(agent_id, {})
            count, _ = per_agent.get(str(event_type), (0, prepared.timestamp))
            per_agent[str(event_type)] = (count + 1, prepared.timestamp)

    def agent_pending_triggers(self, agent_id: str) -> dict[str, tuple[int, datetime]]:
        """Bus events delivered to *agent_id* since it last started a cycle."""
        return dict(self._agent_pending_triggers.get(agent_id, {}))

    def set_detail_level(self, level: str) -> None:
        self._detail_level = _normalize_detail_level(level)

    @property
    def detail_level(self) -> str:
        return self._detail_level

    @property
    def is_debug(self) -> bool:
        return self._detail_level == "DEBUG"

    # ── Ring buffer access (for HTTP polling) ─────────────────────────────────

    def recent_events(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[MonitoringEvent]:
        """Return recent events from the ring buffer, optionally filtered.

        ``since`` — return only events with timestamp > since (UTC).
        ``limit`` — cap the result to the *last* N matching events.
        """
        events = list(self._ring)
        if since is not None:
            events = [e for e in events if e.timestamp > since]
        return events[-limit:]

    # ── Protected buffer ──────────────────────────────────────────────────────

    def pin_event(self, event_id: str) -> bool:
        """Manually pin an event by ID.  Returns True if found (ring or already pinned)."""
        if event_id in self._protected:
            return True
        for evt in self._ring:
            if str(evt.id) == event_id:
                self._protected[event_id] = evt
                return True
        return False

    def unpin_event(self, event_id: str) -> bool:
        """Remove pin protection from an event.  Returns True if it was pinned."""
        existed = event_id in self._protected
        self._protected.pop(event_id, None)
        self._auto_pinned_ids.discard(event_id)
        return existed

    def pinned_events(self) -> list[dict[str, Any]]:
        """Return pinned events as dicts with extra `auto_pinned` flag, oldest first."""
        return [
            {**evt.model_dump(mode="json"), "auto_pinned": eid in self._auto_pinned_ids}
            for eid, evt in self._protected.items()
        ]

    # ── Agent activity tracking ───────────────────────────────────────────────

    def agent_last_active(self, agent_id: str) -> datetime | None:
        """Return the UTC timestamp of the last completed agent cycle, or None."""
        return self._agent_last_active.get(agent_id)

    # ── Convenience factory ───────────────────────────────────────────────────

    def build_event(
        self,
        source_module: str,
        event_type: MonitoringEventType,
        broker_name: str | None = None,
        pair: str | None = None,
        **payload_kwargs,
    ) -> MonitoringEvent:
        """Build a MonitoringEvent with current UTC timestamp."""
        return MonitoringEvent(
            timestamp=datetime.now(UTC),
            source_module=source_module,
            event_type=event_type,
            broker_name=broker_name,
            pair=pair,
            payload=payload_kwargs,
        )

    def _prepare_event(self, event: MonitoringEvent) -> MonitoringEvent | None:
        if self.is_debug:
            return event
        if event.event_type in _INFO_SUPPRESSED_EVENT_TYPES:
            return None
        trimmed_payload = self._trim_value(event.payload)
        if trimmed_payload == event.payload:
            return event
        return event.model_copy(update={"payload": trimmed_payload})

    def _trim_value(self, value: Any) -> Any:
        if isinstance(value, str):
            if len(value) <= _INFO_MAX_STR_LEN:
                return value
            omitted = len(value) - _INFO_MAX_STR_LEN
            return value[:_INFO_MAX_STR_LEN] + f" …[{omitted} chars omitted]"
        if isinstance(value, list):
            items = [self._trim_value(item) for item in value[:_INFO_MAX_LIST_ITEMS]]
            if len(value) > _INFO_MAX_LIST_ITEMS:
                omitted = len(value) - _INFO_MAX_LIST_ITEMS
                items.append(f"…[{omitted} items omitted]")
            return items
        if isinstance(value, dict):
            return {key: self._trim_value(item) for key, item in value.items()}
        return value


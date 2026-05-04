from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any

from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.ports.monitoring import AbstractMonitoringBus

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
    MonitoringEventType.TIMEFRAME_CALCULATED,
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

    DEFAULT_QUEUE_SIZE = 10_000
    RING_BUFFER_SIZE   = 1_000

    def __init__(self, detail_level: str = "INFO") -> None:
        self._subscribers: list[asyncio.Queue[MonitoringEvent]] = []
        self._ring: deque[MonitoringEvent] = deque(maxlen=self.RING_BUFFER_SIZE)
        self._detail_level = _normalize_detail_level(detail_level)

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
        for q in list(self._subscribers):
            try:
                q.put_nowait(prepared)
            except asyncio.QueueFull:
                pass
            except Exception:
                pass  # never let monitoring break the main system

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


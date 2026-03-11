from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import List

from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.ports.monitoring import AbstractMonitoringBus

_log = logging.getLogger(__name__)


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

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[MonitoringEvent]] = []
        self._ring: deque[MonitoringEvent] = deque(maxlen=self.RING_BUFFER_SIZE)

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
        self._ring.append(event)
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
            except Exception:
                pass  # never let monitoring break the main system

    # ── Ring buffer access (for HTTP polling) ─────────────────────────────────

    def recent_events(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> List[MonitoringEvent]:
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
            timestamp=datetime.now(timezone.utc),
            source_module=source_module,
            event_type=event_type,
            broker_name=broker_name,
            pair=pair,
            payload=payload_kwargs,
        )


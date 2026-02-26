from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.ports.monitoring import AbstractMonitoringBus

_log = logging.getLogger(__name__)


class MonitoringBus(AbstractMonitoringBus):
    """In-process monitoring event bus.

    Any component can call ``emit()`` synchronously.  The event is put into
    every subscriber queue without blocking.  If a queue is full the event is
    dropped for that subscriber (the system is never back-pressured).

    Typical usage::

        bus = MonitoringBus()
        queue = bus.subscribe()           # returns an asyncio.Queue
        ...
        bus.emit(MonitoringEvent(...))    # fire-and-forget

        # In monitoring consumer:
        event = await queue.get()

    The queue is bounded (default 10 000 events).  Old events are dropped
    when a slow consumer falls behind.
    """

    DEFAULT_QUEUE_SIZE = 10_000

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[MonitoringEvent]] = []

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
        """Publish *event* to all subscribers.  Never raises, never blocks."""
        if not self._subscribers:
            return
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Subscriber too slow — drop the event rather than blocking
                pass
            except Exception:
                pass  # never let monitoring break the main system

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

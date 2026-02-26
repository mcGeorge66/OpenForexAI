from __future__ import annotations

from abc import ABC, abstractmethod

from openforexai.models.monitoring import MonitoringEvent


class AbstractMonitoringBus(ABC):
    """Port: fire-and-forget observability sink.

    All system components call ``emit()`` to report what they are doing.
    If no monitor is connected the events are silently discarded.
    The system **must never block** on monitoring — implementations must
    guarantee that ``emit()`` returns immediately regardless of subscriber state.
    """

    @abstractmethod
    def emit(self, event: MonitoringEvent) -> None:
        """Publish *event* to all connected monitors.

        Must never raise.  Must never block.  If a subscriber queue is full
        the oldest or newest event is dropped silently.
        """
        ...

from __future__ import annotations

from datetime import UTC, datetime

from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.monitoring.bus import MonitoringBus


def test_info_monitoring_keeps_m5_candle_queued_events_visible():
    bus = MonitoringBus(detail_level="INFO")

    bus.emit(MonitoringEvent(
        timestamp=datetime.now(UTC),
        source_module="broker.TEST1",
        event_type=MonitoringEventType.M5_CANDLE_QUEUED,
        broker_name="TEST1",
        pair="EURUSD",
        payload={"timestamp": "2026-05-05T12:00:00+00:00"},
    ))

    events = bus.recent_events(limit=10)
    assert len(events) == 1
    assert events[0].event_type == MonitoringEventType.M5_CANDLE_QUEUED

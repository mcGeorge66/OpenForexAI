from __future__ import annotations

from datetime import UTC, datetime

from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.monitoring.bus import MonitoringBus


def test_info_monitoring_suppresses_m5_candle_queued_events():
    bus = MonitoringBus(detail_level="INFO")

    bus.emit(MonitoringEvent(
        timestamp=datetime.now(UTC),
        source_module="broker.TEST1",
        event_type=MonitoringEventType.M5_CANDLE_QUEUED,
        broker_name="TEST1",
        pair="EURUSD",
        payload={"timestamp": "2026-05-05T12:00:00+00:00"},
    ))

    assert bus.recent_events(limit=10) == []


def test_debug_monitoring_keeps_m5_candle_queued_events_visible():
    bus = MonitoringBus(detail_level="DEBUG")

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


def _delivery(agent_id: str, event: str = "m5_candle_trigger") -> MonitoringEvent:
    return MonitoringEvent(
        timestamp=datetime.now(UTC),
        source_module="eventbus",
        event_type=event,  # the bus reports the event type as a plain string
        payload={"event": event, "target": agent_id},
    )


def _skip(agent_id: str, reason: str = "session_filter") -> MonitoringEvent:
    return MonitoringEvent(
        timestamp=datetime.now(UTC),
        source_module=f"agent:{agent_id}",
        event_type=MonitoringEventType.AGENT_TRIGGER_SKIPPED,
        payload={"agent_id": agent_id, "trigger": "m5_candle_trigger", "reason": reason},
    )


def test_a_logged_skip_clears_the_pending_trigger_at_info_level():
    """The 2026-09-14 false alarm: at INFO the skip was filtered out before the
    bookkeeping ran, so an agent outside its session looked stalled."""
    bus = MonitoringBus(detail_level="INFO")
    agent = "OXS_T-USDJPY-AA-PTJ"

    bus.emit(_delivery(agent))
    assert bus.agent_pending_triggers(agent) != {}

    bus.emit(_skip(agent))

    assert bus.agent_pending_triggers(agent) == {}


def test_skips_stay_out_of_the_event_log_at_info_level():
    """Counted, but not shown — one entry per skipped candle would drown it."""
    bus = MonitoringBus(detail_level="INFO")
    bus.emit(_skip("OXS_T-USDJPY-AA-PTJ"))

    assert bus.recent_events(limit=10) == []


def test_skips_are_visible_in_the_event_log_at_debug_level():
    bus = MonitoringBus(detail_level="DEBUG")
    bus.emit(_skip("OXS_T-USDJPY-AA-PTJ"))

    events = bus.recent_events(limit=10)
    assert [e.event_type for e in events] == [MonitoringEventType.AGENT_TRIGGER_SKIPPED]

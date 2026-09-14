"""Auto-pinned monitoring errors must reach the bus, or nobody learns of them.

The MonitoringBus already decides what matters enough to survive eviction.
That same set was invisible outside the dashboard: in-memory only, gone on
restart, and unable to drive a notification rule.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from openforexai.models.messaging import EventType
from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.monitoring.alert_bridge import (
    alert_bridge_loop, alert_payload, should_bridge,
)
from openforexai.monitoring.bus import MonitoringBus


def _event(event_type, payload=None, **kw):
    return MonitoringEvent(
        timestamp=datetime.now(UTC),
        source_module=kw.pop("source_module", "ec:OXS_T-EURUSD-EC-TRSLF"),
        event_type=event_type,
        payload=payload or {},
        **kw,
    )


# ── Selection ────────────────────────────────────────────────────────────────

def test_every_auto_pinned_kind_is_bridged():
    """Bound to _AUTO_PIN_TYPES on purpose: a kind added there later is
    covered without touching this module."""
    from openforexai.monitoring.bus import _AUTO_PIN_TYPES
    bridged = [t for t in _AUTO_PIN_TYPES if should_bridge(_event(t))]
    assert len(bridged) == len(_AUTO_PIN_TYPES) - 1  # system_error is excluded


def test_a_broker_coming_back_is_reported_too():
    """The only non-error worth interrupting someone for — otherwise you learn
    that the broker went away and never that it returned."""
    assert should_bridge(_event(MonitoringEventType.BROKER_CONNECTED)) is True


def test_the_pinboard_stays_errors_only():
    """BROKER_CONNECTED is alerted on but must not be pinned: _AUTO_PIN_TYPES
    means 'protect from eviction', and a successful connect is not a fault."""
    from openforexai.monitoring.bus import _AUTO_PIN_TYPES
    assert MonitoringEventType.BROKER_CONNECTED not in _AUTO_PIN_TYPES


def test_system_error_is_not_bridged_twice():
    """Whoever raises it already publishes a richer bus event; bridging the
    monitoring copy as well would notify twice for one failure."""
    assert should_bridge(_event(MonitoringEventType.SYSTEM_ERROR)) is False


def test_routine_events_are_left_alone():
    assert should_bridge(_event(MonitoringEventType.M5_CANDLE_SAVED)) is False


# ── Payload ──────────────────────────────────────────────────────────────────

def test_the_kind_and_the_source_travel_with_it():
    p = alert_payload(_event(MonitoringEventType.EC_RUN_FAILED,
                             {"ec_id": "OXS_T-EURUSD-EC-TRSLF", "error": "Script syntax error"}))
    assert p["alert_type"] == "ec_run_failed"
    assert p["source"] == "ec:OXS_T-EURUSD-EC-TRSLF"
    assert p["message"] == "Script syntax error"
    assert p["ec_id"] == "OXS_T-EURUSD-EC-TRSLF"


def test_message_is_found_whatever_the_source_calls_it():
    """Each source names its failure differently; a rule should not have to."""
    assert alert_payload(_event(MonitoringEventType.BROKER_ERROR, {"error": "timeout"}))["message"] == "timeout"
    assert alert_payload(_event(MonitoringEventType.TOOL_CALL_FAILED, {"reason": "denied"}))["message"] == "denied"


def test_no_recognisable_text_leaves_an_empty_message_not_a_crash():
    assert alert_payload(_event(MonitoringEventType.BROKER_ERROR, {"code": 7}))["message"] == ""


def test_original_fields_survive_as_placeholders():
    p = alert_payload(_event(MonitoringEventType.LLM_ERROR,
                             {"agent_id": "A", "turn": 3, "error": "boom"}))
    assert p["agent_id"] == "A" and p["turn"] == 3


def test_alert_type_cannot_be_shadowed_by_the_original_payload():
    """Merging the source payload must not let it rewrite what kind it is."""
    p = alert_payload(_event(MonitoringEventType.BROKER_ERROR, {"alert_type": "gefaelscht"}))
    assert p["alert_type"] == "broker_error"


# ── End to end ───────────────────────────────────────────────────────────────

class _Bus:
    def __init__(self):
        self.published = []

    async def publish(self, msg, **kw):
        self.published.append(msg)


@pytest.mark.asyncio
async def test_an_auto_pinned_error_arrives_on_the_bus():
    mon, bus = MonitoringBus(detail_level="INFO"), _Bus()
    task = asyncio.create_task(alert_bridge_loop(mon, bus))
    await asyncio.sleep(0)
    mon.emit(_event(MonitoringEventType.EC_RUN_FAILED, {"ec_id": "X", "error": "kaputt"}))
    mon.emit(_event(MonitoringEventType.M5_CANDLE_SAVED, {"pair": "EURUSD"}))
    for _ in range(50):
        await asyncio.sleep(0)
        if bus.published:
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(bus.published) == 1, "routine events must not be forwarded"
    msg = bus.published[0]
    assert msg.event_type == EventType.SYSTEM_ALERT
    assert msg.payload["alert_type"] == "ec_run_failed"
    assert msg.payload["message"] == "kaputt"

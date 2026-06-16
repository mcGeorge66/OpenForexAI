from __future__ import annotations

from datetime import UTC, datetime, timedelta

from openforexai.agents.agent import Agent
from openforexai.models.messaging import EventType
from openforexai.models.monitoring import MonitoringEventType
from openforexai.monitoring.bus import MonitoringBus


def test_resolve_cycle_pair_prefers_configured_pair() -> None:
    agent = Agent.__new__(Agent)
    agent._config = {"pair": "GBPUSD"}

    resolved = agent._resolve_cycle_pair(
        EventType.ANALYSIS_RESULT.value,
        {
            "response": '{"symbol":"EURUSD"}',
            "trigger_payload": {"pair": "USDJPY"},
        },
    )

    assert resolved == "GBPUSD"


def test_resolve_cycle_pair_uses_analysis_response_symbol_for_broker_agent() -> None:
    agent = Agent.__new__(Agent)
    agent._config = {}

    resolved = agent._resolve_cycle_pair(
        EventType.ANALYSIS_RESULT.value,
        {
            "response": '{"symbol":"EURUSD","decision":"BIAS_SHORT"}',
        },
    )

    assert resolved == "EURUSD"


def test_resolve_cycle_pair_falls_back_to_trigger_payload_pair() -> None:
    agent = Agent.__new__(Agent)
    agent._config = {"pair": "ALL___"}

    resolved = agent._resolve_cycle_pair(
        EventType.ANALYSIS_RESULT.value,
        {
            "response": '{"decision":"BIAS_SHORT"}',
            "trigger_payload": {"pair": "EURUSD"},
        },
    )

    assert resolved == "EURUSD"


def test_resolve_analysis_timestamp_uses_m5_candle_trigger_payload() -> None:
    agent = Agent.__new__(Agent)

    resolved = agent._resolve_analysis_timestamp(
        EventType.M5_CANDLE_TRIGGER.value,
        {
            "candle": {"timestamp": "2026-05-06T06:30:00Z"},
        },
    )

    assert resolved == "2026-05-06T06:30:00Z"


def test_parse_json_object_rejects_empty_text() -> None:
    agent = Agent.__new__(Agent)

    assert agent._parse_json_object("") is None
    assert agent._parse_json_object("   ") is None


def test_parse_json_object_accepts_valid_analysis_payload() -> None:
    agent = Agent.__new__(Agent)

    parsed = agent._parse_json_object('{"symbol":"EURUSD","decision":"NEUTRAL"}')

    assert parsed == {"symbol": "EURUSD", "decision": "NEUTRAL"}


def test_should_run_for_trigger_cycles_counter_by_divider() -> None:
    class _Logger:
        def debug(self, *args, **kwargs) -> None:
            return None

    agent = Agent.__new__(Agent)
    agent._logger = _Logger()
    agent._any_candle_divider = 3
    agent._m5_candle_event_count = 0

    run_1, count_1 = agent._should_run_for_trigger(EventType.M5_CANDLE_TRIGGER.value)
    run_2, count_2 = agent._should_run_for_trigger(EventType.M5_CANDLE_TRIGGER.value)
    run_3, count_3 = agent._should_run_for_trigger(EventType.M5_CANDLE_TRIGGER.value)
    run_4, count_4 = agent._should_run_for_trigger(EventType.M5_CANDLE_TRIGGER.value)

    assert (run_1, count_1) == (False, 1)
    assert (run_2, count_2) == (False, 2)
    assert (run_3, count_3) == (True, 3)
    assert (run_4, count_4) == (False, 1)


def test_measure_trigger_age_ms_for_m5_candle_trigger() -> None:
    agent = Agent.__new__(Agent)
    ts = (datetime.now(UTC) - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")

    age_ms = agent._measure_trigger_age_ms(
        EventType.M5_CANDLE_TRIGGER.value,
        {"candle": {"timestamp": ts}},
    )

    assert age_ms is not None
    assert 9000 <= age_ms <= 11000


def test_emit_agent_backlog_detected_only_when_debug_enabled() -> None:
    class _Context:
        broker_name = "OXS_T"
        pair = "EURUSD"

    class _Dispatcher:
        _context = _Context()

    agent = Agent.__new__(Agent)
    agent.agent_id = "OXS_T-EURUSD-AA-ANLYS"
    agent._tool_dispatcher = _Dispatcher()

    info_bus = MonitoringBus(detail_level="INFO")
    agent._monitoring_bus = info_bus
    agent._emit_agent_backlog_detected(
        event_val=EventType.M5_CANDLE_TRIGGER.value,
        source="OXS_T-EURUSD-AD-ADPT",
        backlog_remaining=2,
        trigger_age_ms=1234.5,
    )
    assert info_bus.recent_events(limit=10) == []

    debug_bus = MonitoringBus(detail_level="DEBUG")
    agent._monitoring_bus = debug_bus
    agent._emit_agent_backlog_detected(
        event_val=EventType.M5_CANDLE_TRIGGER.value,
        source="OXS_T-EURUSD-AD-ADPT",
        backlog_remaining=2,
        trigger_age_ms=1234.5,
    )
    events = debug_bus.recent_events(limit=10)
    assert len(events) == 1
    assert events[0].event_type == MonitoringEventType.AGENT_BACKLOG_DETECTED
    assert events[0].payload["backlog_remaining"] == 2

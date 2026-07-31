from __future__ import annotations

from openforexai.agents.agent import Agent
from openforexai.models.monitoring import MonitoringEventType
from openforexai.monitoring.bus import MonitoringBus


def test_agent_emits_llm_debug_monitoring_events_only_in_debug_mode() -> None:
    bus = MonitoringBus(detail_level="DEBUG")

    class _Context:
        broker_name = "OXS_T"
        pair = "EURUSD"

    class _Dispatcher:
        _context = _Context()

    agent = Agent.__new__(Agent)
    agent.agent_id = "OXS_T-EURUSD-AA-ANLYS"
    agent._monitoring_bus = bus
    agent._tool_dispatcher = _Dispatcher()

    agent._emit_llm_diagnostic_event(
        MonitoringEventType.LLM_HTTP_ATTEMPT_STARTED,
        turn=6,
        attempt=1,
    )

    events = bus.recent_events(limit=10)
    assert len(events) == 1
    assert events[0].event_type == MonitoringEventType.LLM_HTTP_ATTEMPT_STARTED
    assert events[0].payload["agent_id"] == "OXS_T-EURUSD-AA-ANLYS"
    assert events[0].payload["turn"] == 6

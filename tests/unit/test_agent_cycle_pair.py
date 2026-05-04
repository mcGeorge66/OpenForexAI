from __future__ import annotations

from openforexai.agents.agent import Agent
from openforexai.models.messaging import EventType


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

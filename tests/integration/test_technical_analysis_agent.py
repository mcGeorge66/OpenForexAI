from __future__ import annotations

import asyncio

import pytest

from tests.conftest import MockBroker, MockLLMProvider, MockRepository, MOCK_BROKER_NAME, make_snapshot
from openforexai.agents.technical_analysis.technical_analysis_agent import TechnicalAnalysisAgent
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType


_TA_PHASE1_RESPONSE = {
    "preliminary_observations": "Uptrend on H4",
    "indicators_needed": [],  # no indicators needed for this test
}

_TA_PHASE2_RESPONSE = {
    "signal": "bullish",
    "confidence": 0.78,
    "reasoning": "Strong H4 uptrend, RSI not overbought",
    "timeframe_signals": {"H1": "bullish", "H4": "bullish", "D1": "neutral"},
    "chart_patterns": [],
    "support_resistance": [],
    "trend_assessments": [],
}


class _TwoPhaseLL(MockLLMProvider):
    """Returns phase-1 response on first call, phase-2 on subsequent calls."""

    def __init__(self) -> None:
        super().__init__()
        self._call_count = 0

    async def complete_structured(self, system_prompt, user_message, response_schema):
        self._call_count += 1
        if self._call_count == 1:
            return _TA_PHASE1_RESPONSE
        return _TA_PHASE2_RESPONSE


def _make_ta_agent() -> tuple[TechnicalAnalysisAgent, EventBus]:
    broker = MockBroker()
    repo = MockRepository()
    bus = EventBus()

    container = DataContainer(repository=repo, event_bus=bus)
    container.register_broker(broker, ["EURUSD"])

    agent = TechnicalAnalysisAgent(
        llm=_TwoPhaseLL(),
        repository=repo,
        bus=bus,
        data_container=container,
        broker_name=MOCK_BROKER_NAME,
    )
    return agent, bus


@pytest.mark.asyncio
async def test_ta_agent_structured_id():
    """TechnicalAnalysisAgent must have the correct structured ID."""
    agent, _ = _make_ta_agent()
    from openforexai.messaging.agent_id import AgentId
    aid = AgentId.parse(agent.agent_id)
    assert aid.type == "GA"
    assert aid.broker == "GLOBL"
    assert aid.pair == "ALL..."


@pytest.mark.asyncio
async def test_ta_agent_responds_to_request():
    """ANALYSIS_REQUESTED via _handle_message should produce ANALYSIS_RESULT."""
    agent, bus = _make_ta_agent()

    results: list[AgentMessage] = []

    async def on_result(msg: AgentMessage) -> None:
        results.append(msg)

    bus.subscribe(EventType.ANALYSIS_RESULT, on_result)

    dispatch_task = asyncio.create_task(bus.start_dispatch_loop())

    snapshot = make_snapshot("EURUSD")
    request = AgentMessage(
        event_type=EventType.ANALYSIS_REQUESTED,
        source_agent_id="MOCKB_EURUSD_AA_TRD1",
        payload={"pair": "EURUSD", "snapshot": snapshot.model_dump(mode="json")},
        correlation_id="test-corr-001",
    )

    # Deliver message directly to agent via _handle_message
    await agent._handle_message(request)

    # Give the bus a moment to dispatch the result
    await asyncio.sleep(0.2)
    dispatch_task.cancel()
    try:
        await dispatch_task
    except asyncio.CancelledError:
        pass

    assert len(results) == 1
    assert results[0].correlation_id == "test-corr-001"
    assert results[0].payload["signal"] == "bullish"

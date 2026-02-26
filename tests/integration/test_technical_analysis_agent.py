from __future__ import annotations

import asyncio

import pytest

from tests.conftest import MockLLMProvider, MockRepository, make_snapshot
from openforexai.agents.technical_analysis.technical_analysis_agent import TechnicalAnalysisAgent
from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType


_TA_RESPONSE = {
    "signal": "bullish",
    "confidence": 0.78,
    "reasoning": "Strong H4 uptrend, RSI not overbought",
    "timeframe_signals": {"H1": "bullish", "H4": "bullish", "D1": "neutral"},
    "chart_patterns": [],
    "support_resistance": [],
    "trend_assessments": [],
}


@pytest.mark.asyncio
async def test_ta_agent_responds_to_request():
    llm = MockLLMProvider(structured_response=_TA_RESPONSE)
    repo = MockRepository()
    bus = EventBus()

    ta_agent = TechnicalAnalysisAgent(llm=llm, repository=repo, bus=bus)
    bus.subscribe(EventType.ANALYSIS_REQUESTED, ta_agent.on_analysis_requested)

    results: list[AgentMessage] = []
    async def on_result(msg: AgentMessage):
        results.append(msg)
    bus.subscribe(EventType.ANALYSIS_RESULT, on_result)

    dispatch_task = asyncio.create_task(bus.start_dispatch_loop())

    snapshot = make_snapshot("EURUSD")
    request = AgentMessage(
        event_type=EventType.ANALYSIS_REQUESTED,
        source_agent_id="trading_EURUSD",
        payload={"pair": "EURUSD", "snapshot": snapshot.model_dump(mode="json")},
        correlation_id="test-corr-001",
    )
    await bus.publish(request)

    # Give the bus time to dispatch
    await asyncio.sleep(0.5)
    dispatch_task.cancel()
    try:
        await dispatch_task
    except asyncio.CancelledError:
        pass

    assert len(results) == 1
    assert results[0].correlation_id == "test-corr-001"
    assert results[0].payload["signal"] == "bullish"


@pytest.mark.asyncio
async def test_ta_agent_timeout_in_trading_agent():
    """TradingAgent must proceed gracefully when analysis times out."""
    from tests.conftest import MockBroker
    from openforexai.agents.trading.trading_agent import TradingAgent
    from openforexai.data.container import DataContainer

    broker = MockBroker()
    # LLM first call requests deep analysis, second call returns HOLD
    call_count = [0]

    class SlowLLM(MockLLMProvider):
        async def complete_structured(self, system_prompt, user_message, response_schema):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "action": "HOLD",
                    "confidence": 0.5,
                    "reasoning": "Ambiguous",
                    "needs_deep_analysis": True,
                }
            return {
                "action": "HOLD",
                "confidence": 0.5,
                "reasoning": "No TA available",
                "needs_deep_analysis": False,
            }

    llm = SlowLLM()
    repo = MockRepository()
    bus = EventBus()
    container = DataContainer(broker=broker, repository=repo, pairs=["EURUSD"], rolling_weeks=1)
    await container.initialize()

    agent = TradingAgent(
        pair="EURUSD",
        broker=broker,
        data_container=container,
        llm=llm,
        repository=repo,
        bus=bus,
        cycle_interval_seconds=0,
        analysis_timeout_seconds=0.1,  # very short timeout
    )

    # No TA agent subscribed → request will time out
    dispatch_task = asyncio.create_task(bus.start_dispatch_loop())
    await agent.run_cycle()
    dispatch_task.cancel()
    try:
        await dispatch_task
    except asyncio.CancelledError:
        pass

    # Should complete without error even with timeout
    assert call_count[0] >= 1

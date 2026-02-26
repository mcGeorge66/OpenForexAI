from __future__ import annotations

import asyncio

import pytest

from tests.conftest import MockBroker, MockLLMProvider, MockRepository, make_snapshot
from openforexai.agents.trading.trading_agent import TradingAgent
from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import EventType


@pytest.mark.asyncio
async def test_trading_agent_publishes_signal():
    broker = MockBroker()
    llm = MockLLMProvider()
    repo = MockRepository()
    bus = EventBus()

    from openforexai.data.container import DataContainer
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
    )

    published: list = []
    bus.subscribe(EventType.SIGNAL_GENERATED, lambda msg: published.append(msg) or asyncio.coroutine(lambda: None)())

    async def mock_subscribe(msg):
        published.append(msg)

    bus.subscribe(EventType.SIGNAL_GENERATED, mock_subscribe)

    # Run one cycle only
    agent._running = True
    await agent.run_cycle()

    assert len(published) >= 1
    assert published[0].event_type == EventType.SIGNAL_GENERATED
    assert published[0].payload["pair"] == "EURUSD"


@pytest.mark.asyncio
async def test_trading_agent_hold_does_not_publish():
    broker = MockBroker()
    llm = MockLLMProvider(structured_response={
        "action": "HOLD",
        "confidence": 0.4,
        "reasoning": "no clear signal",
        "needs_deep_analysis": False,
    })
    repo = MockRepository()
    bus = EventBus()

    from openforexai.data.container import DataContainer
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
    )

    published: list = []
    async def on_signal(msg):
        published.append(msg)
    bus.subscribe(EventType.SIGNAL_GENERATED, on_signal)

    await agent.run_cycle()
    assert len(published) == 0

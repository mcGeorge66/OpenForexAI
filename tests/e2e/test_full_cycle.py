from __future__ import annotations

import asyncio

import pytest

from tests.conftest import MockBroker, MockLLMProvider, MockRepository
from openforexai.agents.optimization.optimization_agent import OptimizationAgent
from openforexai.agents.supervisor.supervisor_agent import SupervisorAgent
from openforexai.agents.technical_analysis.technical_analysis_agent import TechnicalAnalysisAgent
from openforexai.agents.trading.trading_agent import TradingAgent
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.messaging.handlers import wire_subscriptions
from openforexai.models.messaging import EventType
from openforexai.models.risk import RiskParameters


async def _build_system(pairs: list[str]):
    broker = MockBroker()
    repo = MockRepository()
    bus = EventBus()

    container = DataContainer(broker=broker, repository=repo, pairs=pairs, rolling_weeks=1)
    await container.initialize()

    llm = MockLLMProvider()
    risk_params = RiskParameters()

    supervisor = SupervisorAgent(
        risk_params=risk_params,
        broker=broker,
        data_container=container,
        pairs=pairs,
        llm=llm,
        repository=repo,
        bus=bus,
    )

    trading_agents = [
        TradingAgent(
            pair=pair,
            broker=broker,
            data_container=container,
            llm=llm,
            repository=repo,
            bus=bus,
            cycle_interval_seconds=0,
        )
        for pair in pairs
    ]

    ta_agent = TechnicalAnalysisAgent(llm=llm, repository=repo, bus=bus)
    opt_agent = OptimizationAgent(
        pairs=pairs,
        data_container=container,
        llm=llm,
        repository=repo,
        bus=bus,
        min_trades_before_run=100,
    )

    wire_subscriptions(bus, supervisor, trading_agents, ta_agent, opt_agent)
    return broker, repo, bus, trading_agents, supervisor


@pytest.mark.asyncio
async def test_single_pair_full_cycle():
    """Minimum configuration: one pair → one TradingAgent."""
    broker, repo, bus, agents, supervisor = await _build_system(["EURUSD"])
    assert len(agents) == 1

    dispatch_task = asyncio.create_task(bus.start_dispatch_loop())

    signals_approved: list = []
    async def on_approved(msg): signals_approved.append(msg)
    bus.subscribe(EventType.SIGNAL_APPROVED, on_approved)

    await agents[0].run_cycle()
    await asyncio.sleep(0.3)  # let bus dispatch

    dispatch_task.cancel()
    try:
        await dispatch_task
    except asyncio.CancelledError:
        pass

    assert len(signals_approved) >= 1
    assert len(broker.orders) >= 1


@pytest.mark.asyncio
async def test_three_pairs_full_cycle():
    """Variable agent count: three pairs → three TradingAgents."""
    pairs = ["EURUSD", "USDJPY", "GBPUSD"]
    broker, repo, bus, agents, supervisor = await _build_system(pairs)
    assert len(agents) == 3

    dispatch_task = asyncio.create_task(bus.start_dispatch_loop())

    signals_approved: list = []
    async def on_approved(msg): signals_approved.append(msg)
    bus.subscribe(EventType.SIGNAL_APPROVED, on_approved)

    # Run one cycle per agent
    await asyncio.gather(*[a.run_cycle() for a in agents])
    await asyncio.sleep(0.5)

    dispatch_task.cancel()
    try:
        await dispatch_task
    except asyncio.CancelledError:
        pass

    assert len(broker.orders) == len(pairs)
    handled_pairs = {msg.payload["pair"] for msg in signals_approved}
    assert handled_pairs == set(pairs)

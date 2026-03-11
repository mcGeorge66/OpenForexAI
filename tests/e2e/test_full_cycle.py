from __future__ import annotations

import asyncio

import pytest
from openforexai.agents.optimization.optimization_agent import OptimizationAgent
from openforexai.agents.supervisor.supervisor_agent import SupervisorAgent
from openforexai.agents.technical_analysis.technical_analysis_agent import TechnicalAnalysisAgent
from openforexai.agents.trading.trading_agent import TradingAgent

from openforexai.data.container import DataContainer
from openforexai.messaging.agent_id import AgentId
from openforexai.messaging.bus import EventBus
from openforexai.models.risk import RiskParameters
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.tools.base import ToolContext
from openforexai.tools.dispatcher import ToolDispatcher
from tests.conftest import MOCK_BROKER_NAME, MockBroker, MockLLMProvider, MockRepository


async def _build_system(pairs: list[str]):
    broker = MockBroker()
    repo = MockRepository()
    bus = EventBus()

    container = DataContainer(repository=repo, event_bus=bus)
    container.register_broker(broker, pairs)
    container.subscribe_to_bus()

    llm = MockLLMProvider()
    risk_params = RiskParameters()

    supervisor = SupervisorAgent(
        broker_name=MOCK_BROKER_NAME,
        risk_params=risk_params,
        broker=broker,
        data_container=container,
        pairs=pairs,
        llm=llm,
        repository=repo,
        bus=bus,
    )

    trading_agents: list[TradingAgent] = []
    for pair in pairs:
        aid = AgentId.build(broker=MOCK_BROKER_NAME, pair=pair, agent_type="AA", name="TRD1")
        agent_id_str = aid.format()
        context = ToolContext(
            agent_id=agent_id_str,
            broker_name=MOCK_BROKER_NAME,
            pair=pair,
            data_container=container,
            repository=repo,
            broker=broker,
            event_bus=bus,
        )
        dispatcher = ToolDispatcher(registry=DEFAULT_REGISTRY, context=context)
        trading_agents.append(TradingAgent(
            broker_name=MOCK_BROKER_NAME,
            pair=pair,
            data_container=container,
            llm=llm,
            repository=repo,
            bus=bus,
            tool_dispatcher=dispatcher,
            cycle_interval_seconds=0,
        ))

    ta_agent = TechnicalAnalysisAgent(
        llm=llm,
        repository=repo,
        bus=bus,
        data_container=container,
        broker_name=MOCK_BROKER_NAME,
    )
    opt_agent = OptimizationAgent(
        pairs=pairs,
        data_container=container,
        llm=llm,
        repository=repo,
        bus=bus,
        min_trades_before_run=100,
    )

    return broker, repo, bus, trading_agents, supervisor, ta_agent, opt_agent


@pytest.mark.asyncio
async def test_single_pair_full_cycle():
    """Minimum configuration: one pair → one TradingAgent, run one cycle."""
    broker, repo, bus, agents, supervisor, ta_agent, opt_agent = await _build_system(["EURUSD"])
    assert len(agents) == 1

    dispatch_task = asyncio.create_task(bus.start_dispatch_loop())

    # Run one cycle for the trading agent
    for agent in agents:
        agent._running = True
        await agent.run_cycle()

    await asyncio.sleep(0.2)  # let bus drain

    dispatch_task.cancel()
    try:
        await dispatch_task
    except asyncio.CancelledError:
        pass

    # Each trading agent should have saved one AgentDecision
    assert len(repo.decisions) == 1
    assert repo.decisions[0].pair == "EURUSD"


@pytest.mark.asyncio
async def test_three_pairs_full_cycle():
    """Variable agent count: three pairs → three TradingAgents, one decision each."""
    pairs = ["EURUSD", "USDJPY", "GBPUSD"]
    broker, repo, bus, agents, supervisor, ta_agent, opt_agent = await _build_system(pairs)
    assert len(agents) == 3

    dispatch_task = asyncio.create_task(bus.start_dispatch_loop())

    for agent in agents:
        agent._running = True
    await asyncio.gather(*[a.run_cycle() for a in agents])

    await asyncio.sleep(0.3)

    dispatch_task.cancel()
    try:
        await dispatch_task
    except asyncio.CancelledError:
        pass

    # Three decisions, one per pair
    assert len(repo.decisions) == 3
    decision_pairs = {d.pair for d in repo.decisions}
    assert decision_pairs == set(pairs)


@pytest.mark.asyncio
async def test_all_agents_have_structured_ids():
    """All agents must use valid structured agent IDs."""
    pairs = ["EURUSD"]
    broker, repo, bus, trading_agents, supervisor, ta_agent, opt_agent = await _build_system(pairs)

    all_agents = [supervisor, *trading_agents, ta_agent, opt_agent]
    for agent in all_agents:
        parsed = AgentId.try_parse(agent.agent_id)
        assert parsed is not None, f"Agent {agent.agent_id!r} has invalid structured ID"

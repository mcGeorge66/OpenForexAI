from __future__ import annotations

import asyncio

import pytest

from tests.conftest import MockBroker, MockLLMProvider, MockRepository, MOCK_BROKER_NAME
from openforexai.agents.trading.trading_agent import TradingAgent
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.tools.base import ToolContext
from openforexai.tools.dispatcher import ToolDispatcher


def _make_trading_agent(
    pair: str = "EURUSD",
    response_text: str = "HOLD — no clear signal.",
) -> tuple[TradingAgent, MockRepository]:
    broker = MockBroker()
    llm = MockLLMProvider(response_text=response_text)
    repo = MockRepository()
    bus = EventBus()

    container = DataContainer(repository=repo, event_bus=bus)
    container.register_broker(broker, [pair])

    context = ToolContext(
        agent_id=f"MOCKB_{pair.ljust(6, '.')[:6]}_AA_TRD1",
        broker_name=MOCK_BROKER_NAME,
        pair=pair,
        data_container=container,
        repository=repo,
        broker=broker,
        event_bus=bus,
    )
    dispatcher = ToolDispatcher(registry=DEFAULT_REGISTRY, context=context)

    agent = TradingAgent(
        broker_name=MOCK_BROKER_NAME,
        pair=pair,
        data_container=container,
        llm=llm,
        repository=repo,
        bus=bus,
        tool_dispatcher=dispatcher,
        cycle_interval_seconds=0,
    )
    return agent, repo


@pytest.mark.asyncio
async def test_trading_agent_run_cycle_saves_decision():
    """run_cycle() should call the LLM and persist an AgentDecision."""
    agent, repo = _make_trading_agent()

    agent._running = True
    await agent.run_cycle()

    assert len(repo.decisions) == 1
    assert repo.decisions[0].agent_id == agent.agent_id
    assert repo.decisions[0].pair == "EURUSD"


@pytest.mark.asyncio
async def test_trading_agent_structured_id():
    """Agent ID must follow the structured naming convention."""
    agent, _ = _make_trading_agent()
    from openforexai.messaging.agent_id import AgentId
    aid = AgentId.parse(agent.agent_id)
    assert aid.type == "AA"
    assert aid.name == "TRD1"


@pytest.mark.asyncio
async def test_trading_agent_handle_prompt_updated():
    """PROMPT_UPDATED message must update the agent's system prompt."""
    from openforexai.models.messaging import AgentMessage, EventType

    agent, _ = _make_trading_agent()
    agent.load_prompt("original prompt")

    msg = AgentMessage(
        event_type=EventType.PROMPT_UPDATED,
        source_agent_id="GLOBL_ALL..._GA_OPT1",
        payload={"system_prompt": "new improved prompt", "pair": "EURUSD"},
    )
    await agent._handle_message(msg)
    assert agent._system_prompt == "new improved prompt"

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from openforexai.agents.optimization.optimization_agent import OptimizationAgent

from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.models.trade import (
    TradeDirection,
    TradeOrder,
    TradeResult,
    TradeSignal,
    TradeStatus,
)
from tests.conftest import MockBroker, MockLLMProvider, MockRepository


def _make_closed_trade(pnl: float, pair: str = "EURUSD") -> TradeResult:
    now = datetime.now(UTC)
    signal = TradeSignal(
        pair=pair,
        direction=TradeDirection.BUY,
        entry_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        confidence=0.8,
        reasoning="test",
        generated_at=now,
        agent_id="MOCKB_EURUSD_AA_TRD1",
    )
    order = TradeOrder(signal=signal, units=1000, risk_pct=1.0, approved_by="MOCKB_ALL..._BA_SUP1")
    return TradeResult(
        order=order,
        broker_order_id="ORD",
        status=TradeStatus.CLOSED,
        pnl=Decimal(str(pnl)),
        opened_at=now.replace(hour=10),
        closed_at=now,
    )


def _make_opt_agent(min_trades: int = 20) -> tuple[OptimizationAgent, MockRepository]:
    broker = MockBroker()
    repo = MockRepository()
    bus = EventBus()

    container = DataContainer(repository=repo, event_bus=bus)
    container.register_broker(broker, ["EURUSD"])

    agent = OptimizationAgent(
        pairs=["EURUSD"],
        data_container=container,
        llm=MockLLMProvider(),
        repository=repo,
        bus=bus,
        min_trades_before_run=min_trades,
    )
    return agent, repo


@pytest.mark.asyncio
async def test_optimization_structured_id():
    """OptimizationAgent must have the correct structured ID."""
    agent, _ = _make_opt_agent()
    from openforexai.messaging.agent_id import AgentId
    aid = AgentId.parse(agent.agent_id)
    assert aid.type == "GA"
    assert aid.broker == "GLOBL"
    assert aid.name == "OPT1"


@pytest.mark.asyncio
async def test_optimization_skips_insufficient_trades():
    """Agent should skip optimization when fewer trades than threshold exist."""
    agent, repo = _make_opt_agent(min_trades=20)

    for t in [_make_closed_trade(10.0) for _ in range(5)]:
        await repo.save_trade(t)

    await agent._optimize_pair("EURUSD")
    assert len(repo.prompts) == 0


@pytest.mark.asyncio
async def test_optimization_creates_prompt_candidate():
    """Agent should generate and save a prompt candidate with enough trades."""
    agent, repo = _make_opt_agent(min_trades=5)

    new_prompt_text = "Improved: focus on london session BUY signals only."
    from openforexai.ports.llm import LLMResponse

    async def mock_complete(system_prompt, user_message, **_):
        return LLMResponse(
            content=new_prompt_text, model="mock", input_tokens=50, output_tokens=80, raw={}
        )

    agent.llm.complete = mock_complete  # type: ignore[method-assign]

    for t in [_make_closed_trade(15.0) for _ in range(10)]:
        await repo.save_trade(t)

    await agent._optimize_pair("EURUSD")
    assert len(repo.prompts) >= 1

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.conftest import MockBroker, MockLLMProvider, MockRepository
from openforexai.agents.optimization.optimization_agent import OptimizationAgent
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import EventType
from openforexai.models.trade import (
    TradeDirection,
    TradeOrder,
    TradeResult,
    TradeSignal,
    TradeStatus,
)


def _make_closed_trade(pnl: float, pair: str = "EURUSD") -> TradeResult:
    now = datetime.now(timezone.utc)
    signal = TradeSignal(
        pair=pair,
        direction=TradeDirection.BUY,
        entry_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        confidence=0.8,
        reasoning="test",
        generated_at=now,
        agent_id="trading_EURUSD",
    )
    order = TradeOrder(signal=signal, units=1000, risk_pct=1.0, approved_by="supervisor")
    return TradeResult(
        order=order,
        broker_order_id="ORD",
        status=TradeStatus.CLOSED,
        pnl=Decimal(str(pnl)),
        opened_at=now.replace(hour=10),
        closed_at=now,
    )


@pytest.mark.asyncio
async def test_optimization_skips_insufficient_trades():
    broker = MockBroker()
    repo = MockRepository()
    bus = EventBus()
    container = DataContainer(broker=broker, repository=repo, pairs=["EURUSD"], rolling_weeks=1)
    await container.initialize()

    agent = OptimizationAgent(
        pairs=["EURUSD"],
        data_container=container,
        llm=MockLLMProvider(),
        repository=repo,
        bus=bus,
        min_trades_before_run=20,
    )

    # Only 5 trades — below threshold
    for t in [_make_closed_trade(10.0) for _ in range(5)]:
        await repo.save_trade(t)

    await agent._optimize_pair("EURUSD")
    # No prompt candidate should have been created
    assert len(repo.prompts) == 0


@pytest.mark.asyncio
async def test_optimization_creates_prompt_candidate():
    broker = MockBroker()
    repo = MockRepository()
    bus = EventBus()
    container = DataContainer(broker=broker, repository=repo, pairs=["EURUSD"], rolling_weeks=1)
    await container.initialize()

    new_prompt_text = "Improved: focus on london session BUY signals only."
    llm = MockLLMProvider()
    from openforexai.ports.llm import LLMResponse
    async def mock_complete(system_prompt, user_message, **_):
        return LLMResponse(content=new_prompt_text, model="mock", input_tokens=50, output_tokens=80, raw={})
    llm.complete = mock_complete

    agent = OptimizationAgent(
        pairs=["EURUSD"],
        data_container=container,
        llm=llm,
        repository=repo,
        bus=bus,
        min_trades_before_run=5,
    )

    # Enough winning trades to trigger pattern detection
    for t in [_make_closed_trade(15.0) for _ in range(10)]:
        await repo.save_trade(t)

    await agent._optimize_pair("EURUSD")
    assert len(repo.prompts) >= 1
    assert new_prompt_text in repo.prompts[-1].system_prompt

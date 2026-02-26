from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.conftest import MockBroker, MockLLMProvider, MockRepository
from openforexai.agents.supervisor.supervisor_agent import SupervisorAgent
from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.risk import RiskParameters
from openforexai.models.trade import TradeDirection, TradeSignal


def _signal_message(pair: str = "EURUSD") -> AgentMessage:
    signal = TradeSignal(
        pair=pair,
        direction=TradeDirection.BUY,
        entry_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        confidence=0.80,
        reasoning="test",
        generated_at=datetime.now(timezone.utc),
        agent_id="trading_EURUSD",
    )
    return AgentMessage(
        event_type=EventType.SIGNAL_GENERATED,
        source_agent_id="trading_EURUSD",
        payload={
            "pair": pair,
            "signal_id": str(signal.id),
            "signal": signal.model_dump(mode="json"),
        },
    )


@pytest.mark.asyncio
async def test_supervisor_approves_valid_signal():
    broker = MockBroker()
    repo = MockRepository()
    bus = EventBus()
    container = DataContainer(broker=broker, repository=repo, pairs=["EURUSD"], rolling_weeks=1)
    await container.initialize()

    supervisor = SupervisorAgent(
        risk_params=RiskParameters(),
        broker=broker,
        data_container=container,
        pairs=["EURUSD"],
        llm=MockLLMProvider(),
        repository=repo,
        bus=bus,
    )

    approved: list[AgentMessage] = []
    async def on_approved(msg): approved.append(msg)
    bus.subscribe(EventType.SIGNAL_APPROVED, on_approved)

    await supervisor.on_signal_generated(_signal_message())

    assert len(approved) == 1
    assert approved[0].payload["pair"] == "EURUSD"
    assert len(broker.orders) == 1


@pytest.mark.asyncio
async def test_supervisor_rejects_at_position_limit():
    from openforexai.models.trade import Position

    broker = MockBroker()

    async def too_many_positions():
        return [
            Position(
                broker_position_id=str(i),
                pair="USDJPY",
                direction=TradeDirection.BUY,
                units=1000,
                open_price=Decimal("150.0"),
                current_price=Decimal("150.5"),
                unrealized_pnl=Decimal("50"),
                opened_at=datetime.now(timezone.utc),
            )
            for i in range(6)  # already at max
        ]

    broker.get_open_positions = too_many_positions

    repo = MockRepository()
    bus = EventBus()
    container = DataContainer(broker=broker, repository=repo, pairs=["EURUSD"], rolling_weeks=1)
    await container.initialize()

    supervisor = SupervisorAgent(
        risk_params=RiskParameters(max_open_positions=6),
        broker=broker,
        data_container=container,
        pairs=["EURUSD"],
        llm=MockLLMProvider(),
        repository=repo,
        bus=bus,
    )

    rejected: list[AgentMessage] = []
    async def on_rejected(msg): rejected.append(msg)
    bus.subscribe(EventType.SIGNAL_REJECTED, on_rejected)

    await supervisor.on_signal_generated(_signal_message())
    assert len(rejected) == 1

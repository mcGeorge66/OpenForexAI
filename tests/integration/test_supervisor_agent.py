from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.conftest import MockBroker, MockLLMProvider, MockRepository, MOCK_BROKER_NAME
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
        agent_id=f"MOCKB_{pair.ljust(6, '.')[:6]}_AA_TRD1",
    )
    return AgentMessage(
        event_type=EventType.SIGNAL_GENERATED,
        source_agent_id=f"MOCKB_{pair.ljust(6, '.')[:6]}_AA_TRD1",
        payload={
            "pair": pair,
            "signal_id": str(signal.id),
            "signal": signal.model_dump(mode="json"),
        },
    )


def _make_supervisor(pairs: list[str] | None = None) -> tuple[SupervisorAgent, MockBroker, MockRepository]:
    pairs = pairs or ["EURUSD"]
    broker = MockBroker()
    repo = MockRepository()
    bus = EventBus()

    container = DataContainer(repository=repo, event_bus=bus)
    container.register_broker(broker, pairs)

    supervisor = SupervisorAgent(
        broker_name=MOCK_BROKER_NAME,
        risk_params=RiskParameters(),
        broker=broker,
        data_container=container,
        pairs=pairs,
        llm=MockLLMProvider(),
        repository=repo,
        bus=bus,
    )
    return supervisor, broker, repo


@pytest.mark.asyncio
async def test_supervisor_structured_id():
    """Supervisor agent_id must match the BA_SUP1 naming convention."""
    supervisor, _, _ = _make_supervisor()
    from openforexai.messaging.agent_id import AgentId
    aid = AgentId.parse(supervisor.agent_id)
    assert aid.type == "BA"
    assert aid.name == "SUP1"
    assert aid.pair == "ALL..."


@pytest.mark.asyncio
async def test_supervisor_approves_valid_signal():
    """Supervisor should approve a valid signal and place an order."""
    supervisor, broker, repo = _make_supervisor()

    approved: list[AgentMessage] = []

    async def on_approved(msg: AgentMessage) -> None:
        approved.append(msg)

    supervisor.bus.subscribe(EventType.SIGNAL_APPROVED, on_approved)

    await supervisor._on_signal_generated(_signal_message())

    assert len(approved) == 1
    assert approved[0].payload["pair"] == "EURUSD"
    assert len(broker.orders) == 1


@pytest.mark.asyncio
async def test_supervisor_rejects_at_position_limit():
    """Supervisor should reject when the position limit is already reached."""
    from openforexai.models.trade import Position

    supervisor, broker, _ = _make_supervisor()

    # Simulate broker already at max positions
    broker._positions = [
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
        for i in range(6)
    ]
    supervisor.risk_engine.params.max_open_positions = 6

    rejected: list[AgentMessage] = []

    async def on_rejected(msg: AgentMessage) -> None:
        rejected.append(msg)

    supervisor.bus.subscribe(EventType.SIGNAL_REJECTED, on_rejected)

    await supervisor._on_signal_generated(_signal_message())
    assert len(rejected) == 1


@pytest.mark.asyncio
async def test_supervisor_handle_message_routes_signal():
    """SIGNAL_GENERATED delivered via _handle_message must trigger approval flow."""
    supervisor, broker, _ = _make_supervisor()

    approved: list = []

    async def on_approved(msg: AgentMessage) -> None:
        approved.append(msg)

    supervisor.bus.subscribe(EventType.SIGNAL_APPROVED, on_approved)

    await supervisor._handle_message(_signal_message())
    assert len(approved) == 1

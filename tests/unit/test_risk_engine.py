from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from openforexai.agents.supervisor.risk_engine import RiskEngine
from openforexai.models.risk import RiskParameters
from openforexai.models.trade import TradeDirection, TradeSignal


def make_signal(pair="EURUSD", direction=TradeDirection.BUY):
    return TradeSignal(
        pair=pair,
        direction=direction,
        entry_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        confidence=0.8,
        reasoning="test",
        generated_at=datetime.now(UTC),
        agent_id="test",
    )


def test_approve_clean_state():
    engine = RiskEngine(RiskParameters())
    assessment = engine.assess(
        signal=make_signal(),
        open_positions=[],
        account_balance=10_000.0,
        daily_pnl=0.0,
        correlation_matrix=None,
    )
    assert assessment.approved
    assert assessment.adjusted_units and assessment.adjusted_units > 0


def test_reject_max_positions(mock_broker):
    from openforexai.models.trade import Position

    params = RiskParameters(max_open_positions=2)
    engine = RiskEngine(params)

    positions = [
        Position(
            broker_position_id=str(i),
            pair="EURUSD",
            direction=TradeDirection.BUY,
            units=1000,
            open_price=Decimal("1.1000"),
            current_price=Decimal("1.1010"),
            unrealized_pnl=Decimal("10"),
            opened_at=datetime.now(UTC),
        )
        for i in range(3)
    ]
    assessment = engine.assess(
        signal=make_signal(),
        open_positions=positions,
        account_balance=10_000.0,
        daily_pnl=0.0,
        correlation_matrix=None,
    )
    assert not assessment.approved
    assert "Max open positions" in (assessment.rejection_reason or "")


def test_reject_drawdown_exceeded():
    from openforexai.models.trade import Position

    params = RiskParameters(max_drawdown_pct=5.0)
    engine = RiskEngine(params)

    positions = [
        Position(
            broker_position_id="1",
            pair="EURUSD",
            direction=TradeDirection.BUY,
            units=1000,
            open_price=Decimal("1.1000"),
            current_price=Decimal("1.0500"),
            unrealized_pnl=Decimal("-600"),
            opened_at=datetime.now(UTC),
        )
    ]
    assessment = engine.assess(
        signal=make_signal(),
        open_positions=positions,
        account_balance=10_000.0,
        daily_pnl=0.0,
        correlation_matrix=None,
    )
    assert not assessment.approved
    assert "drawdown" in (assessment.rejection_reason or "").lower()

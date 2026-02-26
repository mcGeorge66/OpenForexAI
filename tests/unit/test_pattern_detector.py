from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from openforexai.agents.optimization.pattern_detector import detect_patterns
from openforexai.models.trade import (
    TradeDirection,
    TradeOrder,
    TradeResult,
    TradeSignal,
    TradeStatus,
)


def _make_trade(pnl: float, direction: str = "BUY", hour: int = 9) -> TradeResult:
    opened = datetime.now(timezone.utc).replace(hour=hour)
    signal = TradeSignal(
        pair="EURUSD",
        direction=TradeDirection(direction),
        entry_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        confidence=0.8,
        reasoning="test",
        generated_at=opened,
        agent_id="trading_EURUSD",
    )
    order = TradeOrder(signal=signal, units=1000, risk_pct=1.0, approved_by="supervisor")
    return TradeResult(
        order=order,
        broker_order_id=f"ORD_{pnl}",
        status=TradeStatus.CLOSED,
        pnl=Decimal(str(pnl)),
        opened_at=opened,
        closed_at=opened,
    )


def test_no_patterns_for_small_sample():
    trades = [_make_trade(10.0)] * 3
    patterns = detect_patterns(trades)
    assert patterns == []


def test_detects_session_bias():
    # All trades in london session with high win rate
    trades = [_make_trade(20.0, hour=10) for _ in range(10)] + [
        _make_trade(-5.0, hour=10) for _ in range(2)
    ]
    patterns = detect_patterns(trades)
    session_patterns = [p for p in patterns if p.pattern_type == "session_bias"]
    assert len(session_patterns) >= 1
    assert any(p.win_rate_when_present >= 0.6 for p in session_patterns)


def test_detects_direction_bias():
    # All BUY trades winning
    trades = [_make_trade(15.0, direction="BUY") for _ in range(8)] + [
        _make_trade(-3.0, direction="SELL") for _ in range(4)
    ]
    patterns = detect_patterns(trades)
    dir_patterns = [p for p in patterns if p.pattern_type == "direction_bias"]
    assert len(dir_patterns) >= 1

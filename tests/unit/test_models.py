from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from openforexai.models.analysis import AnalysisResult, SignalDirection
from openforexai.models.market import Candle, Tick
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.risk import RiskParameters
from openforexai.models.trade import TradeDirection, TradeSignal


def test_tick_mid():
    tick = Tick(
        pair="EURUSD",
        bid=Decimal("1.1000"),
        ask=Decimal("1.1002"),
        timestamp=datetime.now(timezone.utc),
    )
    assert tick.mid == Decimal("1.1001")


def test_trade_signal_confidence_bounds():
    base = dict(
        pair="EURUSD",
        direction=TradeDirection.BUY,
        entry_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        reasoning="test",
        generated_at=datetime.now(timezone.utc),
        agent_id="test_agent",
    )
    signal = TradeSignal(**base, confidence=0.75)
    assert signal.confidence == 0.75

    with pytest.raises(Exception):
        TradeSignal(**base, confidence=1.5)


def test_risk_parameters_defaults():
    rp = RiskParameters()
    assert rp.max_risk_per_trade_pct == 1.0
    assert rp.max_open_positions == 6


def test_agent_message_broadcast():
    msg = AgentMessage(
        event_type=EventType.SIGNAL_GENERATED,
        source_agent_id="trading_EURUSD",
        payload={"pair": "EURUSD"},
    )
    assert msg.target_agent_id is None


def test_analysis_result_fields():
    result = AnalysisResult(
        pair="EURUSD",
        correlation_id="test-corr",
        signal=SignalDirection.BULLISH,
        confidence=0.8,
        reasoning="Strong uptrend",
        timeframe_signals={"H1": "bullish", "H4": "neutral"},
    )
    assert result.signal == SignalDirection.BULLISH
    assert result.timeframe_signals["H1"] == "bullish"

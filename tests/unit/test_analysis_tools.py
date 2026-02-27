from __future__ import annotations

from tests.conftest import make_candle
from openforexai.agents.technical_analysis.analysis_tools import (
    detect_doji,
    detect_engulfing,
    fibonacci_levels,
    find_swing_highs,
    find_swing_lows,
    trend_strength,
)


def test_detect_doji_true():
    from decimal import Decimal
    from datetime import datetime, timezone
    from openforexai.models.market import Candle

    doji = Candle(
        timestamp=datetime.now(timezone.utc),
        open=Decimal("1.1000"),
        high=Decimal("1.1020"),
        low=Decimal("1.0980"),
        close=Decimal("1.1001"),  # tiny body
        tick_volume=500,
        spread=Decimal("0.0002"),
        timeframe="H1",
    )
    assert detect_doji([doji]) is True


def test_detect_doji_false():
    candle = make_candle(close=1.1050)
    assert detect_doji([candle]) is False


def test_detect_engulfing_bullish():
    from decimal import Decimal
    from datetime import datetime, timezone
    from openforexai.models.market import Candle

    prev = Candle(
        timestamp=datetime.now(timezone.utc),
        open=Decimal("1.1050"),
        high=Decimal("1.1060"),
        low=Decimal("1.1020"),
        close=Decimal("1.1025"),  # bearish prev
        tick_volume=500,
        spread=Decimal("0.0002"),
        timeframe="H1",
    )
    curr = Candle(
        timestamp=datetime.now(timezone.utc),
        open=Decimal("1.1010"),
        high=Decimal("1.1080"),
        low=Decimal("1.1000"),
        close=Decimal("1.1070"),  # bullish curr engulfs
        tick_volume=800,
        spread=Decimal("0.0002"),
        timeframe="H1",
    )
    result = detect_engulfing([prev, curr])
    assert result == "bullish"


def test_fibonacci_levels_keys():
    levels = fibonacci_levels(swing_low=1.1000, swing_high=1.1200)
    assert "61.8" in levels
    assert abs(levels["50.0"] - 1.1100) < 0.0001


def test_trend_strength_bullish():
    candles = [make_candle(close=1.1000 + i * 0.0010) for i in range(25)]
    direction, strength = trend_strength(candles)
    assert direction == "bullish"
    assert strength > 0.5


def test_trend_strength_insufficient_data():
    direction, strength = trend_strength([make_candle()])
    assert direction == "neutral"
    assert strength == 0.0

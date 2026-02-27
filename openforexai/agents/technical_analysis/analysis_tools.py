from __future__ import annotations

from openforexai.models.market import Candle


def detect_doji(candles: list[Candle], threshold: float = 0.1) -> bool:
    """Return True if the last candle is a doji (body < threshold * range)."""
    if not candles:
        return False
    c = candles[-1]
    body = abs(float(c.close - c.open))
    candle_range = float(c.high - c.low)
    if candle_range == 0:
        return False
    return body / candle_range < threshold


def detect_engulfing(candles: list[Candle]) -> str | None:
    """Return 'bullish', 'bearish', or None for the last two candles."""
    if len(candles) < 2:
        return None
    prev, curr = candles[-2], candles[-1]
    prev_bullish = prev.close > prev.open
    curr_bullish = curr.close > curr.open

    if (
        not prev_bullish   # previous was bearish
        and curr_bullish   # current is bullish
        and curr.open < prev.close
        and curr.close > prev.open
    ):
        return "bullish"
    if (
        prev_bullish       # previous was bullish
        and not curr_bullish  # current is bearish
        and curr.open > prev.close
        and curr.close < prev.open
    ):
        return "bearish"
    return None


def find_swing_highs(candles: list[Candle], lookback: int = 3) -> list[float]:
    """Return local swing high prices within *lookback* candles on each side."""
    highs = [float(c.high) for c in candles]
    result: list[float] = []
    for i in range(lookback, len(highs) - lookback):
        if highs[i] == max(highs[i - lookback : i + lookback + 1]):
            result.append(highs[i])
    return result


def find_swing_lows(candles: list[Candle], lookback: int = 3) -> list[float]:
    lows = [float(c.low) for c in candles]
    result: list[float] = []
    for i in range(lookback, len(lows) - lookback):
        if lows[i] == min(lows[i - lookback : i + lookback + 1]):
            result.append(lows[i])
    return result


def fibonacci_levels(swing_low: float, swing_high: float) -> dict[str, float]:
    diff = swing_high - swing_low
    return {
        "0.0": swing_low,
        "23.6": swing_high - 0.236 * diff,
        "38.2": swing_high - 0.382 * diff,
        "50.0": swing_high - 0.5 * diff,
        "61.8": swing_high - 0.618 * diff,
        "78.6": swing_high - 0.786 * diff,
        "100.0": swing_high,
    }


def trend_strength(candles: list[Candle], period: int = 20) -> tuple[str, float]:
    """Return (direction, strength 0-1) based on slope of closing prices."""
    if len(candles) < period:
        return "neutral", 0.0
    closes = [float(c.close) for c in candles[-period:]]
    first, last = closes[0], closes[-1]
    total_range = max(closes) - min(closes)
    if total_range == 0:
        return "neutral", 0.0
    strength = min(abs(last - first) / total_range, 1.0)
    direction = "bullish" if last > first else "bearish"
    return direction, round(strength, 3)

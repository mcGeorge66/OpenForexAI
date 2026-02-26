from __future__ import annotations

from typing import Union

from openforexai.data.indicators import atr, bollinger_bands, ema, rsi, sma
from openforexai.data.container import DataContainer

# Return type: single float, a dict (Bollinger Bands), or None when not enough data
IndicatorResult = Union[float, dict[str, float], None]

# Supported indicator names (case-insensitive)
_ALIASES: dict[str, str] = {
    "MA":  "SMA",
    "SMA": "SMA",
    "EMA": "EMA",
    "RSI": "RSI",
    "ATR": "ATR",
    "BB":  "BB",
    "BOLLINGER": "BB",
}


def calculate_indicator(
    indicator: str,
    period: int,
    timeframe: str,
    pair: str,
    data_container: DataContainer,
) -> IndicatorResult:
    """Compute *indicator* on-the-fly for a given *pair* and *timeframe*.

    This is the single shared tool for all agents.  The caller declares
    **what** it needs; this function handles **how** to get the candles
    and compute the value.

    Args:
        indicator:  One of: MA | SMA | EMA | RSI | ATR | BB | BOLLINGER
        period:     Lookback period (e.g. 14 for ATR, 20 for SMA).
        timeframe:  M5 | M15 | M30 | H1 | H4 | D1
        pair:       Currency pair, e.g. "USDJPY" or "EURUSD".
        data_container: Shared DataContainer instance (injected at agent startup).

    Returns:
        - float for SMA / EMA / RSI / ATR
        - dict {"upper": float, "middle": float, "lower": float} for BB
        - None when there are not enough candles to compute the indicator.

    Raises:
        ValueError: for an unrecognised indicator name.
    """
    name = _ALIASES.get(indicator.upper())
    if name is None:
        raise ValueError(
            f"Unknown indicator {indicator!r}. "
            f"Supported: {', '.join(sorted(set(_ALIASES.values())))}"
        )

    candles = data_container.get_candles(pair.upper(), timeframe.upper())
    if not candles:
        return None

    if name == "SMA":
        return sma(candles, period)
    if name == "EMA":
        return ema(candles, period)
    if name == "RSI":
        return rsi(candles, period)
    if name == "ATR":
        return atr(candles, period)
    if name == "BB":
        result = bollinger_bands(candles, period)
        if result is None:
            return None
        upper, middle, lower = result
        return {"upper": upper, "middle": middle, "lower": lower}

    return None  # unreachable, keeps type-checker happy


class IndicatorToolset:
    """Thin wrapper that binds a DataContainer to the calculate_indicator function.

    Agents receive one IndicatorToolset instance at startup and call
    ``toolset.calculate(...)`` directly — no DataContainer reference needed
    at call-site.

    Example (inside any agent):
        result = self.indicators.calculate("ATR", 14, "M15", "USDJPY")
        # → 0.00123 (float)

        bands = self.indicators.calculate("BB", 20, "H1", "EURUSD")
        # → {"upper": 1.0980, "middle": 1.0960, "lower": 1.0940}
    """

    def __init__(self, data_container: DataContainer) -> None:
        self._dc = data_container

    def calculate(
        self,
        indicator: str,
        period: int,
        timeframe: str,
        pair: str,
    ) -> IndicatorResult:
        """Compute *indicator*(*period*) on *pair* candles at *timeframe*."""
        return calculate_indicator(indicator, period, timeframe, pair, self._dc)

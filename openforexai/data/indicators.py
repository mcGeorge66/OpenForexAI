from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta as ta
from scipy.signal import find_peaks

from openforexai.models.market import Candle


def _closes(candles: list[Candle]) -> np.ndarray:
    return np.array([float(c.close) for c in candles], dtype=float)


def _highs(candles: list[Candle]) -> np.ndarray:
    return np.array([float(c.high) for c in candles], dtype=float)


def _lows(candles: list[Candle]) -> np.ndarray:
    return np.array([float(c.low) for c in candles], dtype=float)


def candles_to_df(candles: list[Candle]) -> pd.DataFrame:
    return pd.DataFrame({
        "open":   [float(c.open)        for c in candles],
        "high":   [float(c.high)        for c in candles],
        "low":    [float(c.low)         for c in candles],
        "close":  [float(c.close)       for c in candles],
        "volume": [float(c.tick_volume) for c in candles],
    })


def sma(candles: list[Candle], period: int) -> float | None:
    if len(candles) < period:
        return None
    df = candles_to_df(candles)
    result = ta.sma(df["close"], length=period)
    if result is None or result.empty:
        return None
    val = result.iloc[-1]
    return None if pd.isna(val) else float(val)


def ema(candles: list[Candle], period: int) -> float | None:
    if len(candles) < period:
        return None
    df = candles_to_df(candles)
    result = ta.ema(df["close"], length=period)
    if result is None or result.empty:
        return None
    val = result.iloc[-1]
    return None if pd.isna(val) else float(val)


def rsi(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    df = candles_to_df(candles)
    result = ta.rsi(df["close"], length=period)
    if result is None or result.empty:
        return None
    val = result.iloc[-1]
    return None if pd.isna(val) else float(val)


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    df = candles_to_df(candles)
    result = ta.atr(df["high"], df["low"], df["close"], length=period)
    if result is None or result.empty:
        return None
    val = result.iloc[-1]
    return None if pd.isna(val) else float(val)


def bollinger_bands(
    candles: list[Candle], period: int = 20, num_std: float = 2.0
) -> tuple[float, float, float] | None:
    """Returns (upper, middle, lower)."""
    if len(candles) < period:
        return None
    df = candles_to_df(candles)
    result = ta.bbands(df["close"], length=period, std=num_std)
    if result is None or result.empty:
        return None
    upper_cols = [c for c in result.columns if c.startswith("BBU_")]
    mid_cols   = [c for c in result.columns if c.startswith("BBM_")]
    lower_cols = [c for c in result.columns if c.startswith("BBL_")]
    if not (upper_cols and mid_cols and lower_cols):
        return None
    upper  = result[upper_cols[0]].iloc[-1]
    middle = result[mid_cols[0]].iloc[-1]
    lower  = result[lower_cols[0]].iloc[-1]
    if any(pd.isna(v) for v in [upper, middle, lower]):
        return None
    return float(upper), float(middle), float(lower)


def vwap(candles: list[Candle]) -> float | None:
    if not candles:
        return None
    typical_prices = np.array(
        [float(c.high + c.low + c.close) / 3 for c in candles], dtype=float
    )
    volumes = np.array([float(c.tick_volume) for c in candles], dtype=float)
    total_volume = np.sum(volumes)
    if total_volume == 0:
        return None
    return float(np.sum(typical_prices * volumes) / total_volume)


def _find_peaks_plateau(arr: np.ndarray, prominence: float = 0.0) -> list[tuple[int, float]]:
    """Peak detection that handles plateaus (consecutive equal values).

    Returns list of (candle_index, prominence_value) tuples.
    scipy's find_peaks requires strictly greater-than neighbours and silently
    misses plateaus.  This wrapper collapses each run of identical values into
    a single representative index (the midpoint) before calling find_peaks.
    """
    n = len(arr)
    if n < 3:
        return []
    compressed_vals: list[float] = []
    compressed_idx: list[int]   = []
    i = 0
    while i < n:
        j = i
        while j + 1 < n and arr[j + 1] == arr[i]:
            j += 1
        compressed_vals.append(float(arr[i]))
        compressed_idx.append((i + j) // 2)
        i = j + 1
    if len(compressed_vals) < 3:
        return []
    cv = np.array(compressed_vals, dtype=float)
    peaks, props = find_peaks(cv, prominence=prominence)
    prominences = props.get("prominences", np.zeros(len(peaks)))
    return [(compressed_idx[p], float(prominences[k])) for k, p in enumerate(peaks)]


def swing_highs(candles: list[Candle], prominence: float = 0.0) -> list[tuple[int, float]]:
    """Return (index, prominence) pairs of swing high candles."""
    if len(candles) < 3:
        return []
    return _find_peaks_plateau(_highs(candles), prominence)


def swing_lows(candles: list[Candle], prominence: float = 0.0) -> list[tuple[int, float]]:
    """Return (index, prominence) pairs of swing low candles."""
    if len(candles) < 3:
        return []
    return _find_peaks_plateau(-_lows(candles), prominence)


# DXY component weights — ICE formula, USDSEK excluded (5-pair approximation)
_DXY_WEIGHTS: dict[str, float] = {
    "EURUSD": -0.576,
    "USDJPY": +0.136,
    "GBPUSD": -0.119,
    "USDCAD": +0.091,
    "USDCHF": +0.036,
}
_DXY_CONSTANT = 50.14348112


def synthetic_dxy(component_candles: dict[str, list[Candle]]) -> list[float | None]:
    """Compute a synthetic DXY index series from 5 component pairs.

    Uses ICE formula structure (USDSEK excluded — 5-pair approximation).
    Result is aligned to the shortest component series. Returns None at
    positions where any component has invalid (non-positive) data.
    """
    if not component_candles:
        return []
    n = min(len(v) for v in component_candles.values())
    if n == 0:
        return []

    results: list[float | None] = []
    for i in range(n):
        val = _DXY_CONSTANT
        valid = True
        for pair, exponent in _DXY_WEIGHTS.items():
            series = component_candles.get(pair)
            if not series or i >= len(series):
                valid = False
                break
            price = float(series[i].close)
            if price <= 0:
                valid = False
                break
            val *= price ** exponent
        results.append(round(val, 4) if valid else None)
    return results

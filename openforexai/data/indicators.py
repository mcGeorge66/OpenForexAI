from __future__ import annotations

import numpy as np

from openforexai.models.market import Candle


def _closes(candles: list[Candle]) -> np.ndarray:
    return np.array([float(c.close) for c in candles], dtype=float)


def _highs(candles: list[Candle]) -> np.ndarray:
    return np.array([float(c.high) for c in candles], dtype=float)


def _lows(candles: list[Candle]) -> np.ndarray:
    return np.array([float(c.low) for c in candles], dtype=float)


def sma(candles: list[Candle], period: int) -> float | None:
    closes = _closes(candles)
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))


def ema(candles: list[Candle], period: int) -> float | None:
    closes = _closes(candles)
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema_val = closes[0]
    for price in closes[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return float(ema_val)


def rsi(candles: list[Candle], period: int = 14) -> float | None:
    closes = _closes(candles)
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1]),
        ),
    )
    return float(np.mean(tr[-period:]))


def bollinger_bands(
    candles: list[Candle], period: int = 20, num_std: float = 2.0
) -> tuple[float, float, float] | None:
    """Returns (upper, middle, lower)."""
    closes = _closes(candles)
    if len(closes) < period:
        return None
    window = closes[-period:]
    middle = float(np.mean(window))
    std = float(np.std(window, ddof=1))
    return middle + num_std * std, middle, middle - num_std * std


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




"""FOMAK core computation — ported from fomak_engine5.py (external Fomak_service
project). Formulas kept faithful to the original (TR/ATR, Strength/Volatility/
Persistence/Impulse/Noise binning, higher-timeframe EMA alignment) — only the
windowing changed: instead of fixed day-grid state blocks, this computes ONE
FOMAK for an arbitrary floating window ("the last N candles ending at an anchor
timestamp"), which is what a specific trade/analysis moment actually needs.

FOMAK format: {S_bin}{D_char}{V_bin}{P_bin}{I_bin}{N_bin}{A_char} — see
FOMAK_101-2.pdf for the full derivation and worked examples. S/V/P/I/N are
deliberately coarsened to a 1-3 scale (not the original's 1-5) — see the
BINS_* constants below — so an exact pattern_key match in smem actually
recurs often enough across trades to be useful.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Coarsened from fomak_engine5.py's original 5-bin defaults (4 thresholds each,
# e.g. [0.5, 1.0, 1.5, 2.5] for Strength) to 3 bins, so the exact-match pattern_key
# lookup in smem actually finds repeats often enough to be useful. Each new
# threshold is the average of one adjacent pair of the original four
# (first pair -> low/mid boundary, last pair -> mid/high boundary), e.g.
# [0.5, 1.0, 1.5, 2.5] -> [(0.5+1.0)/2, (1.5+2.5)/2] = [0.75, 2.0].
BINS_STRENGTH = [0.75, 2.0]
BINS_VOLA = [0.9, 1.4]
BINS_PERSIST = [0.6, 0.8]
BINS_IMPULSE = [0.75, 1.75]
BINS_NOISE = [0.375, 0.675]

ATR_SHORT_PERIOD = 14
ATR_LONG_PERIOD = 50
IMPULSE_SHIFT = 4
EMA_STATE_PERIOD = 20
EMA_MIN_MOVE_PIPS = 1.0

# Warmup candles needed before the window so the rolling ATR series is settled
# by the time the window itself starts — mirrors fomak_engine5.py's warmup_bars().
WARMUP_CANDLES = max(ATR_SHORT_PERIOD, ATR_LONG_PERIOD)


class FomakInputError(ValueError):
    """Raised when there isn't enough valid candle data to compute a FOMAK."""


def pip_factor_for_price(sample_price: float) -> float:
    """Same JPY-vs-other heuristic already used elsewhere in this codebase
    (ui/ChartAnalysis.tsx's pipSize logic) — price > 20 implies a JPY-style pair
    (2 decimal pips) rather than a 4/5-decimal major."""
    return 100.0 if sample_price > 20 else 10000.0


def _bin_by_thresholds(val: float | None, thresholds: list[float]) -> int:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0
    for i, thr in enumerate(thresholds, start=1):
        if val < thr:
            return i
    return len(thresholds) + 1


def _candles_to_df(candles: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    df["datetime"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
    df = df.sort_values("datetime").reset_index(drop=True)
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    return df


def alignment_char(d_char: str, higher_dir: str) -> str:
    """Ported verbatim from FOMAKEngine._alignment_char."""
    if d_char == "U" and higher_dir == "U":
        return "S"
    if d_char == "D" and higher_dir == "U":
        return "O"
    if d_char == "N" and higher_dir == "U":
        return "U"
    if d_char == "U" and higher_dir == "D":
        return "O"
    if d_char == "D" and higher_dir == "D":
        return "S"
    if d_char == "N" and higher_dir == "D":
        return "D"
    if higher_dir == "N":
        return "S" if d_char == "N" else "N"
    return "N"


def _higher_timeframe_direction(higher_tf_candles: list[dict[str, Any]], pip_factor: float) -> str:
    if not higher_tf_candles or len(higher_tf_candles) < 2:
        return "N"
    hdf = _candles_to_df(higher_tf_candles)
    ema = hdf["close"].ewm(span=EMA_STATE_PERIOD, adjust=False).mean()
    ema_diff = ema.diff() * pip_factor
    last_diff = ema_diff.iloc[-1]
    if pd.isna(last_diff) or abs(last_diff) < EMA_MIN_MOVE_PIPS:
        return "N"
    return "U" if last_diff > 0 else "D"


def compute_fomak(
    window_candles: list[dict[str, Any]],
    warmup_candles: list[dict[str, Any]],
    higher_tf_candles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute one FOMAK code for `window_candles` (the block itself, oldest-first).

    `warmup_candles` are earlier same-timeframe candles ending exactly where
    `window_candles` begins — used only to give the rolling ATR series enough
    history to be meaningful once the window starts (never included in the
    block's own move/persistence/noise/impulse calculations).

    `higher_tf_candles` are candles at the higher timeframe (oldest-first,
    ending at/before the window's end) used for the alignment character.
    """
    if len(window_candles) < 2:
        raise FomakInputError("Need at least 2 candles in the window to compute a FOMAK.")

    all_candles = [*warmup_candles, *window_candles]
    df = _candles_to_df(all_candles)
    pip_factor = pip_factor_for_price(float(df["close"].iloc[-1]))

    pip_high = df["high"] * pip_factor
    pip_low = df["low"] * pip_factor
    pip_close = df["close"] * pip_factor
    prev_close = pip_close.shift(1)

    true_range = pd.concat(
        [pip_high - pip_low, (pip_high - prev_close).abs(), (pip_low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr_short = true_range.rolling(ATR_SHORT_PERIOD).mean()
    atr_long = true_range.rolling(ATR_LONG_PERIOD).mean()

    n = len(window_candles)
    block = df.iloc[-n:]
    block_atr_short = atr_short.iloc[-n:]
    block_atr_long = atr_long.iloc[-n:]

    atr_short_med = float(block_atr_short.median())
    atr_long_med = float(block_atr_long.median())
    if np.isnan(atr_short_med) or atr_short_med == 0 or np.isnan(atr_long_med) or atr_long_med == 0:
        raise FomakInputError(
            "Not enough warmup history to compute a stable ATR for this window — "
            "need more candles before the anchor."
        )

    o = float(block["open"].iloc[0])
    c = float(block["close"].iloc[-1])
    move_total_pips = (c - o) * pip_factor
    direction_sign = 1 if move_total_pips > 0 else (-1 if move_total_pips < 0 else 0)
    d_char = "U" if direction_sign > 0 else ("D" if direction_sign < 0 else "N")

    strength = abs(move_total_pips) / atr_short_med
    vola_ratio = atr_short_med / atr_long_med

    closes = block["close"].astype(float)
    moves = closes.diff().dropna()
    if len(moves) > 0:
        persist_score = float((moves > 0).sum() / len(moves))
        signs = np.sign(moves.values)
        noise_score = float((signs[1:] != signs[:-1]).sum() / (len(signs) - 1)) if len(signs) > 1 else 0.0
    else:
        persist_score = float("nan")
        noise_score = float("nan")

    impulse_score = float("nan")
    if len(closes) > IMPULSE_SHIFT:
        diff_shift = (closes - closes.shift(IMPULSE_SHIFT)).abs().dropna()
        if not diff_shift.empty:
            impulse_score = float(diff_shift.max() * pip_factor / atr_short_med)

    s_bin = _bin_by_thresholds(strength, BINS_STRENGTH)
    v_bin = _bin_by_thresholds(vola_ratio, BINS_VOLA)
    p_bin = _bin_by_thresholds(persist_score, BINS_PERSIST)
    i_bin = _bin_by_thresholds(impulse_score, BINS_IMPULSE)
    n_bin = _bin_by_thresholds(noise_score, BINS_NOISE)

    higher_dir = _higher_timeframe_direction(higher_tf_candles, pip_factor)
    a_char = alignment_char(d_char, higher_dir)

    fomak = f"{s_bin}{d_char}{v_bin}{p_bin}{i_bin}{n_bin}{a_char}"

    def _round_or_none(val: float) -> float | None:
        return None if (val is None or (isinstance(val, float) and np.isnan(val))) else round(val, 4)

    return {
        "fomak": fomak,
        "direction": d_char,
        "higher_timeframe_direction": higher_dir,
        "raw_values": {
            "strength": _round_or_none(strength),
            "vola_ratio": _round_or_none(vola_ratio),
            "persist_score": _round_or_none(persist_score),
            "noise_score": _round_or_none(noise_score),
            "impulse_score": _round_or_none(impulse_score),
            "atr_short": _round_or_none(atr_short_med),
            "atr_long": _round_or_none(atr_long_med),
            "S_bin": s_bin, "V_bin": v_bin, "P_bin": p_bin, "I_bin": i_bin, "N_bin": n_bin,
        },
    }

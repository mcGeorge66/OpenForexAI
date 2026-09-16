"""Market keys stored beside the candles: the FOMAK as a property of the series.

The FOMAK became business-critical the moment it started steering which prompt
an agent gets. A value that is recomputed on every question has three problems
this module removes:

  - It cannot be measured at scale. Asking the tool once per candle costs
    ~10 ms; a sweep over both pairs' history is 11 minutes of pure recompute,
    every time. Stored once, it is a table read.
  - There is no single truth. "The FOMAK the agent saw" and "the FOMAK I
    recomputed" were two different things for 41 of 103 trades until the
    forming candle was excluded. One stored value per closed candle ends that
    question for good.
  - It is not available historically. Only 103 of 772 trades carried one,
    because the tool was added late.

**The parameter set is part of the key.** A FOMAK means nothing without the
window length, the higher timeframe and the ATR periods it was computed with —
and it silently means something *else* after the bin thresholds are
recalibrated, which has already happened once in this project. `param_set`
therefore includes a checksum over those thresholds: re-tuning them produces
new rows next to the old ones instead of quietly invalidating everything
stored. Two values can always be compared, or explicitly not.

One table per broker and pair, mirroring the candle tables — with several pairs
across several brokers a shared table would grow into the wrong shape, and the
cross-pair query is a cheap UNION (see `read_keys_across`).
"""
from __future__ import annotations

import hashlib
from typing import Any

from openforexai.tools.market import _fomak_core as fomak_core

# Bumped by hand only when the stored *shape* changes (new column, different
# meaning of an existing one) — not for threshold changes, which the checksum
# below already separates.
SCHEMA_VERSION = 1


def bins_checksum() -> str:
    """Short checksum over everything that silently changes what a FOMAK means.

    The bin edges are module constants, so a recalibration would otherwise
    leave every stored value looking valid while meaning something different.
    """
    payload = repr([
        fomak_core.BINS_STRENGTH,
        fomak_core.BINS_VOLA,
        fomak_core.BINS_PERSIST,
        fomak_core.BINS_IMPULSE,
        fomak_core.BINS_NOISE,
        fomak_core.IMPULSE_SHIFT,
        fomak_core.EMA_STATE_PERIOD,
        fomak_core.EMA_MIN_MOVE_PIPS,
    ])
    return hashlib.sha1(payload.encode()).hexdigest()[:8]


def param_set(
    *,
    timeframe: str,
    lookback_candles: int,
    higher_timeframe: str,
    atr_short_period: int = fomak_core.ATR_SHORT_PERIOD,
    atr_long_period: int = fomak_core.ATR_LONG_PERIOD,
) -> str:
    """Everything that changes the resulting code, as one comparable string.

    Example: ``M5-24-M30-14-50-b3f9a1c2``. Readable on purpose — a stored row
    should say what it is without a lookup table.
    """
    return (
        f"{timeframe.upper()}-{int(lookback_candles)}-{higher_timeframe.upper()}"
        f"-{int(atr_short_period)}-{int(atr_long_period)}-{bins_checksum()}"
    )


def keys_table(broker_name: str, pair: str, timeframe: str) -> str:
    """`OXS_T_USDJPY_M5_keys`, beside `OXS_T_USDJPY_M5`."""
    def _sanitize(s: str) -> str:
        return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in s)
    return (
        f"{_sanitize(broker_name.upper())}_{_sanitize(pair.upper())}"
        f"_{_sanitize(timeframe.upper())}_keys"
    )


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    timestamp    TEXT NOT NULL,
    param_set    TEXT NOT NULL,
    fomak        TEXT NOT NULL,
    fomak_text   TEXT,
    fopok        TEXT,
    fopok_text   TEXT,
    raw_values   TEXT,
    computed_at  TEXT NOT NULL,
    PRIMARY KEY (timestamp, param_set)
);
"""

COLUMNS = (
    "timestamp", "param_set", "fomak", "fomak_text",
    "fopok", "fopok_text", "raw_values", "computed_at",
)
INSERT_SQL = (
    "INSERT OR REPLACE INTO {table} (" + ", ".join(COLUMNS) + ") "
    "VALUES (" + ",".join("?" * len(COLUMNS)) + ")"
)


def row_for(
    *,
    timestamp: str,
    params: str,
    fomak: str,
    raw_values: dict[str, Any] | None,
    computed_at: str,
    fopok: str | None = None,
    fopok_raw: dict[str, Any] | None = None,
) -> tuple:
    """One row in the order COLUMNS declares.

    The written-out forms are stored, not just the codes. The similarity search
    works on text and the agent reads text — recomputing a sentence that never
    changes for a given code would be work done a million times for nothing.
    They are derived here, so a code and its text can never drift apart.
    """
    import json
    from openforexai.tools.market._fomak_text import explain_fomak
    from openforexai.tools.market._fopok_core import explain_fopok

    try:
        fomak_text = explain_fomak(fomak) if fomak else None
    except Exception:
        fomak_text = None
    try:
        fopok_text = explain_fopok(fopok, fopok_raw) if fopok else None
    except Exception:
        fopok_text = None

    return (
        timestamp,
        params,
        fomak,
        fomak_text,
        fopok,
        fopok_text,
        json.dumps(raw_values, separators=(",", ":")) if raw_values else None,
        computed_at,
    )

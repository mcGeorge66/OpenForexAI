"""Tool: compute_fomak — deterministic market-character fingerprint for a candle
window, ending at an anchor timestamp (or "now" if omitted). See
FOMAK_101-2.pdf for the full derivation; _fomak_core.py/_fomak_text.py are
ported from the original fomak_engine5.py/fomak_analyse.py.

Registered as a normal tool, which means it works two ways for free:
- as a tool_blocks entry in a snapshot profile (deterministic, no LLM tool-call
  needed — this is how AA's decision-only cycle gets it)
- as a live tool call for any agent that has it in allowed_tools (EA, the Chart
  Analysis assistant, ...)
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import logging

from openforexai.data.market_keys import param_set as market_key_param_set
from openforexai.tools.base import BaseTool, ToolContext, fetch_candles
_log = logging.getLogger(__name__)

from openforexai.tools.market._fomak_core import (
    EMA_STATE_PERIOD,
    WARMUP_CANDLES,
    warmup_for,
    FomakInputError,
    compute_fomak,
)
from openforexai.tools.market._fomak_text import explain_fomak, interpret_fomak

def _truthy(value: Any) -> bool:
    """tool_blocks configs sometimes quote booleans as strings (matching the existing
    convention of quoting numbers like "count": "30") — tolerate that."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "0")
    return bool(value)


_VALID_TIMEFRAMES = ["M5", "M15", "M30", "H1", "H4", "D1"]
_NEXT_HIGHER_TIMEFRAME = {
    tf: (_VALID_TIMEFRAMES[i + 1] if i + 1 < len(_VALID_TIMEFRAMES) else tf)
    for i, tf in enumerate(_VALID_TIMEFRAMES)
}


class ComputeFomakTool(BaseTool):
    name = "compute_fomak"
    description = (
        "Compute a FOMAK code — a compact, deterministic fingerprint of market character "
        "(trend strength, direction, volatility, persistence, impulse, and alignment "
        "with the higher timeframe trend) for a window of candles ending at an anchor "
        "timestamp (or now, if omitted). Same formula every time — use it to reliably "
        "recognize 'have we seen this market character before' (e.g. as a pattern_key for "
        "semantic_memory), not as a trading signal itself. Returns the code always; raw "
        "values (including a noise_score not encoded in the code itself) and a "
        "plain-language explanation are optional."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pair": {"type": "string", "description": "Currency pair, e.g. EURUSD. Defaults to the current pair."},
            "timeframe": {
                "type": "string",
                "enum": _VALID_TIMEFRAMES,
                "description": "Timeframe of the candle window itself.",
            },
            "lookback_candles": {
                "type": "integer",
                "minimum": 3,
                "maximum": 200,
                "description": "How many candles (at 'timeframe') the window covers, counting back from the anchor.",
            },
            "anchor": {
                "type": "string",
                "description": "Optional ISO8601 timestamp — the window ends here. Omit for 'now'.",
            },
            "higher_timeframe": {
                "type": "string",
                "enum": _VALID_TIMEFRAMES,
                "description": "Timeframe used for the alignment character (A). Omit to auto-use the next higher timeframe above 'timeframe'.",
            },
            "include_forming_candle": {
                "type": "boolean",
                "description": (
                    "Include the candle currently being built. Default false, and it "
                    "should stay false for anything whose result is stored, compared or "
                    "replayed: a forming candle grows tick by tick, so the same moment "
                    "yields a different key when asked twice. Set it only for an "
                    "on-the-fly look at the bar in progress."
                ),
            },
            "include_raw_values": {
                "type": "boolean",
                "description": "Include the underlying continuous values (strength, vola_ratio, persist_score, ...) and bins. Default false.",
            },
            "atr_short_period": {
                "type": "integer",
                "description": (
                    "ATR period the move is measured against (default 14). Changing it moves "
                    "the strength and volatility distributions, so the binning thresholds — "
                    "calibrated from percentiles of ~12,000 real windows — no longer hold and "
                    "have to be re-derived."
                ),
                "minimum": 2,
                "maximum": 200,
                "default": 14,
            },
            "atr_long_period": {
                "type": "integer",
                "description": (
                    "The slower ATR the faster one is compared against for the volatility "
                    "ratio (default 50). Same caveat as atr_short_period."
                ),
                "minimum": 3,
                "maximum": 500,
                "default": 50,
            },
            "include_explanation": {
                "type": "boolean",
                "description": "Include a plain-language explanation of the code. Default false.",
            },
        },
        "required": ["timeframe", "lookback_candles"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        timeframe = str(arguments.get("timeframe", "")).upper()
        if timeframe not in _VALID_TIMEFRAMES:
            return {"error": f"Invalid timeframe {timeframe!r}. Must be one of: {', '.join(_VALID_TIMEFRAMES)}"}

        try:
            lookback_candles = int(arguments.get("lookback_candles"))
        except (TypeError, ValueError):
            return {"error": "Argument 'lookback_candles' is required and must be an integer >= 3."}
        if lookback_candles < 3:
            return {"error": "Argument 'lookback_candles' is required and must be an integer >= 3."}

        higher_timeframe = str(arguments.get("higher_timeframe") or "").upper() or _NEXT_HIGHER_TIMEFRAME[timeframe]
        if higher_timeframe not in _VALID_TIMEFRAMES:
            return {"error": f"Invalid higher_timeframe {higher_timeframe!r}."}

        anchor = str(arguments.get("anchor") or "").strip() or None
        pair = str(arguments.get("pair") or context.pair or "").upper()
        if not pair:
            return {"error": "No 'pair' given and none set in the current context."}
        if not context.broker_name:
            return {"error": "broker_name not set in tool context."}

        include_forming = _truthy(arguments.get("include_forming_candle"))
        want_raw = _truthy(arguments.get("include_raw_values"))
        want_explanation = _truthy(arguments.get("include_explanation"))
        atr_short_period = int(arguments.get("atr_short_period") or 14)
        atr_long_period = int(arguments.get("atr_long_period") or 50)
        # The warmup follows the longer period — otherwise the rolling ATR has
        # not settled by the time the window starts.
        total_needed = lookback_candles + warmup_for(atr_short_period, atr_long_period)

        # Stored first. One key costs ~10 ms to compute and the DataContainer
        # already writes one per closed candle, so recomputing it on every
        # question is work done for nothing — and, worse, a second opinion
        # where there should be one answer.
        params = market_key_param_set(
            timeframe=timeframe,
            lookback_candles=lookback_candles,
            higher_timeframe=higher_timeframe,
            atr_short_period=atr_short_period,
            atr_long_period=atr_long_period,
        )
        if not include_forming:
            stored = await _stored_key(context, pair, timeframe, params, anchor)
            if stored:
                return _response_from_stored(
                    stored, pair=pair, timeframe=timeframe,
                    higher_timeframe=higher_timeframe,
                    lookback_candles=lookback_candles,
                    want_raw=want_raw, want_explanation=want_explanation,
                )
        try:
            candles = await fetch_candles(
                context, timeframe, total_needed, pair=pair, start=anchor,
                include_forming=include_forming,
            )
            higher_tf_candles = await fetch_candles(
                context, higher_timeframe, EMA_STATE_PERIOD + 10, pair=pair, start=anchor,
                include_forming=include_forming,
            )
        except RuntimeError as exc:
            return {"error": str(exc)}

        if len(candles) < lookback_candles + 1:
            return {
                "error": (
                    f"Not enough candle history available: got {len(candles)}, need at least "
                    f"{lookback_candles + 1} (lookback + warmup) at {timeframe} ending "
                    f"{anchor or 'now'}."
                )
            }

        warmup_candles = candles[:-lookback_candles]
        window_candles = candles[-lookback_candles:]

        try:
            result = compute_fomak(
                window_candles, warmup_candles, higher_tf_candles,
                atr_short_period=atr_short_period,
                atr_long_period=atr_long_period,
            )
        except FomakInputError as exc:
            return {"error": str(exc)}

        response: dict[str, Any] = {
            "fomak": result["fomak"],
            "pair": pair,
            "timeframe": timeframe,
            "higher_timeframe": higher_timeframe,
            "lookback_candles": lookback_candles,
            "anchor": anchor or datetime.now(UTC).isoformat(),
            "includes_forming_candle": include_forming,
        }
        if not include_forming:
            await _store_key(
                context, pair, timeframe, params,
                window_candles[-1]["timestamp"], result,
            )

        if want_raw:
            response["direction"] = result["direction"]
            response["higher_timeframe_direction"] = result["higher_timeframe_direction"]
            response["raw_values"] = result["raw_values"]
        if want_explanation:
            response["explanation"] = (
                f"{explain_fomak(result['fomak'])}\n\n{interpret_fomak(result['fomak'])}"
            )
        return response


# ── The stored key as a cache ──────────────────────────────────────────────

async def _stored_key(
    context: ToolContext, pair: str, timeframe: str, params: str, anchor: str | None,
) -> dict[str, Any] | None:
    """The row in force at *anchor*, or None — never an exception.

    A missing repository, an older one without the method, a timeout: all of
    them mean "compute it yourself", never "fail the analysis". The value is
    derived and reproducible, so falling back costs time and nothing else.
    """
    from openforexai.tools.base import repo_request

    try:
        row = await repo_request(context, "get_market_key_at", {
            "broker_name": context.broker_name,
            "pair": pair,
            "timeframe": timeframe,
            "param_set": params,
            "at": anchor,
        }, timeout=5.0)
    except Exception:
        return None
    return row if isinstance(row, dict) and row.get("fomak") else None


async def _store_key(
    context: ToolContext, pair: str, timeframe: str, params: str,
    last_candle_timestamp: str, result: dict[str, Any],
) -> None:
    """Keep what was just computed, stamped the way the maintenance stamps it.

    The stamp is the close time of the newest candle in the window — the
    moment the key becomes valid — not the anchor that was asked for. An
    anchor mid-candle and one at its close describe the same market and must
    not produce two rows.
    """
    from datetime import datetime, timedelta

    from openforexai.data.market_keys import row_for
    from openforexai.tools.base import TIMEFRAME_MINUTES, repo_request

    minutes = TIMEFRAME_MINUTES.get(timeframe.upper())
    if not minutes:
        return
    try:
        opened = datetime.fromisoformat(str(last_candle_timestamp))
        valid_from = (opened + timedelta(minutes=minutes)).isoformat()
        await repo_request(context, "save_market_keys", {
            "broker_name": context.broker_name,
            "pair": pair,
            "timeframe": timeframe,
            "rows": [list(row_for(
                timestamp=valid_from, params=params, fomak=result["fomak"],
                raw_values=result.get("raw_values"),
                computed_at=datetime.now(UTC).isoformat(),
            ))],
        }, timeout=5.0)
    except Exception as exc:
        _log.debug("Market key not stored: %s", exc)


def _response_from_stored(
    row: dict[str, Any], *, pair: str, timeframe: str, higher_timeframe: str,
    lookback_candles: int, want_raw: bool, want_explanation: bool,
) -> dict[str, Any]:
    """Same shape as a freshly computed answer, so a caller cannot tell — and
    does not need to — whether it was read or computed. `from_store` says so
    anyway, because a cached answer that hides that it is cached is the kind
    of thing nobody can debug later."""
    import json

    response: dict[str, Any] = {
        "fomak": row["fomak"],
        "pair": pair,
        "timeframe": timeframe,
        "higher_timeframe": higher_timeframe,
        "lookback_candles": lookback_candles,
        "anchor": row["timestamp"],
        "includes_forming_candle": False,
        "from_store": True,
    }
    if want_raw and row.get("raw_values"):
        try:
            response["raw_values"] = json.loads(row["raw_values"])
        except (TypeError, ValueError):
            pass
    if want_explanation:
        response["explanation"] = row.get("fomak_text") or explain_fomak(row["fomak"])
    return response

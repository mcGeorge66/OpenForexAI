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

from openforexai.data.container import DATA_CONTAINER_ID
from openforexai.models.messaging import EventType
from openforexai.tools.base import BaseTool, ToolContext, bus_request
from openforexai.tools.market._fomak_core import (
    EMA_STATE_PERIOD,
    WARMUP_CANDLES,
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
        "(trend strength, direction, volatility, persistence, impulse, noise, and alignment "
        "with the higher timeframe trend) for a window of candles ending at an anchor "
        "timestamp (or now, if omitted). Same formula every time — use it to reliably "
        "recognize 'have we seen this market character before' (e.g. as a pattern_key for "
        "semantic_memory), not as a trading signal itself. Returns the code always; raw "
        "values and a plain-language explanation are optional."
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
            "include_raw_values": {
                "type": "boolean",
                "description": "Include the underlying continuous values (strength, vola_ratio, persist_score, ...) and bins. Default false.",
            },
            "include_explanation": {
                "type": "boolean",
                "description": "Include a plain-language explanation of the code. Default false.",
            },
            "lang": {
                "type": "string",
                "enum": ["de", "en"],
                "description": "Language for the explanation, if requested. Default 'de'.",
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

        total_needed = lookback_candles + WARMUP_CANDLES
        try:
            candles = await self._fetch_candles(context, pair, timeframe, total_needed, anchor)
            higher_tf_candles = await self._fetch_candles(
                context, pair, higher_timeframe, EMA_STATE_PERIOD + 10, anchor,
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
            result = compute_fomak(window_candles, warmup_candles, higher_tf_candles)
        except FomakInputError as exc:
            return {"error": str(exc)}

        response: dict[str, Any] = {
            "fomak": result["fomak"],
            "pair": pair,
            "timeframe": timeframe,
            "higher_timeframe": higher_timeframe,
            "lookback_candles": lookback_candles,
            "anchor": anchor or datetime.now(UTC).isoformat(),
        }
        if _truthy(arguments.get("include_raw_values")):
            response["direction"] = result["direction"]
            response["higher_timeframe_direction"] = result["higher_timeframe_direction"]
            response["raw_values"] = result["raw_values"]
        if _truthy(arguments.get("include_explanation")):
            lang = arguments.get("lang")
            response["explanation"] = (
                f"{explain_fomak(result['fomak'], lang)}\n\n{interpret_fomak(result['fomak'], lang)}"
            )
        return response

    @staticmethod
    async def _fetch_candles(
        context: ToolContext, pair: str, timeframe: str, count: int, start: str | None,
    ) -> list[dict[str, Any]]:
        response = await bus_request(
            context=context,
            event_type=EventType.CANDLES_REQUEST,
            target_id=DATA_CONTAINER_ID,
            instrument=pair,
            payload={
                "broker_name": context.broker_name,
                "timeframe": timeframe,
                "limit": count,
                **({"start": start} if start else {}),
            },
        )
        if response.get("error"):
            raise RuntimeError(f"DataContainer error: {response['error']}")
        candles = response.get("candles", [])
        return candles[-count:]

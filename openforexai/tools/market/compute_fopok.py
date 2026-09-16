"""compute_fopok — the position key, as a snapshot-callable tool.

Self-contained on purpose: snapshot tool blocks run in parallel and cannot take
another block's output as an argument, so this fetches its own level structure
instead of expecting one. It does that by calling get_swing_levels rather than
re-implementing the clustering, touch_count and ATR that tool already provides.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.market._fopok_core import (
    FopokInputError,
    compute_fopok,
    explain_fopok,
)
from openforexai.tools.market.swing_levels import GetSwingLevelsTool


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class ComputeFopokTool(BaseTool):
    name = "compute_fopok"
    description = (
        "Compute a FOPOK code — a compact, deterministic fingerprint of where price stands "
        "in its level structure, the position counterpart to compute_fomak's movement "
        "fingerprint. Five letters: position in the corridor (Down/Middle/Up), corridor "
        "width in ATR (Tight/Normal/Wide), whether the barrier above and the one below are "
        "Fresh or Exhausted (how often they have been tested), and whether the higher "
        "timeframe is Aligned, has None of its own, or is in Conflict. Also returns the room "
        "to each barrier in ATR — the number a take-profit has to fit inside. Use it together "
        "with compute_fomak: the same movement at the upper edge of a tight corridor is a "
        "different situation from the same movement at a worn support."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {
                "type": "string",
                "description": "Broker short_name. Used by the Tool Executor to resolve broker context.",
            },
            "pair": {
                "type": "string",
                "description": "Currency pair, e.g. EURUSD. Used by the Tool Executor to resolve pair context.",
            },
            "timeframe": {
                "type": "string",
                "description": "Timeframe the level structure is read on. Default M15.",
                "enum": ["M5", "M15", "M30", "H1", "H4", "D1"],
                "default": "M15",
            },
            "higher_timeframe": {
                "type": "string",
                "description": "Timeframe for the wider view. Default H1.",
                "enum": ["M15", "M30", "H1", "H4", "D1"],
                "default": "H1",
            },
            "lookback": {
                "type": "integer",
                "description": "Candles to analyse for levels (default 100, max 500).",
                "minimum": 10,
                "maximum": 500,
                "default": 100,
            },
            "prominence": {
                "type": "number",
                "description": (
                    "Minimum swing prominence, passed through to get_swing_levels. 0.0 keeps "
                    "every local extreme — measured on 1647 real M15 windows that puts the "
                    "next level a median 0.33 ATR away, which is a wiggle rather than a zone."
                ),
                "minimum": 0.0,
                "default": 0.0,
            },
            "prominence_atr": {
                "type": "number",
                "description": (
                    "Minimum swing prominence in ATR, passed through to get_swing_levels. "
                    "Preferable to `prominence`, which is an absolute price distance and so "
                    "needs a different number for every pair. Around 0.25 gave the widest "
                    "usable corridors on real M15 windows."
                ),
                "minimum": 0.0,
                "default": 0.0,
            },
            "atr_period": {
                "type": "number",
                "description": (
                    "ATR period every distance is expressed in, passed through to "
                    "get_swing_levels. Default 14; the snapshot's own atr_m15 block uses 7, so "
                    "set them alike if the two are to be compared."
                ),
                "minimum": 2,
                "maximum": 200,
                "default": 14,
            },
            "include_explanation": {
                "type": "boolean",
                "description": "Include the plain-language reading of the code. Default false.",
            },
        },
        "required": ["timeframe"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        timeframe = str(arguments.get("timeframe") or "M15").upper()
        higher_timeframe = str(arguments.get("higher_timeframe") or "H1").upper()
        lookback = int(arguments.get("lookback") or 100)
        prominence = float(arguments.get("prominence") or 0.0)
        atr_period = int(arguments.get("atr_period") or 14)
        prominence_atr = float(arguments.get("prominence_atr") or 0.0)

        levels_tool = GetSwingLevelsTool()

        async def levels(tf: str) -> dict[str, Any]:
            result = await levels_tool.execute(
                {"timeframe": tf, "lookback": lookback, "prominence": prominence,
                 "prominence_atr": prominence_atr, "atr_period": atr_period},
                context,
            )
            if not isinstance(result, dict):
                raise FopokInputError(f"get_swing_levels returned no data for {tf}")
            return result

        own = await levels(timeframe)
        higher = await levels(higher_timeframe)

        atr = own.get("atr")
        try:
            result = compute_fopok(
                current_price=float(own["current_price"]),
                nearest_resistance=own.get("nearest_resistance"),
                nearest_support=own.get("nearest_support"),
                atr=float(atr) if atr else 0.0,
                higher_resistance=higher.get("nearest_resistance"),
                higher_support=higher.get("nearest_support"),
            )
        except (FopokInputError, KeyError, TypeError, ValueError) as exc:
            # A missing barrier is a normal state (price at the edge of the
            # analysed range), not a failure worth aborting a cycle for — it is
            # reported so a caller can see why there is no code.
            return {
                "fopok": None,
                "error": str(exc),
                "timeframe": timeframe,
                "higher_timeframe": higher_timeframe,
                "current_price": own.get("current_price"),
            }

        response = {
            "fopok": result["fopok"],
            "position": result["position"],
            "timeframe": timeframe,
            "higher_timeframe": higher_timeframe,
            "current_price": own.get("current_price"),
            "atr_period": atr_period,
            "raw_values": result["raw_values"],
        }
        if _truthy(arguments.get("include_explanation")):
            response["explanation"] = explain_fopok(result["fopok"], result["raw_values"])
        return response

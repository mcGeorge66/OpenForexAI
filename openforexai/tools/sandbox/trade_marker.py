"""Tool: trade_marker — sandbox-only chart annotation (Prompt Workbench).

Marks the opening or closing of a simulated trade on the chart. Start and end
are set with separate calls sharing the same ``trade_id``, so a trade can stay
open across multiple simulation steps; more than one trade can be open at
once. Resolves candle numbers via ``context.extra["candle_index_map"]`` and
appends a structured record to ``context.extra["workbench_annotations"]`` for
the endpoint to read back — pairing open/close records and computing candle
count / pips is done by the frontend, not here.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class TradeMarkerTool(BaseTool):
    name = "trade_marker"
    description = (
        "Sandbox tool (Prompt Workbench only): mark the opening or closing of a simulated "
        "trade on the chart. Call with action='open' when you decide to enter a position, "
        "and action='close' with the SAME trade_id later to close it - the chart will draw "
        "a line between the two candles showing candle count and pips. More than one trade "
        "can be open at once; use distinct trade_id values to tell them apart."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["open", "close"], "description": "Whether this call opens or closes the trade."},
            "trade_id": {"type": "string", "description": "Identifier you choose, reused for the matching close call."},
            "candle_number": {"type": "integer", "description": "Candle #N where the action happens."},
            "direction": {"type": "string", "enum": ["long", "short"], "description": "Required for action='open'."},
        },
        "required": ["action", "trade_id", "candle_number"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        index_map: dict[int, dict[str, Any]] = context.extra.get("candle_index_map", {})
        action = str(arguments.get("action", "")).strip().lower()
        trade_id = str(arguments.get("trade_id", "")).strip()
        if action not in ("open", "close"):
            return {"error": f"Invalid action {action!r}; must be 'open' or 'close'."}
        if not trade_id:
            return {"error": "trade_id is required."}
        try:
            candle_number = int(arguments.get("candle_number"))
        except (TypeError, ValueError):
            return {"error": "candle_number must be an integer."}

        candle = index_map.get(candle_number)
        if candle is None:
            return {"error": f"Candle number #{candle_number} not found in the currently visible window."}

        annotation: dict[str, Any] = {
            "kind": "trade",
            "action": action,
            "trade_id": trade_id,
            "candle_number": candle_number,
            "timestamp": candle["timestamp"],
            "price": candle["close"],
        }
        if action == "open":
            direction = str(arguments.get("direction", "")).strip().lower()
            if direction not in ("long", "short"):
                return {"error": "direction ('long' or 'short') is required for action='open'."}
            annotation["direction"] = direction

        annotations: list[dict[str, Any]] = context.extra.setdefault("workbench_annotations", [])
        annotations.append(annotation)
        return {"status": "ok", **annotation}

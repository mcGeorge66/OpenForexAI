"""Tool: trade_marker — sandbox-only chart annotation (Prompt Workbench).

Marks the opening or closing of a simulated trade on the chart. Start and end
are set with separate calls sharing the same ``trade_id``, so a trade can stay
open across multiple simulation steps; more than one trade can be open at
once. Resolves candle numbers via ``context.extra["candle_index_map"]`` and
appends a structured record to ``context.extra["workbench_annotations"]`` for
the endpoint to read back — pairing open/close records and computing candle
count / pips is done by the frontend, not here.

``op`` controls new/correct/remove, independent of ``action`` (open/close):
'new' records a leg (auto-assigning a short trade_id if opening without one),
'change' replaces a previously recorded leg's data in place (same trade_id
*and* action — a trade's open and close legs are corrected independently),
'delete' removes one leg — recorded in
``context.extra["workbench_removed_annotation_ids"]`` instead of
``workbench_annotations``.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.sandbox._annotation_ids import collect_used_ids, resolve_existing_id, resolve_new_id


class TradeMarkerTool(BaseTool):
    name = "trade_marker"
    description = (
        "Sandbox tool (Prompt Workbench only): mark the opening or closing of a simulated "
        "trade on the chart. Call with action='open' when you decide to enter a position, "
        "and action='close' with the SAME trade_id later to close it - the chart will draw "
        "a line between the two candles showing candle count and pips. More than one trade "
        "can be open at once; use distinct trade_id values to tell them apart. Use op='change' "
        "with the same trade_id AND action to correct a leg you recorded earlier (open and "
        "close are corrected independently), and op='delete' to remove one - look the "
        "trade_id up with get_annotation first if you don't remember it."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["new", "change", "delete"],
                "description": "'new' records this leg (default), 'change' replaces a previous leg with the "
                               "same trade_id+action, 'delete' removes it.",
            },
            "action": {"type": "string", "enum": ["open", "close"], "description": "Whether this call opens or closes the trade."},
            "trade_id": {
                "type": "string",
                "description": "At most 2 alphanumeric characters, e.g. 'T1'. Omit for op='new' with action='open' "
                               "to auto-assign one. Required otherwise (close must match the opening trade_id; "
                               "change/delete must match the leg you're correcting).",
            },
            "candle_number": {"type": "integer", "description": "Candle #N where the action happens."},
            "direction": {"type": "string", "enum": ["long", "short"], "description": "Required for action='open'."},
        },
        "required": ["action", "candle_number"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        op = str(arguments.get("op", "new")).strip().lower() or "new"
        if op not in ("new", "change", "delete"):
            return {"error": f"Invalid op {op!r}; must be 'new', 'change', or 'delete'."}

        action = str(arguments.get("action", "")).strip().lower()
        if action not in ("open", "close"):
            return {"error": f"Invalid action {action!r}; must be 'open' or 'close'."}

        used_ids = collect_used_ids(context.extra)
        trade_id_arg = str(arguments.get("trade_id", ""))

        if op == "delete":
            trade_id, error = resolve_existing_id(trade_id_arg, used_ids)
            if error:
                return {"error": error}
            context.extra.setdefault("workbench_removed_annotation_ids", []).append(
                {"kind": "trade", "trade_id": trade_id, "action": action},
            )
            return {"status": "ok", "op": "delete", "kind": "trade", "trade_id": trade_id, "action": action}

        if op == "change":
            trade_id, error = resolve_existing_id(trade_id_arg, used_ids)
            if error:
                return {"error": error}
        elif action == "open":
            trade_id, error = resolve_new_id(trade_id_arg, used_ids)
            if error:
                return {"error": error}
        else:  # op == "new", action == "close" — must reference the trade it's closing
            trade_id = trade_id_arg.strip().upper()
            if not trade_id:
                return {"error": "trade_id is required for action='close' (must match the trade_id used to open it)."}

        try:
            candle_number = int(arguments.get("candle_number"))
        except (TypeError, ValueError):
            return {"error": "candle_number must be an integer."}

        index_map: dict[int, dict[str, Any]] = context.extra.get("candle_index_map", {})
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
        return {"status": "ok", "op": op, **annotation}

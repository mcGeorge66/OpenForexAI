"""Tool: trade_marker — sandbox-only chart annotation (Prompt Workbench).

Marks the opening or closing of a simulated trade on the chart. Start and end
are set with separate calls sharing the same ``trade_id``, so a trade can stay
open across multiple simulation steps; more than one trade can be open at
once. Resolves candle numbers via ``context.extra["candle_index_map"]`` and
appends a structured record to ``context.extra["workbench_annotations"]`` for
the endpoint to read back — pairing open/close records and computing candle
count / pips is done by the frontend, not here.

Once a leg (open or close) has been recorded, its execution facts — candle,
direction, action — are permanent, mirroring a real broker fill that can't be
un-sent: ``op='change'`` may only update the free-text ``note``, never the
candle, direction, or which trade/action it belongs to. ``op='delete'`` on a
trade leg fails with an explanatory error by default; the Prompt Workbench's
Simulation tab has a "delete of trades accepted" checkbox (off by default)
that flips ``context.extra["allow_trade_delete"]`` to allow it when a session
genuinely needs to retract a mis-recorded leg. If FIFO is enabled for this
session (``context.extra["fifo_enabled"]``), closing a trade out of order —
while an older trade is still open — is rejected, mirroring brokers that
enforce first-in-first-out position closing.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.sandbox._annotation_ids import collect_used_ids, resolve_existing_id, resolve_new_id


def _all_trade_legs(context: ToolContext) -> list[dict[str, Any]]:
    existing = context.extra.get("existing_annotations", []) or []
    this_turn = context.extra.get("workbench_annotations", []) or []
    return [a for a in (*existing, *this_turn) if a.get("kind") == "trade"]


def _find_leg(legs: list[dict[str, Any]], trade_id: str, action: str) -> dict[str, Any] | None:
    for leg in reversed(legs):  # last recorded version wins if a note-only 'change' was applied
        if leg.get("trade_id") == trade_id and leg.get("action") == action:
            return leg
    return None


def _oldest_open_trade(legs: list[dict[str, Any]]) -> dict[str, Any] | None:
    opens = {leg["trade_id"]: leg for leg in legs if leg.get("action") == "open"}
    for leg in legs:
        if leg.get("action") == "close":
            opens.pop(leg.get("trade_id"), None)
    if not opens:
        return None
    return min(opens.values(), key=lambda leg: leg.get("candle_number", 0))


class TradeMarkerTool(BaseTool):
    name = "trade_marker"
    description = (
        "Sandbox tool (Prompt Workbench only): mark the opening or closing of a simulated "
        "trade on the chart. Call with action='open' when you decide to enter a position, "
        "and action='close' with the SAME trade_id later to close it - the chart will draw "
        "a line between the two candles showing candle count and pips. More than one trade "
        "can be open at once; use distinct trade_id values to tell them apart. Once a leg is "
        "recorded its candle/direction are final - like a real broker fill, it cannot be "
        "un-sent. op='delete' on a trade leg fails unless this session has explicitly enabled "
        "it (close it instead); op='change' with the same trade_id AND action may only update "
        "the free-text 'note', never the candle or direction. If FIFO is active for this "
        "session, you must close the oldest still-open trade before closing a newer one - look "
        "up open trades with get_annotation if you're unsure which is oldest."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["new", "change", "delete"],
                "description": "'new' records this leg (default). 'change' updates only the 'note' of a "
                               "previously recorded leg with the same trade_id+action - candle/direction "
                               "cannot be changed. 'delete' is rejected for trade legs unless this session "
                               "has explicitly enabled it - use action='close' instead where possible.",
            },
            "action": {"type": "string", "enum": ["open", "close"], "description": "Whether this call opens or closes the trade."},
            "trade_id": {
                "type": "string",
                "description": "At most 2 alphanumeric characters, e.g. 'T1'. Omit for op='new' with action='open' "
                               "to auto-assign one. Required otherwise (close must match the opening trade_id; "
                               "change must match the leg whose note you're updating).",
            },
            "candle_number": {"type": "integer", "description": "Candle #N where the action happens. Not used for op='change' (the original candle is kept)."},
            "direction": {"type": "string", "enum": ["long", "short"], "description": "Required for action='open' with op='new'."},
            "note": {"type": "string", "description": "Optional free-text note. The only field op='change' is allowed to update."},
        },
        "required": ["action"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        op = str(arguments.get("op", "new")).strip().lower() or "new"
        if op not in ("new", "change", "delete"):
            return {"error": f"Invalid op {op!r}; must be 'new', 'change', or 'delete'."}

        action = str(arguments.get("action", "")).strip().lower()
        if action not in ("open", "close"):
            return {"error": f"Invalid action {action!r}; must be 'open' or 'close'."}

        legs = _all_trade_legs(context)
        used_ids = collect_used_ids(context.extra)
        trade_id_arg = str(arguments.get("trade_id", ""))

        if op == "delete":
            if not context.extra.get("allow_trade_delete"):
                return {
                    "error": "A trade leg cannot be deleted once recorded - a real broker fill can't be "
                             "un-sent. If the trade is still open, use action='close' to close it instead. "
                             "(Deletion can be enabled for this session via the 'delete of trades accepted' "
                             "checkbox in the Simulation tab.)",
                }
            trade_id, error = resolve_existing_id(trade_id_arg, used_ids)
            if error:
                return {"error": error}
            if _find_leg(legs, trade_id, action) is None:
                return {"error": f"No recorded {action} leg for trade_id {trade_id!r} to delete."}
            context.extra.setdefault("workbench_removed_annotation_ids", []).append(
                {"kind": "trade", "trade_id": trade_id, "action": action},
            )
            return {"status": "ok", "op": "delete", "kind": "trade", "trade_id": trade_id, "action": action}

        if op == "change":
            trade_id, error = resolve_existing_id(trade_id_arg, used_ids)
            if error:
                return {"error": error}
            original = _find_leg(legs, trade_id, action)
            if original is None:
                return {"error": f"No recorded {action} leg for trade_id {trade_id!r} - use op='new' to record one."}
            note = str(arguments.get("note", "")).strip()
            if not note:
                return {"error": "op='change' on a trade leg may only update 'note' - provide a non-empty note."}
            annotation = {**original, "note": note}
            annotations: list[dict[str, Any]] = context.extra.setdefault("workbench_annotations", [])
            annotations.append(annotation)
            return {"status": "ok", "op": "change", **annotation}

        # op == 'new' from here on.
        if action == "open":
            trade_id, error = resolve_new_id(trade_id_arg, used_ids)
            if error:
                return {"error": error}
        else:  # action == 'close' — must reference the trade it's closing
            trade_id = trade_id_arg.strip().upper()
            if not trade_id:
                return {"error": "trade_id is required for action='close' (must match the trade_id used to open it)."}
            if context.extra.get("fifo_enabled"):
                oldest = _oldest_open_trade(legs)
                if oldest is not None and oldest.get("trade_id") != trade_id:
                    return {
                        "error": f"FIFO is active: trade {oldest['trade_id']!r} (opened at candle "
                                 f"#{oldest.get('candle_number')}) is the oldest still-open trade and must "
                                 f"be closed before {trade_id!r}.",
                    }

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
        note = str(arguments.get("note", "")).strip()
        if note:
            annotation["note"] = note
        if action == "open":
            direction = str(arguments.get("direction", "")).strip().lower()
            if direction not in ("long", "short"):
                return {"error": "direction ('long' or 'short') is required for action='open'."}
            annotation["direction"] = direction
        else:  # close — carry the direction over from the opening leg so it's visible standalone
            opening_leg = _find_leg(legs, trade_id, "open")
            if opening_leg is not None and opening_leg.get("direction"):
                annotation["direction"] = opening_leg["direction"]

        annotations: list[dict[str, Any]] = context.extra.setdefault("workbench_annotations", [])
        annotations.append(annotation)
        return {"status": "ok", "op": op, **annotation}

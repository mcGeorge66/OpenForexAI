"""Tool: candle_marker — sandbox-only chart annotation (Prompt Workbench).

Places a single arrow marker above or below one candle with a short text,
e.g. to point out a specific entry point the agent identified. Resolves the
candle number via ``context.extra["candle_index_map"]`` and appends a
structured record to ``context.extra["workbench_annotations"]``, same pattern
as zone_marker/trade_marker.

``op`` controls new/correct/remove: 'new' places a marker (auto-assigning a
short id if none given), 'change' replaces a previous marker's data in place
(same marker_id), 'delete' removes it — recorded in
``context.extra["workbench_removed_annotation_ids"]`` instead of
``workbench_annotations``.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.sandbox._annotation_ids import collect_used_ids, resolve_existing_id, resolve_new_id


class CandleMarkerTool(BaseTool):
    name = "candle_marker"
    description = (
        "Sandbox tool (Prompt Workbench only): mark a single candle on the chart with an "
        "arrow and a short text label, e.g. to point out a specific entry point, a "
        "breakout candle, or any other single moment you want to highlight. For marking a "
        "range use zone_marker instead; for a full trade with entry+exit use trade_marker. "
        "Use op='change' with the same marker_id to correct a marker you placed earlier, "
        "and op='delete' to remove one you decide was wrong - look the marker_id up with "
        "get_annotation first if you don't remember it."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["new", "change", "delete"],
                "description": "'new' places a marker (default), 'change' replaces a previous marker with the "
                               "same marker_id, 'delete' removes it.",
            },
            "candle_number": {"type": "integer", "description": "Candle #N to mark."},
            "position": {"type": "string", "enum": ["above", "below"], "description": "Whether the arrow sits above or below the candle."},
            "text": {"type": "string", "description": "Short label shown next to the arrow, e.g. 'Entry' or 'Breakout'."},
            "marker_id": {
                "type": "string",
                "description": "At most 2 alphanumeric characters, e.g. 'B3'. Omit for op='new' to auto-assign "
                               "one. Required for op='change'/'delete' — must match the marker_id you're correcting.",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        op = str(arguments.get("op", "new")).strip().lower() or "new"
        if op not in ("new", "change", "delete"):
            return {"error": f"Invalid op {op!r}; must be 'new', 'change', or 'delete'."}

        used_ids = collect_used_ids(context.extra)
        marker_id_arg = str(arguments.get("marker_id", ""))

        if op == "delete":
            marker_id, error = resolve_existing_id(marker_id_arg, used_ids)
            if error:
                return {"error": error}
            context.extra.setdefault("workbench_removed_annotation_ids", []).append({"kind": "candle_marker", "marker_id": marker_id})
            return {"status": "ok", "op": "delete", "kind": "candle_marker", "marker_id": marker_id}

        index_map: dict[int, dict[str, Any]] = context.extra.get("candle_index_map", {})
        try:
            candle_number = int(arguments.get("candle_number"))
        except (TypeError, ValueError):
            return {"error": "candle_number must be an integer."}
        position = str(arguments.get("position", "")).strip().lower()
        if position not in ("above", "below"):
            return {"error": f"Invalid position {position!r}; must be 'above' or 'below'."}
        text = str(arguments.get("text", "")).strip() or "Marker"

        if op == "change":
            marker_id, error = resolve_existing_id(marker_id_arg, used_ids)
        else:
            marker_id, error = resolve_new_id(marker_id_arg, used_ids)
        if error:
            return {"error": error}

        candle = index_map.get(candle_number)
        if candle is None:
            return {"error": f"Candle number #{candle_number} not found in the currently visible window."}

        annotation = {
            "kind": "candle_marker",
            "marker_id": marker_id,
            "candle_number": candle_number,
            "timestamp": candle["timestamp"],
            "position": position,
            "text": text,
        }
        annotations: list[dict[str, Any]] = context.extra.setdefault("workbench_annotations", [])
        annotations.append(annotation)
        return {"status": "ok", "op": op, **annotation}

"""Tool: candle_marker — sandbox-only chart annotation (Prompt Workbench).

Places a single arrow marker above or below one candle with a short text,
e.g. to point out a specific entry point the agent identified. Resolves the
candle number via ``context.extra["candle_index_map"]`` and appends a
structured record to ``context.extra["workbench_annotations"]``, same pattern
as zone_marker/trade_marker.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class CandleMarkerTool(BaseTool):
    name = "candle_marker"
    description = (
        "Sandbox tool (Prompt Workbench only): mark a single candle on the chart with an "
        "arrow and a short text label, e.g. to point out a specific entry point, a "
        "breakout candle, or any other single moment you want to highlight. For marking a "
        "range use zone_marker instead; for a full trade with entry+exit use trade_marker."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "candle_number": {"type": "integer", "description": "Candle #N to mark."},
            "position": {"type": "string", "enum": ["above", "below"], "description": "Whether the arrow sits above or below the candle."},
            "text": {"type": "string", "description": "Short label shown next to the arrow, e.g. 'Entry' or 'Breakout'."},
            "marker_id": {"type": "string", "description": "Optional identifier to update/replace a previous marker with the same id."},
        },
        "required": ["candle_number", "position", "text"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        index_map: dict[int, dict[str, Any]] = context.extra.get("candle_index_map", {})
        try:
            candle_number = int(arguments.get("candle_number"))
        except (TypeError, ValueError):
            return {"error": "candle_number must be an integer."}
        position = str(arguments.get("position", "")).strip().lower()
        if position not in ("above", "below"):
            return {"error": f"Invalid position {position!r}; must be 'above' or 'below'."}
        text = str(arguments.get("text", "")).strip() or "Marker"
        marker_id = str(arguments.get("marker_id", "")).strip() or f"marker_{candle_number}"

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
        return {"status": "ok", **annotation}

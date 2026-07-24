"""Tool: zone_marker — sandbox-only chart annotation (Prompt Workbench).

Draws a labelled, semi-transparent zone/box on the chart spanning a range of
candles. Resolves candle numbers via ``context.extra["candle_index_map"]``
(populated per-request by the Prompt Workbench endpoint) and appends a
structured record to ``context.extra["workbench_annotations"]``, which the
endpoint reads back after the run completes and returns to the frontend for
rendering — the chart itself is never touched from here.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class ZoneMarkerTool(BaseTool):
    name = "zone_marker"
    description = (
        "Sandbox tool (Prompt Workbench only): draw a labelled, semi-transparent zone "
        "on the chart spanning a range of candles - e.g. to mark a trend, a support/"
        "resistance area, or a consolidation range you identified. Candle numbers are "
        "the #N labels shown with the loaded candle data (#1 = newest .. #total = oldest)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "start_candle_number": {"type": "integer", "description": "Candle #N where the zone starts."},
            "end_candle_number": {"type": "integer", "description": "Candle #N where the zone ends."},
            "heading": {"type": "string", "description": "Short label shown on the zone, e.g. 'Uptrend' or 'Resistance'."},
            "zone_id": {"type": "string", "description": "Optional identifier to update/replace a previous zone with the same id."},
        },
        "required": ["start_candle_number", "end_candle_number", "heading"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        index_map: dict[int, dict[str, Any]] = context.extra.get("candle_index_map", {})
        try:
            start_number = int(arguments.get("start_candle_number"))
            end_number = int(arguments.get("end_candle_number"))
        except (TypeError, ValueError):
            return {"error": "start_candle_number and end_candle_number must be integers."}
        heading = str(arguments.get("heading", "")).strip() or "Zone"
        zone_id = str(arguments.get("zone_id", "")).strip() or f"zone_{start_number}_{end_number}"

        start_candle = index_map.get(start_number)
        end_candle = index_map.get(end_number)
        if start_candle is None or end_candle is None:
            return {
                "error": f"Candle number(s) not found in the currently visible window: "
                         f"start=#{start_number} end=#{end_number}.",
            }

        annotation = {
            "kind": "zone",
            "zone_id": zone_id,
            "heading": heading,
            "start_candle_number": start_number,
            "end_candle_number": end_number,
            "start_timestamp": start_candle["timestamp"],
            "end_timestamp": end_candle["timestamp"],
        }
        annotations: list[dict[str, Any]] = context.extra.setdefault("workbench_annotations", [])
        annotations.append(annotation)
        return {"status": "ok", **annotation}

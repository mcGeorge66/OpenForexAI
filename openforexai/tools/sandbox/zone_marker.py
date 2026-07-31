"""Tool: zone_marker — sandbox-only chart annotation (Prompt Workbench).

Draws a labelled, semi-transparent zone/box on the chart spanning a range of
candles. Resolves candle numbers via ``context.extra["candle_index_map"]``
(populated per-request by the Prompt Workbench endpoint) and appends a
structured record to ``context.extra["workbench_annotations"]``, which the
endpoint reads back after the run completes and returns to the frontend for
rendering — the chart itself is never touched from here.

``op`` controls new/correct/remove: 'new' creates a zone (auto-assigning a
short id if none given), 'change' replaces a previous zone's data in place
(same zone_id), 'delete' removes it — recorded in
``context.extra["workbench_removed_annotation_ids"]`` instead of
``workbench_annotations``.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.sandbox._annotation_ids import collect_used_ids, resolve_existing_id, resolve_new_id


class ZoneMarkerTool(BaseTool):
    name = "zone_marker"
    description = (
        "Sandbox tool (Prompt Workbench only): draw a labelled, semi-transparent zone "
        "on the chart spanning a range of candles - e.g. to mark a trend, a support/"
        "resistance area, or a consolidation range you identified. Candle numbers are "
        "the #N labels shown with the loaded candle data (#1 = newest .. #total = oldest). "
        "Use op='change' with the same zone_id to correct a zone you drew earlier (e.g. wrong "
        "range or heading), and op='delete' to remove one you decide was wrong - look the "
        "zone_id up with get_annotation first if you don't remember it."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["new", "change", "delete"],
                "description": "'new' draws a zone (default), 'change' replaces a previous zone with the "
                               "same zone_id, 'delete' removes it.",
            },
            "start_candle_number": {"type": "integer", "description": "Candle #N where the zone starts."},
            "end_candle_number": {"type": "integer", "description": "Candle #N where the zone ends."},
            "heading": {"type": "string", "description": "Short label shown on the zone, e.g. 'Uptrend' or 'Resistance'."},
            "zone_id": {
                "type": "string",
                "description": "At most 2 alphanumeric characters, e.g. 'A1'. Omit for op='new' to auto-assign "
                               "one. Required for op='change'/'delete' — must match the zone_id you're correcting.",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        op = str(arguments.get("op", "new")).strip().lower() or "new"
        if op not in ("new", "change", "delete"):
            return {"error": f"Invalid op {op!r}; must be 'new', 'change', or 'delete'."}

        used_ids = collect_used_ids(context.extra)
        zone_id_arg = str(arguments.get("zone_id", ""))

        if op == "delete":
            zone_id, error = resolve_existing_id(zone_id_arg, used_ids)
            if error:
                return {"error": error}
            context.extra.setdefault("workbench_removed_annotation_ids", []).append({"kind": "zone", "zone_id": zone_id})
            return {"status": "ok", "op": "delete", "kind": "zone", "zone_id": zone_id}

        index_map: dict[int, dict[str, Any]] = context.extra.get("candle_index_map", {})
        try:
            start_number = int(arguments.get("start_candle_number"))
            end_number = int(arguments.get("end_candle_number"))
        except (TypeError, ValueError):
            return {"error": "start_candle_number and end_candle_number must be integers."}
        heading = str(arguments.get("heading", "")).strip() or "Zone"

        if op == "change":
            zone_id, error = resolve_existing_id(zone_id_arg, used_ids)
        else:
            zone_id, error = resolve_new_id(zone_id_arg, used_ids)
        if error:
            return {"error": error}

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
        return {"status": "ok", "op": op, **annotation}

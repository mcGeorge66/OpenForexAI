"""Tool: get_annotation — sandbox-only lookup (Prompt Workbench).

Read-side counterpart to zone_marker/trade_marker/candle_marker: lets the
agent look up markings it (or a prior turn) already placed, plus the real
candles around them, so a follow-up question like "why did you mark T2?" can
be answered from actual recorded facts instead of confabulating from memory.

The backend is stateless across requests — ``context.extra["existing_annotations"]``
is populated per-request from ``PromptWorkbenchChatRequest.existing_annotations``,
which the frontend fills from the annotations it has already accumulated
client-side (see PromptWorkbench.tsx).
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


def _annotation_id(annotation: dict[str, Any]) -> str | None:
    kind = annotation.get("kind")
    if kind == "zone":
        return annotation.get("zone_id")
    if kind == "trade":
        return annotation.get("trade_id")
    if kind == "candle_marker":
        return annotation.get("marker_id")
    return None


def _candle_range(annotation: dict[str, Any]) -> tuple[int, int] | None:
    kind = annotation.get("kind")
    if kind == "zone":
        numbers = [annotation.get("start_candle_number"), annotation.get("end_candle_number")]
    elif kind in ("trade", "candle_marker"):
        numbers = [annotation.get("candle_number")]
    else:
        numbers = []
    numbers = [n for n in numbers if isinstance(n, int)]
    return (min(numbers), max(numbers)) if numbers else None


class GetAnnotationTool(BaseTool):
    name = "get_annotation"
    description = (
        "Sandbox tool (Prompt Workbench only): look up chart markings you (or an earlier "
        "turn) placed with zone_marker/trade_marker/candle_marker, plus the real candles "
        "around them. Use this before explaining or justifying a past marking, instead of "
        "relying on memory. Omit all arguments to get every marking; pass annotation_id to "
        "get one specific marking (matches trade_id, zone_id, or marker_id); pass "
        "start_candle_number/end_candle_number to get every marking that falls within that "
        "candle range."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "annotation_id": {"type": "string", "description": "Matches trade_id, zone_id, or marker_id. Takes priority over the candle range."},
            "start_candle_number": {"type": "integer", "description": "With end_candle_number: return every marking overlapping this candle range."},
            "end_candle_number": {"type": "integer", "description": "See start_candle_number."},
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        existing: list[dict[str, Any]] = context.extra.get("existing_annotations", [])
        index_map: dict[int, dict[str, Any]] = context.extra.get("candle_index_map", {})

        annotation_id = str(arguments.get("annotation_id", "")).strip()
        start = arguments.get("start_candle_number")
        end = arguments.get("end_candle_number")

        if annotation_id:
            matches = [a for a in existing if _annotation_id(a) == annotation_id]
        elif isinstance(start, int) and isinstance(end, int):
            lo, hi = min(start, end), max(start, end)
            matches = []
            for a in existing:
                rng = _candle_range(a)
                if rng and rng[0] <= hi and rng[1] >= lo:
                    matches.append(a)
        else:
            matches = list(existing)

        results = []
        for a in matches:
            rng = _candle_range(a)
            nearby_candles: list[dict[str, Any]] = []
            if rng is not None:
                lo, hi = rng
                pad = 0 if a.get("kind") == "zone" else 3
                for number in range(lo - pad, hi + pad + 1):
                    candle = index_map.get(number)
                    if candle is not None:
                        nearby_candles.append({"candle_number": number, **candle})
                nearby_candles.sort(key=lambda c: c["candle_number"], reverse=True)
            results.append({"annotation": a, "nearby_candles": nearby_candles})

        return {"found": len(results), "annotations": results}

"""Tool: get_open_positions — retrieve open positions via broker adapter bus request."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from openforexai.models.messaging import EventType
from openforexai.tools.base import BaseTool, ToolContext, bus_request


def _broker_adapter_id(broker_name: str, pair: str) -> str:
    b = broker_name.upper().ljust(5, "_")[:5]
    p = pair.upper().ljust(6, "_")[:6]
    return f"{b}-{p}-AD-ADPT"


class GetOpenPositionsTool(BaseTool):
    name = "get_open_positions"
    description = (
        "Retrieve all currently open positions for this broker. "
        "Returns pair, direction, units, entry price, current P&L, "
        "stop-loss and take-profit levels. "
        "Use to assess current exposure before making new trade decisions."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {"type": "string", "description": "Broker short_name or module name."},
            "pair": {"type": "string", "description": "Optional currency pair filter."},
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")
        requested_pair = str(arguments.get("pair") or "").strip().upper() or None
        routing_pair = context.pair or "ALL___"

        response = await bus_request(
            context=context,
            event_type=EventType.POSITIONS_REQUEST,
            target_id=_broker_adapter_id(context.broker_name, routing_pair),
            payload={"pair": requested_pair},
            timeout=20.0,
        )

        if response.get("error"):
            raise RuntimeError(f"Broker error: {response['error']}")

        positions = response.get("positions", [])
        if not isinstance(positions, list):
            positions = []

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for position in positions:
            if not isinstance(position, dict):
                continue
            pair_name = str(position.get("pair") or "UNKNOWN").strip().upper() or "UNKNOWN"
            grouped[pair_name].append(position)

        if requested_pair is not None and requested_pair not in grouped:
            grouped[requested_pair] = []

        pairs_payload = {
            pair_name: {
                "count": len(pair_positions),
                "orders": pair_positions,
            }
            for pair_name, pair_positions in sorted(grouped.items())
        }

        return {
            "success": True,
            "broker_name": context.broker_name,
            "pair_filter": requested_pair,
            "used_context_pair": context.pair,
            "total_count": sum(item["count"] for item in pairs_payload.values()),
            "pairs": pairs_payload,
        }

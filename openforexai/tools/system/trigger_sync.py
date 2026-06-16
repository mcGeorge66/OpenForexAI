"""Tool: trigger_sync — manually trigger an order book sync via broker adapter bus."""
from __future__ import annotations

from typing import Any

from openforexai.models.messaging import EventType
from openforexai.tools.base import BaseTool, ToolContext, bus_request


def _broker_adapter_id(broker_name: str, pair: str) -> str:
    b = broker_name.upper().ljust(5, "_")[:5]
    p = pair.upper().ljust(6, "_")[:6]
    return f"{b}-{p}-AD-ADPT"


class TriggerSyncTool(BaseTool):
    name = "trigger_sync"
    description = (
        "Manually trigger an order book sync for this pair. "
        "The broker adapter compares open positions against the internal order book "
        "and reports any discrepancies. "
        "Use when you suspect a position was closed externally or data is stale."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {"type": "string", "description": "Broker short_name or module name."},
            "pair": {"type": "string", "description": "Currency pair, e.g. EURUSD."},
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")

        # Publish POSITIONS_REQUEST to broker adapter which will run a sync
        response = await bus_request(
            context=context,
            event_type=EventType.POSITIONS_REQUEST,
            target_id=_broker_adapter_id(context.broker_name, context.pair),
            payload={"pair": context.pair, "trigger_sync": True},
            timeout=30.0,
        )

        discrepancies = response.get("discrepancies", [])
        return {
            "sync_triggered": True,
            "pair": context.pair,
            "broker": context.broker_name,
            "discrepancies_found": len(discrepancies),
            "discrepancies": discrepancies,
        }

"""Tool: trigger_sync — manually trigger an order book sync with the broker."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


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
        "properties": {},
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if context.broker is None:
            raise RuntimeError("Broker adapter not available in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")

        # BrokerBase exposes trigger_sync(); call it on the adapter
        if hasattr(context.broker, "trigger_sync"):
            discrepancies = await context.broker.trigger_sync(
                pair=context.pair,
                repository=context.repository,
                event_bus=context.event_bus,
            )
        else:
            raise RuntimeError("Broker adapter does not support manual sync")

        return {
            "sync_triggered": True,
            "pair": context.pair,
            "broker": context.broker_name,
            "discrepancies_found": len(discrepancies) if discrepancies else 0,
            "discrepancies": discrepancies or [],
        }


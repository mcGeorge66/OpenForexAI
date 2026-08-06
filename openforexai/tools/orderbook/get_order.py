"""Tool: get_order — fetch one specific order/trade by id, full detail incl. AA analysis."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request


class GetOrderTool(BaseTool):
    name = "get_order"
    description = (
        "Fetch one specific order/trade from the internal order book by its id. Returns the "
        "full record: entry/exit prices, P&L, status, close_reason/close_reasoning, and the "
        "complete market_context_snapshot (the AA's raw analysis text, parsed decision, and "
        "support/resistance/indicator overlays at the moment the order was placed)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order book entry id (UUID)."},
        },
        "required": ["order_id"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        order_id = str(arguments.get("order_id", "")).strip()
        if not order_id:
            return {"error": "Argument 'order_id' is required."}
        entry = await repo_request(context, "get_order_book_entry", {"entry_id": order_id})
        if not entry:
            return {"error": f"No order found with id {order_id!r}."}
        return entry

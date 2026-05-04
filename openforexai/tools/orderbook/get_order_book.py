"""Tool: get_order_book — retrieve the internal order book for the current pair."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class GetOrderBookTool(BaseTool):
    name = "get_order_book"
    description = (
        "Retrieve the internal order book entries for the current pair. "
        "Shows open and recently closed orders placed by agents, including "
        "entry reasoning, P&L, stop-loss, take-profit, and sync status. "
        "Use to understand current exposure and trade history for this pair."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "status_filter": {
                "type": "string",
                "description": "Filter by order status: 'open' | 'all'. Default: 'open'.",
                "enum": ["open", "all"],
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of entries to return (1–100). Default: 20.",
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if context.repository is None:
            raise RuntimeError("Repository not available in tool context")
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")

        status_filter = arguments.get("status_filter", "open")
        limit = min(int(arguments.get("limit", 20)), 100)

        if status_filter == "open":
            entries = await context.repository.get_open_order_book_entries(
                context.broker_name, context.pair
            )
        else:
            entries = await context.repository.get_order_book_entries(
                context.broker_name, context.pair, limit=limit
            )

        return [
            {
                "id": str(e.id),
                "broker_order_id": e.broker_order_id,
                "pair": e.pair,
                "direction": e.direction,
                "order_type": e.order_type,
                "units": e.units,
                "fill_price": float(e.fill_price) if e.fill_price else None,
                "stop_loss": float(e.stop_loss) if e.stop_loss else None,
                "take_profit": float(e.take_profit) if e.take_profit else None,
                "status": e.status,
                "entry_reasoning": e.entry_reasoning,
                "signal_confidence": e.signal_confidence,
                "opened_at": e.opened_at.isoformat() if e.opened_at else None,
                "closed_at": e.closed_at.isoformat() if e.closed_at else None,
                "close_reason": e.close_reason,
                "pnl_pips": e.pnl_pips,
                "pnl_account_currency": float(e.pnl_account_currency) if e.pnl_account_currency else None,
                "sync_confirmed": e.sync_confirmed,
            }
            for e in entries[:limit]
        ]


"""Tool: get_order_book — retrieve the internal order book for the current pair."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class GetOrderBookTool(BaseTool):
    name = "get_order_book"
    description = (
        "Retrieve the internal order book entries for the current pair or, if no pair "
        "is set in context, for the current broker. Shows open and recently closed "
        "orders placed by agents, including entry reasoning, P&L, stop-loss, "
        "take-profit, and sync status."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {
                "type": "string",
                "description": "Broker short_name or module name. Used by the Tool Executor to resolve broker context.",
            },
            "pair": {
                "type": "string",
                "description": "Optional currency pair, e.g. EURUSD. If omitted, broker-wide results are returned.",
            },
            "status_filter": {
                "type": "string",
                "description": (
                    "Filter by order status: 'open' (active entries: pending/open/partially_filled), "
                    "'pending', 'partially_filled', 'closed', 'rejected', 'cancelled', or 'all'. "
                    "Default: 'open'."
                ),
                "enum": [
                    "open",
                    "pending",
                    "partially_filled",
                    "closed",
                    "rejected",
                    "cancelled",
                    "all",
                ],
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

        status_filter = arguments.get("status_filter", "open")
        limit = min(int(arguments.get("limit", 20)), 100)
        pair = context.pair

        if status_filter == "open":
            entries = await context.repository.get_open_order_book_entries(
                context.broker_name, pair
            )
        else:
            entries = await context.repository.get_order_book_entries(
                context.broker_name, pair, limit=limit
            )
            exact_status_map = {
                "pending": "PENDING",
                "partially_filled": "PARTIALLY_FILLED",
                "closed": "CLOSED",
                "rejected": "REJECTED",
                "cancelled": "CANCELLED",
            }
            target_status = exact_status_map.get(status_filter)
            if target_status is not None:
                entries = [e for e in entries if str(e.status) == target_status]

        return [
            {
                "id": str(e.id),
                "broker_name": e.broker_name,
                "sync_key": e.sync_key,
                "broker_order_id": e.broker_order_id,
                "pair": e.pair,
                "direction": e.direction.value,
                "order_type": e.order_type.value,
                "units": e.units,
                "requested_price": float(e.requested_price),
                "fill_price": float(e.fill_price) if e.fill_price else None,
                "stop_loss": float(e.stop_loss) if e.stop_loss else None,
                "take_profit": float(e.take_profit) if e.take_profit else None,
                "status": e.status.value,
                "entry_reasoning": e.entry_reasoning,
                "signal_confidence": e.signal_confidence,
                "requested_at": e.requested_at.isoformat(),
                "opened_at": e.opened_at.isoformat() if e.opened_at else None,
                "closed_at": e.closed_at.isoformat() if e.closed_at else None,
                "close_reason": e.close_reason.value if hasattr(e.close_reason, "value") else e.close_reason,
                "close_price": float(e.close_price) if e.close_price else None,
                "close_reasoning": e.close_reasoning,
                "pnl_pips": float(e.pnl_pips) if e.pnl_pips is not None else None,
                "pnl_account_currency": float(e.pnl_account_currency) if e.pnl_account_currency is not None else None,
                "analyst_decision": (e.market_context_snapshot.get("decision_context") or {}).get("decision"),
                "analysis_available": bool(e.market_context_snapshot.get("analyst_recommendation_raw")),
                "sync_confirmed": e.sync_confirmed,
            }
            for e in entries[:limit]
        ]


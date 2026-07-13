"""Tool: get_order_book — retrieve the internal order book via RepositoryService bus."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request


class GetOrderBookTool(BaseTool):
    name = "get_order_book"
    description = (
        "Retrieve the internal order book entries for the current pair or broker. "
        "Shows open and recently closed orders placed by agents, including entry reasoning, "
        "P&L, stop-loss, take-profit, and sync status."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {"type": "string", "description": "Broker short_name or module name."},
            "pair": {"type": "string", "description": "Optional currency pair."},
            "status_filter": {
                "type": "string",
                "description": "Filter: 'open' | 'pending' | 'partially_filled' | 'closed' | 'rejected' | 'cancelled' | 'all'. Default: 'open'.",
                "enum": ["open", "pending", "partially_filled", "closed", "rejected", "cancelled", "all"],
            },
            "limit": {"type": "integer", "description": "Max entries to return (1–100). Default: 20.", "minimum": 1, "maximum": 100},
            "with_aa_analysis": {"type": "boolean", "description": "Include full AA analyst data (market_context_snapshot). Default: true."},
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")

        status_filter = arguments.get("status_filter", "open")
        limit = min(int(arguments.get("limit", 20)), 100)
        pair = context.pair

        if status_filter == "open":
            entries = await repo_request(
                context, "get_open_order_book_entries",
                {"broker_name": context.broker_name, "pair": pair},
            ) or []
        else:
            entries = await repo_request(
                context, "get_order_book_entries",
                {"broker_name": context.broker_name, "pair": pair, "limit": limit},
            ) or []
            exact_status_map = {
                "pending": "PENDING", "partially_filled": "PARTIALLY_FILLED",
                "closed": "CLOSED", "rejected": "REJECTED", "cancelled": "CANCELLED",
            }
            target_status = exact_status_map.get(status_filter)
            if target_status is not None:
                entries = [e for e in entries if _entry_status(e) == target_status]

        with_aa_analysis = bool(arguments.get("with_aa_analysis", True))
        result = entries[:limit]
        if not with_aa_analysis:
            result = [_entry_to_dict(e) for e in result]
        return result


def _entry_status(e: Any) -> str:
    """Extract status string from either an OrderBookEntry object or a dict."""
    if hasattr(e, "status"):
        s = e.status
        return s.value if hasattr(s, "value") else str(s)
    return str(e.get("status", "")) if isinstance(e, dict) else ""


def _entry_to_dict(e: Any) -> dict:
    d = e.model_dump() if hasattr(e, "model_dump") else (e if isinstance(e, dict) else dict(e))
    d.pop("market_context_snapshot", None)
    return d

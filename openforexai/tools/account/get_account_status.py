"""Tool: get_account_status — retrieve live account balance, equity, margin."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class GetAccountStatusTool(BaseTool):
    name = "get_account_status"
    description = (
        "Retrieve the current account status: balance, equity, free margin, "
        "margin level, leverage, and whether trading is allowed. "
        "Use before placing orders to verify available capital."
    )
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if context.broker is None:
            raise RuntimeError("Broker adapter not available in tool context")

        status = await context.broker.get_account_status()
        return {
            "broker_name": status.broker_name,
            "balance": float(status.balance),
            "equity": float(status.equity),
            "margin": float(status.margin),
            "margin_free": float(status.margin_free),
            "margin_level": float(status.margin_level) if status.margin_level is not None else None,
            "leverage": status.leverage,
            "currency": status.currency,
            "trade_allowed": status.trade_allowed,
            "recorded_at": status.recorded_at.isoformat(),
        }


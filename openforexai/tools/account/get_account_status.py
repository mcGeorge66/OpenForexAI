"""Tool: get_account_status — retrieve live account status via broker adapter bus request."""
from __future__ import annotations

from typing import Any

from openforexai.messaging.agent_id import AgentId
from openforexai.models.messaging import EventType
from openforexai.tools.base import BaseTool, ToolContext, bus_request


def _broker_adapter_id(broker_name: str, pair: str) -> str:
    b = broker_name.upper().ljust(5, "_")[:5]
    p = pair.upper().ljust(6, "_")[:6]
    return f"{b}-{p}-AD-ADPT"


class GetAccountStatusTool(BaseTool):
    name = "get_account_status"
    description = (
        "Retrieve the current account status: balance, equity, free margin, "
        "margin level, leverage, and whether trading is allowed. "
        "Use before placing orders to verify available capital."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {
                "type": "string",
                "description": "Broker short_name or module name.",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")
        pair = context.pair or "ALL___"

        response = await bus_request(
            context=context,
            event_type=EventType.ACCOUNT_STATUS_REQUEST,
            target_id=_broker_adapter_id(context.broker_name, pair),
            payload={},
            timeout=20.0,
        )

        if response.get("error"):
            raise RuntimeError(f"Broker error: {response['error']}")

        status = response.get("status", {})
        return {
            "broker_name": status.get("broker_name"),
            "balance": status.get("balance"),
            "equity": status.get("equity"),
            "margin": status.get("margin"),
            "margin_free": status.get("margin_free"),
            "margin_level": status.get("margin_level"),
            "leverage": status.get("leverage"),
            "currency": status.get("currency"),
            "trade_allowed": status.get("trade_allowed"),
            "recorded_at": status.get("recorded_at"),
        }

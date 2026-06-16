"""Tool: modify_order — adjust SL/TP limits via broker adapter bus request."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from openforexai.models.messaging import EventType
from openforexai.models.trade import OrderStatus
from openforexai.tools.base import BaseTool, ToolContext, bus_request, repo_request


def _broker_adapter_id(broker_name: str, pair: str) -> str:
    b = broker_name.upper().ljust(5, "_")[:5]
    p = pair.upper().ljust(6, "_")[:6]
    return f"{b}-{p}-AD-ADPT"


class ModifyOrderTool(BaseTool):
    name = "modify_order"
    description = (
        "Modify the stop-loss and/or take-profit of an open broker position. "
        "At least one limit must be provided."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {"type": "string", "description": "Broker short_name or module name."},
            "pair": {"type": "string", "description": "Optional currency pair, e.g. EURUSD."},
            "position_id": {"type": "string", "description": "Broker-assigned open position ID to modify."},
            "stop_loss": {"type": "number", "description": "New stop-loss price."},
            "take_profit": {"type": "number", "description": "New take-profit price."},
            "reasoning": {"type": "string", "description": "Optional audit note."},
        },
        "required": ["position_id"],
    }
    requires_approval = False

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")

        stop_loss = (
            Decimal(str(arguments["stop_loss"])) if arguments.get("stop_loss") is not None else None
        )
        take_profit = (
            Decimal(str(arguments["take_profit"])) if arguments.get("take_profit") is not None else None
        )
        if stop_loss is None and take_profit is None:
            raise ValueError("At least one of stop_loss or take_profit must be provided.")

        position_id = arguments["position_id"]
        pair = context.pair or "ALL___"

        response = await bus_request(
            context=context,
            event_type=EventType.ORDER_MODIFY_REQUEST,
            target_id=_broker_adapter_id(context.broker_name, pair),
            payload={
                "position_id": position_id,
                "stop_loss": float(stop_loss) if stop_loss is not None else None,
                "take_profit": float(take_profit) if take_profit is not None else None,
            },
            timeout=20.0,
        )

        if response.get("error"):
            raise RuntimeError(f"Modify order failed: {response['error']}")

        result_status = response.get("status", "UNKNOWN")
        order_book_entry_id: str | None = None

        if context.broker_name and result_status != "REJECTED":
            local_open = await repo_request(
                context, "get_open_order_book_entries",
                {"broker_name": context.broker_name, "pair": context.pair},
            ) or []
            matching_entry = next(
                (e for e in local_open if e.get("broker_order_id") == position_id), None
            )
            if matching_entry is not None:
                order_book_entry_id = str(matching_entry.get("id"))
                updates: dict[str, Any] = {
                    "last_broker_sync": datetime.now(UTC).isoformat(),
                    "sync_confirmed": True,
                }
                if stop_loss is not None:
                    updates["stop_loss"] = str(stop_loss)
                if take_profit is not None:
                    updates["take_profit"] = str(take_profit)
                await repo_request(context, "update_order_book_entry", {
                    "entry_id": order_book_entry_id, "updates": updates,
                })

        return {
            "success": result_status != "REJECTED",
            "position_id": position_id,
            "status": result_status,
            "broker_name": context.broker_name,
            "stop_loss": float(stop_loss) if stop_loss is not None else None,
            "take_profit": float(take_profit) if take_profit is not None else None,
            "order_book_entry_id": order_book_entry_id,
        }

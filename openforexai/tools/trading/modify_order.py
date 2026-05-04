"""Tool: modify_order — adjust SL/TP limits for an open position."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class ModifyOrderTool(BaseTool):
    name = "modify_order"
    description = (
        "Modify the stop-loss and/or take-profit of an open broker position. "
        "At least one limit must be provided."
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
                "description": "Optional currency pair, e.g. EURUSD. Used by the Tool Executor to resolve pair context.",
            },
            "position_id": {
                "type": "string",
                "description": "The broker-assigned open position ID to modify.",
            },
            "stop_loss": {
                "type": "number",
                "description": "New stop-loss price. Omit to keep the current stop-loss unchanged.",
            },
            "take_profit": {
                "type": "number",
                "description": "New take-profit price. Omit to keep the current take-profit unchanged.",
            },
            "reasoning": {
                "type": "string",
                "description": "Optional audit note explaining why the limits are being changed.",
            },
        },
        "required": ["position_id"],
    }
    requires_approval = False

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if context.broker is None:
            raise RuntimeError("Broker adapter not available in tool context")

        stop_loss = (
            Decimal(str(arguments["stop_loss"]))
            if arguments.get("stop_loss") is not None
            else None
        )
        take_profit = (
            Decimal(str(arguments["take_profit"]))
            if arguments.get("take_profit") is not None
            else None
        )
        if stop_loss is None and take_profit is None:
            raise ValueError("At least one of stop_loss or take_profit must be provided.")

        position_id = arguments["position_id"]
        result = await context.broker.modify_position(
            position_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        order_book_entry_id: str | None = None
        if context.repository is not None and context.broker_name and result.status != "REJECTED":
            local_open = await context.repository.get_open_order_book_entries(context.broker_name)
            matching_entry = next(
                (entry for entry in local_open if entry.broker_order_id == position_id),
                None,
            )
            if matching_entry is not None:
                order_book_entry_id = str(matching_entry.id)
                updates: dict[str, Any] = {
                    "last_broker_sync": datetime.now(UTC),
                    "sync_confirmed": True,
                }
                if stop_loss is not None:
                    updates["stop_loss"] = stop_loss
                if take_profit is not None:
                    updates["take_profit"] = take_profit
                await context.repository.update_order_book_entry(order_book_entry_id, updates)

        return {
            "success": result.status != "REJECTED",
            "position_id": position_id,
            "status": result.status,
            "broker_name": result.broker_name,
            "broker_message": result.close_reason,
            "stop_loss": float(stop_loss) if stop_loss is not None else None,
            "take_profit": float(take_profit) if take_profit is not None else None,
            "order_book_entry_id": order_book_entry_id,
        }

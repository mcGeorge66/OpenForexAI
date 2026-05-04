"""Tool: close_position — close an open position by ID."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from openforexai.models.trade import CloseReason, OrderStatus
from openforexai.tools.base import BaseTool, ToolContext


class ClosePositionTool(BaseTool):
    name = "close_position"
    description = (
        "Close an open position by its broker position ID. "
        "Use get_open_positions to retrieve position IDs first. "
        "Use get_open_positions to retrieve position IDs first."
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
                "description": "Optional currency pair, e.g. EURUSD. Used to narrow close-all operations and tool context.",
            },
            "position_id": {
                "type": "string",
                "description": "The broker-assigned position ID to close.",
            },
            "units": {
                "type": "integer",
                "description": "Optional partial close size in broker units. If omitted, closes the full position.",
                "exclusiveMinimum": 0,
            },
            "lots": {
                "type": "number",
                "description": "Optional partial close size in lots. Converted to units using lots * 100000.",
                "exclusiveMinimum": 0,
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why this position is being closed (logged).",
            },
        },
        "required": ["position_id"],
    }
    requires_approval = False

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if context.broker is None:
            raise RuntimeError("Broker adapter not available in tool context")

        position_id = arguments["position_id"]
        reasoning = str(arguments.get("reasoning", "")).strip() or None
        lots_arg = arguments.get("lots")
        units_arg = arguments.get("units")
        close_units: int | None = None
        if lots_arg is not None and str(lots_arg) != "":
            lots = float(lots_arg)
            if lots <= 0:
                raise ValueError("lots must be > 0")
            close_units = int(lots * 100_000)
        elif units_arg is not None and str(units_arg) != "":
            close_units = int(units_arg)
            if close_units <= 0:
                raise ValueError("units must be > 0")

        if str(position_id) == "0":
            positions = await context.broker.get_open_positions()
            if context.pair:
                positions = [p for p in positions if p.pair == context.pair]
            results: list[dict[str, Any]] = []
            for position in positions:
                result = await self.execute(
                    {
                        "position_id": position.broker_position_id,
                        "units": close_units,
                        "reasoning": reasoning,
                    },
                    context,
                )
                results.append(result)
            return {
                "success": all(bool(item.get("success")) for item in results),
                "status": "BATCH",
                "closed_count": len(results),
                "results": results,
            }

        result = await context.broker.close_position(position_id, units=close_units)
        order_book_entry_id: str | None = None
        remaining_units: int | None = None

        if context.repository is not None and context.broker_name:
            local_open = await context.repository.get_open_order_book_entries(context.broker_name)
            matching_entry = next(
                (entry for entry in local_open if entry.broker_order_id == position_id),
                None,
            )
            if matching_entry is not None:
                order_book_entry_id = str(matching_entry.id)
                existing_pnl = matching_entry.pnl_account_currency or 0
                accumulated_pnl = existing_pnl + result.pnl if result.pnl is not None else matching_entry.pnl_account_currency
                if result.status == "CLOSED":
                    remaining_units = 0
                    await context.repository.update_order_book_entry(
                        order_book_entry_id,
                        {
                            "status": OrderStatus.CLOSED,
                            "close_reason": CloseReason.AGENT_CLOSED,
                            "close_reasoning": reasoning,
                            "close_price": result.fill_price,
                            "pnl_account_currency": accumulated_pnl,
                            "closed_at": result.closed_at or datetime.now(UTC),
                            "last_broker_sync": datetime.now(UTC),
                            "sync_confirmed": True,
                        },
                    )
                elif result.status == "OPEN" and close_units is not None:
                    remaining_units = max(matching_entry.units - close_units, 0)
                    await context.repository.update_order_book_entry(
                        order_book_entry_id,
                        {
                            "units": remaining_units,
                            "pnl_account_currency": accumulated_pnl,
                            "last_broker_sync": datetime.now(UTC),
                            "sync_confirmed": True,
                        },
                    )

        return {
            "success": result.status != "REJECTED",
            "position_id": position_id,
            "status": result.status,
            "order_id": result.broker_order_id,
            "close_price": float(result.fill_price) if result.fill_price else None,
            "pnl": float(result.pnl) if result.pnl is not None else None,
            "closed_units": close_units,
            "remaining_units": remaining_units,
            "broker_name": result.broker_name,
            "order_book_entry_id": order_book_entry_id,
        }


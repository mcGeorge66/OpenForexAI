"""Tool: get_open_positions — retrieve all currently open positions."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class GetOpenPositionsTool(BaseTool):
    name = "get_open_positions"
    description = (
        "Retrieve all currently open positions for this broker. "
        "Returns pair, direction, units, entry price, current P&L, "
        "stop-loss and take-profit levels. "
        "Use to assess current exposure before making new trade decisions."
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
                "description": "Optional currency pair, e.g. EURUSD. If set, only positions for that pair are returned.",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if context.broker is None:
            raise RuntimeError("Broker adapter not available in tool context")

        positions = await context.broker.get_open_positions()
        if context.pair:
            positions = [p for p in positions if p.pair.upper() == context.pair.upper()]
        return [
            {
                "position_id": p.broker_position_id,
                "pair": p.pair,
                "direction": p.direction.value,
                "units": p.units,
                "entry_price": float(p.open_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "stop_loss": float(p.stop_loss) if p.stop_loss else None,
                "take_profit": float(p.take_profit) if p.take_profit else None,
                "unrealized_pnl": float(p.unrealized_pnl) if p.unrealized_pnl else None,
                "broker_name": p.broker_name,
            }
            for p in positions
        ]


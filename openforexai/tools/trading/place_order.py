"""Tool: place_order — submit a trade order to the broker."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class PlaceOrderTool(BaseTool):
    name = "place_order"
    description = (
        "Submit a trade order for the current currency pair. "
        "Supported order types: MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP. "
        "Always specify stop_loss and take_profit for risk management. "
        "Always specify stop_loss and take_profit for risk management."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "description": "Trade direction: 'buy' | 'sell'",
                "enum": ["buy", "sell"],
            },
            "order_type": {
                "type": "string",
                "description": "Order type: MARKET | LIMIT | STOP | STOP_LIMIT | TRAILING_STOP",
                "enum": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT", "TRAILING_STOP"],
            },
            "units": {
                "type": "number",
                "description": "Number of units to trade (positive number).",
                "exclusiveMinimum": 0,
            },
            "risk_pct": {
                "type": "number",
                "description": "Percentage of account balance to risk (0.1–5.0). Used to size position.",
                "minimum": 0.1,
                "maximum": 5.0,
            },
            "stop_loss": {
                "type": "number",
                "description": "Stop-loss price level. Strongly recommended.",
            },
            "take_profit": {
                "type": "number",
                "description": "Take-profit price level. Strongly recommended.",
            },
            "limit_price": {
                "type": "number",
                "description": "Limit price for LIMIT and STOP_LIMIT orders.",
            },
            "stop_price": {
                "type": "number",
                "description": "Stop trigger price for STOP and STOP_LIMIT orders.",
            },
            "trailing_stop_distance": {
                "type": "number",
                "description": "Trailing stop distance in pips for TRAILING_STOP orders.",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why this trade is being placed (logged for optimization).",
            },
            "confidence": {
                "type": "number",
                "description": "Signal confidence score 0.0–1.0.",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": ["direction", "order_type", "units"],
    }
    requires_approval = False

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        from openforexai.models.trade import TradeOrder, TradeSignal, OrderType

        if context.broker is None:
            raise RuntimeError("Broker adapter not available in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")

        direction = arguments["direction"].lower()
        order_type = OrderType(arguments.get("order_type", "MARKET").upper())
        units = float(arguments["units"])

        signal = TradeSignal(
            pair=context.pair,
            direction=direction,
            confidence=float(arguments.get("confidence", 0.5)),
            reasoning=arguments.get("reasoning", ""),
        )

        order = TradeOrder(
            signal=signal,
            order_type=order_type,
            units=units,
            risk_pct=float(arguments.get("risk_pct", 1.0)),
            stop_loss=Decimal(str(arguments["stop_loss"])) if arguments.get("stop_loss") else None,
            take_profit=Decimal(str(arguments["take_profit"])) if arguments.get("take_profit") else None,
            limit_price=Decimal(str(arguments["limit_price"])) if arguments.get("limit_price") else None,
            stop_price=Decimal(str(arguments["stop_price"])) if arguments.get("stop_price") else None,
            trailing_stop_distance=Decimal(str(arguments["trailing_stop_distance"]))
            if arguments.get("trailing_stop_distance") else None,
            approved_by="supervisor",
        )

        result = await context.broker.place_order(order)
        return {
            "success": result.success,
            "order_id": result.order_id,
            "fill_price": float(result.fill_price) if result.fill_price else None,
            "message": result.message,
        }

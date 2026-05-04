"""Tool: place_order — submit a trade order to the broker."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.trading.order_execution import execute_place_order_arguments


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
            "broker": {
                "type": "string",
                "description": "Broker short_name or module name. Used by the Tool Executor to resolve broker context.",
            },
            "pair": {
                "type": "string",
                "description": "Currency pair, e.g. EURUSD. Used by the Tool Executor to resolve pair context.",
            },
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
                "type": "integer",
                "description": (
                    "Position size in broker units (positive integer, not lots). "
                    "Provide EITHER units, lots, OR risk_pct. "
                    "If lots is provided, it is converted to units using lots * 100000."
                ),
                "exclusiveMinimum": 0,
            },
            "lots": {
                "type": "number",
                "description": (
                    "Position size in lots. "
                    "If provided, this is converted to units using lots * 100000."
                ),
                "exclusiveMinimum": 0,
            },
            "entry_price": {
                "type": "number",
                "description": "Reference entry price. Optional for MARKET, recommended for pending orders.",
            },
            "risk_pct": {
                "type": "number",
                "description": (
                    "Risk-based sizing in percent of account equity (0.1–5.0). "
                    "Provide EITHER risk_pct OR units. "
                    "Used only to compute units before order placement."
                ),
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
                "description": (
                    "Optional documentation text for logs/analysis. "
                    "No direct effect on broker execution."
                ),
            },
            "confidence": {
                "type": "number",
                "description": (
                    "Optional documentation score 0.0–1.0 for audit/analysis. "
                    "No direct effect on broker execution."
                ),
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": ["direction", "order_type"],
    }
    requires_approval = False

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        return await execute_place_order_arguments(arguments, context)


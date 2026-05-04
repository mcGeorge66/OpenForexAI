"""Tool: auto_place_order — place an order using centrally defined defaults."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.trading.order_execution import (
    AUTO_ORDER_DEFAULTS,
    build_auto_place_order_arguments,
    execute_place_order_arguments,
)


class AutoPlaceOrderTool(BaseTool):
    name = "auto_place_order"
    description = (
        "Submit a trade order for the current pair using standard defaults. "
        "Only direction is required; all other fields are optional overrides. "
        "If no units or lots are provided, size is derived from risk_pct."
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
                "description": f"Optional override. Default: {AUTO_ORDER_DEFAULTS['order_type']}",
                "enum": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT", "TRAILING_STOP"],
            },
            "units": {
                "type": "integer",
                "description": "Optional explicit size in broker units. Overrides risk-based sizing.",
                "exclusiveMinimum": 0,
            },
            "lots": {
                "type": "number",
                "description": "Optional explicit size in lots. Converted to units using lots * 100000.",
                "exclusiveMinimum": 0,
            },
            "entry_price": {
                "type": "number",
                "description": "Optional entry price override.",
            },
            "risk_pct": {
                "type": "number",
                "description": f"Optional risk-based sizing override. Default: {AUTO_ORDER_DEFAULTS['risk_pct']}",
                "minimum": 0.1,
                "maximum": 5.0,
            },
            "stop_loss": {
                "type": "number",
                "description": "Optional stop-loss override. If omitted, the shared default is used.",
            },
            "take_profit": {
                "type": "number",
                "description": "Optional take-profit override. If omitted, the shared default is used.",
            },
            "limit_price": {
                "type": "number",
                "description": "Optional limit price override.",
            },
            "stop_price": {
                "type": "number",
                "description": "Optional stop trigger price override.",
            },
            "trailing_stop_distance": {
                "type": "number",
                "description": "Optional trailing stop distance override.",
            },
            "reasoning": {
                "type": "string",
                "description": "Optional documentation text for logs/analysis.",
            },
            "confidence": {
                "type": "number",
                "description": f"Optional confidence override. Default: {AUTO_ORDER_DEFAULTS['confidence']}",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": ["direction"],
    }
    requires_approval = False

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        merged = build_auto_place_order_arguments(arguments)
        return await execute_place_order_arguments(merged, context)

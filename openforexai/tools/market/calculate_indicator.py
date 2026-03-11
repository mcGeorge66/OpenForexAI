"""Tool: calculate_indicator — compute a technical indicator."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class CalculateIndicatorTool(BaseTool):
    name = "calculate_indicator"
    description = (
        "Compute a technical indicator for the current pair and timeframe. "
        "Supports RSI, ATR, SMA, EMA, BB (Bollinger Bands), VWAP. "
        "Use history > 1 to receive a series of values (oldest first) for "
        "trend and divergence analysis."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "indicator": {
                "type": "string",
                "description": "Indicator name: RSI | ATR | SMA | EMA | BB | VWAP",
                "enum": ["RSI", "ATR", "SMA", "EMA", "BB", "VWAP"],
            },
            "period": {
                "type": "integer",
                "description": "Lookback period (e.g. 14 for RSI/ATR, 20 for BB/SMA).",
                "minimum": 1,
                "maximum": 500,
            },
            "timeframe": {
                "type": "string",
                "description": "Candle timeframe: M5 | M15 | M30 | H1 | H4 | D1",
                "enum": ["M5", "M15", "M30", "H1", "H4", "D1"],
            },
            "history": {
                "type": "integer",
                "description": (
                    "Number of consecutive historical values to return (oldest first). "
                    "1 = single latest value (default). "
                    "Use 5–20 for trend analysis."
                ),
                "minimum": 1,
                "maximum": 100,
                "default": 1,
            },
        },
        "required": ["indicator", "period", "timeframe"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        from openforexai.data.indicator_tools import IndicatorToolset
        from openforexai.data.indicator_plugins import DEFAULT_REGISTRY

        if context.data_container is None:
            raise RuntimeError("DataContainer not available in tool context")
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")

        indicator = arguments["indicator"].upper()
        period = int(arguments["period"])
        timeframe = arguments.get("timeframe", "H1").upper()
        history = max(1, min(int(arguments.get("history", 1)), 100))

        toolset = IndicatorToolset(
            data_container=context.data_container,
            registry=DEFAULT_REGISTRY,
            default_broker=context.broker_name,
        )
        result = await toolset.calculate(
            indicator=indicator,
            period=period,
            timeframe=timeframe,
            pair=context.pair,
            history=history,
        )

        if result is None:
            return {"value": None, "reason": "Not enough candle data"}

        return {"indicator": indicator, "period": period, "timeframe": timeframe,
                "history": history, "value": result}


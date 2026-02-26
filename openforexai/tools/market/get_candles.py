"""Tool: get_candles — retrieve OHLCV candle data for the agent's pair."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext

_VALID_TIMEFRAMES = {"M5", "M15", "M30", "H1", "H4", "D1"}


class GetCandlesTool(BaseTool):
    name = "get_candles"
    description = (
        "Retrieve OHLCV candle data for the current currency pair. "
        "Use this to analyse price history at any supported timeframe."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "timeframe": {
                "type": "string",
                "description": "Candle timeframe: M5 | M15 | M30 | H1 | H4 | D1",
                "enum": ["M5", "M15", "M30", "H1", "H4", "D1"],
            },
            "count": {
                "type": "integer",
                "description": "Number of candles to return (1–500, newest last). Default: 50.",
                "minimum": 1,
                "maximum": 500,
            },
        },
        "required": ["timeframe"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        timeframe = arguments.get("timeframe", "H1").upper()
        if timeframe not in _VALID_TIMEFRAMES:
            raise ValueError(f"Invalid timeframe {timeframe!r}. Must be one of: {', '.join(sorted(_VALID_TIMEFRAMES))}")

        count = min(int(arguments.get("count", 50)), 500)

        if context.data_container is None:
            raise RuntimeError("DataContainer not available in tool context")
        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")

        candles = context.data_container.get_candles(
            context.broker_name, context.pair, timeframe
        )
        candles = candles[-count:]

        return [
            {
                "timestamp": c.timestamp.isoformat(),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "tick_volume": c.tick_volume,
                "spread": float(c.spread),
            }
            for c in candles
        ]

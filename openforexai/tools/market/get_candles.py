"""Tool: get_candles — retrieve OHLCV candle data via DataContainer bus request."""
from __future__ import annotations

from typing import Any

from openforexai.data.container import DATA_CONTAINER_ID
from openforexai.models.messaging import EventType
from openforexai.tools.base import BaseTool, ToolContext, bus_request, get_tool_default

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
            "broker": {
                "type": "string",
                "description": "Broker short_name or module name.",
            },
            "pair": {
                "type": "string",
                "description": "Currency pair, e.g. EURUSD.",
            },
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
        timeframe = (arguments.get("timeframe") or get_tool_default("get_candles", "timeframe", "M5")).upper()
        if timeframe not in _VALID_TIMEFRAMES:
            raise ValueError(f"Invalid timeframe {timeframe!r}. Must be one of: {', '.join(sorted(_VALID_TIMEFRAMES))}")

        count = min(int(arguments.get("count") or get_tool_default("get_candles", "count", 50)), 500)

        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")

        response = await bus_request(
            context=context,
            event_type=EventType.CANDLES_REQUEST,
            target_id=DATA_CONTAINER_ID,
            payload={
                "broker_name": context.broker_name,
                "pair": context.pair,
                "timeframe": timeframe,
                "limit": count,
            },
        )

        if response.get("error"):
            raise RuntimeError(f"DataContainer error: {response['error']}")

        candles = response.get("candles", [])
        return candles[-count:]

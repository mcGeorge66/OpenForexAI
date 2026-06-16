"""Tool: calculate_indicator — compute a technical indicator via bus."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from openforexai.data.container import DATA_CONTAINER_ID
from openforexai.models.messaging import EventType
from openforexai.tools.base import BaseTool, ToolContext, bus_request, candle_dicts_to_objects, get_tool_default


class CalculateIndicatorTool(BaseTool):
    name = "calculate_indicator"
    description = (
        "Compute a technical indicator for the current pair and timeframe. "
        "Supports RSI, ATR, SMA, EMA, BB (Bollinger Bands), VWAP, DXY (synthetic Dollar Index). "
        "Returns indicator values together with their candle timestamps. "
        "Use history > 1 to receive a timestamped series (oldest first) for "
        "trend and divergence analysis."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {"type": "string", "description": "Broker short_name or module name."},
            "pair": {"type": "string", "description": "Currency pair, e.g. EURUSD."},
            "indicator": {
                "type": "string",
                "description": "Indicator name: RSI | ATR | SMA | EMA | BB | VWAP | DXY | SLOPE_E | SLOPE_S",
                "enum": ["RSI", "ATR", "SMA", "EMA", "BB", "VWAP", "DXY", "SLOPE_E", "SLOPE_S"],
            },
            "period": {"type": "integer", "description": "Lookback period. For VWAP: 0 = daily reset from 00:00 UTC, >0 = rolling over N candles.", "minimum": 0, "maximum": 500},
            "timeframe": {
                "type": "string",
                "description": "Candle timeframe: M5 | M15 | M30 | H1 | H4 | D1",
                "enum": ["M5", "M15", "M30", "H1", "H4", "D1"],
            },
            "history": {
                "type": "integer",
                "description": "Number of historical values to return (1 = latest only).",
                "minimum": 1, "maximum": 500, "default": 1,
            },
            "smooth_period": {
                "type": "integer",
                "description": "Apply EMA smoothing to the indicator output (period of the smoothing EMA). 1 = no smoothing (default). Useful for slope indicators to reduce noise.",
                "minimum": 1, "maximum": 50, "default": 1,
            },
        },
        "required": ["indicator", "period", "timeframe"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        from openforexai.data.indicator_plugins import DEFAULT_REGISTRY

        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")

        indicator = arguments["indicator"].upper()
        period = int(arguments["period"])
        timeframe = (arguments.get("timeframe") or get_tool_default("calculate_indicator", "timeframe", "H1")).upper()
        history = max(1, min(int(arguments.get("history") or get_tool_default("calculate_indicator", "history", 1)), 500))

        plugin = DEFAULT_REGISTRY.get(indicator)
        if plugin is None:
            raise ValueError(f"Unknown indicator {indicator!r}. Available: {', '.join(DEFAULT_REGISTRY.registered_names())}")

        # DXY needs component pair candles
        if getattr(plugin, "requires_component_pairs", False):
            return await self._compute_dxy(context, plugin, period, timeframe, history)

        # Get candles via DataContainer bus request
        # For VWAP period=0 (daily reset), fetch extra candles to cover from midnight
        if indicator == "VWAP" and period == 0:
            candle_limit = history + 300
        else:
            candle_limit = period * 3 + history + 10
        response = await bus_request(
            context=context,
            event_type=EventType.CANDLES_REQUEST,
            target_id=DATA_CONTAINER_ID,
            payload={"broker_name": context.broker_name, "pair": context.pair,
                     "timeframe": timeframe, "limit": candle_limit},
        )
        if response.get("error"):
            raise RuntimeError(f"DataContainer error: {response['error']}")

        candles = candle_dicts_to_objects(response.get("candles", []))
        if not candles:
            return {"values": None, "reason": "Not enough candle data"}

        smooth_period = max(1, min(int(arguments.get("smooth_period") or 1), 50))
        effective_history = min(max(history, 1), len(candles))
        values = plugin.calculate(candles, period, effective_history)
        if not values:
            return {"values": None, "reason": "Not enough candle data"}

        # Apply EMA smoothing to scalar output if requested
        if smooth_period > 1 and isinstance(values, list) and values and isinstance(values[0], (int, float)):
            alpha = 2.0 / (smooth_period + 1)
            smoothed: list = []
            val = float(values[0])
            for v in values:
                val = alpha * float(v) + (1 - alpha) * val
                smoothed.append(round(val, 6))
            values = smoothed

        result_values = values[0] if history == 1 else values

        # Attach timestamps from the tail of candles
        series = values if isinstance(values, list) else [values]
        candle_tail = candles[-len(series):]

        def _ts(c: Any) -> str | None:
            ts = getattr(c, "timestamp", None)
            if not isinstance(ts, datetime):
                return None
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            return ts.isoformat().replace("+00:00", "Z")

        timestamped = [
            {"timestamp": _ts(candle_tail[i]) if i < len(candle_tail) else None, "value": v}
            for i, v in enumerate(series)
        ]

        return {
            "indicator": indicator,
            "period": period,
            "timeframe": timeframe,
            "history": history,
            "values": timestamped,
        }

    async def _compute_dxy(self, context: ToolContext, plugin: Any, period: int, timeframe: str, history: int) -> Any:
        from openforexai.data.indicators import synthetic_dxy

        component_candles: dict[str, list] = {}
        for comp_pair in getattr(plugin, "DXY_COMPONENTS", []):
            resp = await bus_request(
                context=context,
                event_type=EventType.CANDLES_REQUEST,
                target_id=DATA_CONTAINER_ID,
                payload={"broker_name": context.broker_name, "pair": comp_pair,
                         "timeframe": timeframe, "limit": period * 3 + history + 10},
            )
            candles = candle_dicts_to_objects(resp.get("candles", []))
            if candles:
                component_candles[comp_pair] = candles

        if not component_candles:
            return {"values": None, "reason": "No DXY component data"}

        dxy_values = synthetic_dxy(component_candles)
        if not dxy_values:
            return {"values": None, "reason": "DXY computation failed"}

        # Attach timestamps from first component
        ref_candles = next(iter(component_candles.values()))
        timestamped = [
            {"timestamp": None, "value": v}
            for v in (dxy_values[-history:] if history > 1 else [dxy_values[-1]])
        ]
        return {"indicator": "DXY", "period": period, "timeframe": timeframe,
                "history": history, "values": timestamped}

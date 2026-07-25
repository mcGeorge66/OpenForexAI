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
            "warmup_candles": {
                "type": "integer",
                "description": (
                    "Extra candles fetched before the returned series, so recursive/EMA-style "
                    "smoothing (RSI, ATR, EMA, and SLOPE_E/SLOPE_S when smooth_period > 1) has "
                    "converged by the time it reaches the values actually returned. Leave empty "
                    "to auto-calculate from `period` (targets ~0.1% residual error). Set explicitly "
                    "to override — e.g. to match a specific chart's lookback, or to save DB reads "
                    "when a lower precision is acceptable."
                ),
                "minimum": 0, "maximum": 2000,
            },
            "start": {
                "type": "string",
                "description": (
                    "Optional ISO8601 timestamp. If set, this becomes the anchor point: only "
                    "candles at or before it are used, so the computed values reflect that "
                    "moment in the past instead of the live/most-recent data. Leave empty for "
                    "the normal live behaviour."
                ),
            },
        },
        "required": ["indicator", "period", "timeframe"],
    }

    # Warm-up sizing for recursive smoothing (RSI/ATR use Wilder's alpha=1/period, the
    # slower-converging case; EMA proper uses alpha=2/(period+1)). Wilder's is used as the
    # sizing basis since it's the conservative (larger) requirement of the two, so one
    # multiplier safely covers every indicator that has this dependency at all.
    # k_min = ln(epsilon) / ln(1 - 1/period) ≈ period * ln(1/epsilon) for epsilon=0.001 → ×~6.9,
    # rounded up for margin.
    _WARMUP_MULTIPLIER = 10
    _MIN_WARMUP = 50

    @classmethod
    def _resolve_warmup(cls, arguments: dict[str, Any], period: int) -> int:
        raw = arguments.get("warmup_candles")
        if raw is not None and str(raw).strip() != "":
            return max(0, int(raw))
        return max(period * cls._WARMUP_MULTIPLIER, cls._MIN_WARMUP)

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

        warmup = self._resolve_warmup(arguments, period)
        start = str(arguments.get("start") or "").strip() or None

        # DXY needs component pair candles
        if getattr(plugin, "requires_component_pairs", False):
            return await self._compute_dxy(context, plugin, period, timeframe, history, warmup, start)

        # Get candles via DataContainer bus request
        # For VWAP period=0 (daily reset), fetch extra candles to cover from midnight
        if indicator == "VWAP" and period == 0:
            candle_limit = history + 300
        else:
            candle_limit = warmup + history
        response = await bus_request(
            context=context,
            event_type=EventType.CANDLES_REQUEST,
            target_id=DATA_CONTAINER_ID,
            instrument=context.pair,
            payload={"broker_name": context.broker_name,
                     "timeframe": timeframe, "limit": candle_limit,
                     **({"start": start} if start else {})},
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

    async def _compute_dxy(self, context: ToolContext, plugin: Any, period: int, timeframe: str, history: int, warmup: int, start: str | None = None) -> Any:
        from openforexai.data.indicators import synthetic_dxy

        component_candles: dict[str, list] = {}
        for comp_pair in getattr(plugin, "DXY_COMPONENTS", []):
            resp = await bus_request(
                context=context,
                event_type=EventType.CANDLES_REQUEST,
                target_id=DATA_CONTAINER_ID,
                instrument=comp_pair,
                payload={"broker_name": context.broker_name,
                         "timeframe": timeframe, "limit": warmup + history,
                         **({"start": start} if start else {})},
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

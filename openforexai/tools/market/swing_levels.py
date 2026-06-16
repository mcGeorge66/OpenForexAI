"""Tool: get_swing_levels — detect swing high/low price levels on any timeframe."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from openforexai.data.container import DATA_CONTAINER_ID
from openforexai.models.messaging import EventType
from openforexai.tools.base import BaseTool, ToolContext, bus_request, candle_dicts_to_objects, get_tool_default


def _detect_confluence(
    highs: list[dict],
    lows: list[dict],
    min_gap: float,
    current_price: float,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Find SH/SL pairs within min_gap and merge them into confluence levels.

    Returns (remaining_highs, remaining_lows, confluence_levels).
    Matched highs/lows are removed from their respective lists.
    """
    if not highs or not lows or min_gap <= 0:
        return highs, lows, []

    used_highs: set[int] = set()
    used_lows: set[int] = set()
    confluence: list[dict] = []

    for i, h in enumerate(highs):
        best_j, best_dist = None, float("inf")
        for j, lo in enumerate(lows):
            if j in used_lows:
                continue
            dist = abs(h["price"] - lo["price"])
            if dist <= min_gap and dist < best_dist:
                best_dist, best_j = dist, j
        if best_j is not None:
            used_highs.add(i)
            used_lows.add(best_j)
            lo = lows[best_j]
            avg_price = round((h["price"] + lo["price"]) / 2, 6)
            ts_h, ts_l = h.get("timestamp") or "", lo.get("timestamp") or ""
            most_recent = max(ts_h, ts_l) if ts_h and ts_l else (ts_h or ts_l or None)
            confluence.append({
                "price":     avg_price,
                "timestamp": most_recent,
                "distance":  round(abs(avg_price - current_price), 6),
                "type":      "confluence",
            })

    remaining_highs = [h for i, h in enumerate(highs) if i not in used_highs]
    remaining_lows  = [lo for j, lo in enumerate(lows)  if j not in used_lows]
    return remaining_highs, remaining_lows, confluence


def _cluster_levels(levels: list[dict], min_gap: float, keep: str) -> list[dict]:
    """Merge levels whose prices are within min_gap of each other.

    keep='max' retains the highest price in each cluster (for swing highs).
    keep='min' retains the lowest price in each cluster (for swing lows).
    The most recent timestamp within a cluster is preserved.
    """
    if not levels or min_gap <= 0:
        return levels
    by_price = sorted(levels, key=lambda x: x["price"])
    clusters: list[list[dict]] = [[by_price[0]]]
    for level in by_price[1:]:
        if level["price"] - clusters[-1][-1]["price"] <= min_gap:
            clusters[-1].append(level)
        else:
            clusters.append([level])
    result = []
    for cluster in clusters:
        representative = max(cluster, key=lambda x: x["price"]) if keep == "max" \
                    else min(cluster, key=lambda x: x["price"])
        # Keep the most recent timestamp from the whole cluster
        most_recent = max(
            (c for c in cluster if c["timestamp"]),
            key=lambda x: x["timestamp"],
            default=representative,
        )
        result.append({**representative, "timestamp": most_recent["timestamp"]})
    return result


class GetSwingLevelsTool(BaseTool):
    name = "get_swing_levels"
    description = (
        "Detects swing high and swing low price levels for the current pair on any timeframe. "
        "Uses scipy peak detection with configurable prominence filtering. "
        "Nearby levels are automatically clustered using an ATR-based minimum gap so that "
        "near-duplicate levels are merged into one. "
        "Returns the most recent N swing highs and lows with timestamps and distance from the "
        "current price, plus convenience fields for nearest resistance and nearest support. "
        "Useful for support/resistance context in snapshot tool blocks."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "broker": {
                "type": "string",
                "description": "Broker short_name. Used by the Tool Executor to resolve broker context.",
            },
            "pair": {
                "type": "string",
                "description": "Currency pair, e.g. EURUSD. Used by the Tool Executor to resolve pair context.",
            },
            "timeframe": {
                "type": "string",
                "description": "Candle timeframe: M5 | M15 | M30 | H1 | H4 | D1",
                "enum": ["M5", "M15", "M30", "H1", "H4", "D1"],
            },
            "lookback": {
                "type": "integer",
                "description": "Number of candles to analyse (default 100, max 500).",
                "minimum": 10,
                "maximum": 500,
                "default": 100,
            },
            "prominence": {
                "type": "number",
                "description": (
                    "Minimum price prominence for a swing to qualify. "
                    "0.0 = all local extremes (noisy). Higher values filter out minor wiggles. "
                    "Typical starting points: 0.0005 for M5, 0.001–0.003 for H1."
                ),
                "minimum": 0.0,
                "default": 0.0,
            },
            "atr_period": {
                "type": "integer",
                "description": "ATR period used for cluster gap calculation (default 14).",
                "minimum": 1,
                "maximum": 200,
                "default": 14,
            },
            "min_gap_atr": {
                "type": "number",
                "description": (
                    "Minimum distance between two distinct swing levels, expressed as a multiple "
                    "of ATR(atr_period). Levels closer than this are merged into one (the most "
                    "extreme price in the cluster is kept). Default 0.3 = 30% of ATR. "
                    "Set to 0.0 to disable clustering."
                ),
                "minimum": 0.0,
                "default": 0.3,
            },
            "max_levels": {
                "type": "integer",
                "description": "Maximum number of swing highs and lows to return each (default 5).",
                "minimum": 1,
                "maximum": 20,
                "default": 5,
            },
            "current_price": {
                "type": "number",
                "description": (
                    "Reference price used to compute 'distance' for every level. "
                    "Pass the current M5 close (or any live price) here so that distances "
                    "are meaningful even when swing levels are computed on a higher timeframe "
                    "such as H1 or H4. "
                    "If omitted or null, the tool automatically uses the close of the most "
                    "recent M5 candle available; if no M5 data exists it falls back to the "
                    "close of the last candle of the requested timeframe."
                ),
            },
            "price_source": {
                "type": "string",
                "description": "Price source for swing detection: 'HL' uses High/Low wicks (default), 'OC' uses Open/Close body.",
                "enum": ["HL", "OC"],
                "default": "HL",
            },
            "sort_by": {
                "type": "string",
                "description": "How to select which levels to return: 'nearest' keeps the levels closest to current price (default), 'prominent' keeps the most visually prominent peaks/troughs.",
                "enum": ["nearest", "prominent"],
                "default": "nearest",
            },
        },
        "required": ["timeframe"],
    }

    async def _get_candles(self, context: ToolContext, timeframe: str, limit: int):
        try:
            response = await bus_request(
                context=context,
                event_type=EventType.CANDLES_REQUEST,
                target_id=DATA_CONTAINER_ID,
                payload={"broker_name": context.broker_name, "pair": context.pair,
                         "timeframe": timeframe, "limit": limit},
            )
        except Exception:
            return []
        if response.get("error"):
            return []
        return candle_dicts_to_objects(response.get("candles", []))

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        from openforexai.data.indicators import atr, swing_highs, swing_lows

        if not context.broker_name:
            raise RuntimeError("broker_name not set in tool context")
        if not context.pair:
            raise RuntimeError("pair not set in tool context")

        _D = lambda p, fb: get_tool_default("get_swing_levels", p, fb)
        timeframe    = str(arguments.get("timeframe")   or _D("timeframe",   "H1")).upper()
        lookback     = max(10, min(int(arguments.get("lookback")    or _D("lookback",    100)), 500))
        prominence   = float(arguments.get("prominence")  or _D("prominence",  0.0))
        atr_period   = max(1,  min(int(arguments.get("atr_period")  or _D("atr_period",  14)),  200))
        min_gap_atr  = float(arguments.get("min_gap_atr") or _D("min_gap_atr", 0.3))
        max_levels   = max(1, min(int(arguments.get("max_levels")   or _D("max_levels",  5)),   20))
        price_source = str(arguments.get("price_source") or _D("price_source", "HL")).upper()
        use_oc       = price_source == "OC"
        sort_by      = str(arguments.get("sort_by") or _D("sort_by", "nearest")).lower()
        arg_price    = arguments.get("current_price")
        explicit_price: float | None = float(arg_price) if arg_price is not None else None

        candles = await self._get_candles(context, timeframe, lookback)

        if not candles or len(candles) < 3:
            return {
                "timeframe":          timeframe,
                "lookback":           lookback,
                "candles_available":  len(candles) if candles else 0,
                "current_price":      None,
                "current_price_source": None,
                "atr":                None,
                "min_gap":            None,
                "highs":              [],
                "lows":               [],
                "nearest_resistance": None,
                "nearest_support":    None,
            }

        candles = list(candles)

        # Determine reference price for distance calculations (priority order):
        #   1. Caller-supplied current_price argument
        #   2. Last M5 candle close (when timeframe != M5)
        #   3. Last candle close of the requested timeframe (fallback)
        current_price_source: str
        if explicit_price is not None:
            current_price = explicit_price
            current_price_source = "argument"
        elif timeframe != "M5":
            m5_candles = await self._get_candles(context, "M5", 1)
            if m5_candles:
                current_price = float(list(m5_candles)[-1].close)
                current_price_source = "M5"
            else:
                current_price = float(candles[-1].close)
                current_price_source = timeframe
        else:
            current_price = float(candles[-1].close)
            current_price_source = "M5"

        def _ts(candle: Any) -> str | None:
            ts = getattr(candle, "timestamp", None)
            if not isinstance(ts, datetime):
                return None
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            return ts.isoformat().replace("+00:00", "Z")

        # ATR for adaptive clustering gap
        atr_value = atr(candles, period=atr_period)
        min_gap = round(atr_value * min_gap_atr, 6) if (atr_value and min_gap_atr > 0) else 0.0

        if use_oc:
            import numpy as np
            from openforexai.data.indicators import _find_peaks_plateau
            body_highs = np.array([max(float(c.open), float(c.close)) for c in candles], dtype=float)
            body_lows  = np.array([min(float(c.open), float(c.close)) for c in candles], dtype=float)
            high_peaks = _find_peaks_plateau(body_highs, prominence=prominence)
            low_peaks  = _find_peaks_plateau(-body_lows,  prominence=prominence)
            _high_price = lambda i: round(max(float(candles[i].open), float(candles[i].close)), 6)
            _low_price  = lambda i: round(min(float(candles[i].open), float(candles[i].close)), 6)
        else:
            high_peaks = swing_highs(candles, prominence=prominence)
            low_peaks  = swing_lows(candles,  prominence=prominence)
            _high_price = lambda i: round(float(candles[i].high), 6)
            _low_price  = lambda i: round(float(candles[i].low),  6)

        # Build level dicts for all detected swings (pre-cluster — no max_levels cap yet)
        raw_highs = [
            {
                "price":      _high_price(i),
                "timestamp":  _ts(candles[i]),
                "distance":   round(abs(_high_price(i) - current_price), 6),
                "prominence": prom,
            }
            for i, prom in high_peaks
        ]
        raw_lows = [
            {
                "price":      _low_price(i),
                "timestamp":  _ts(candles[i]),
                "distance":   round(abs(_low_price(i) - current_price), 6),
                "prominence": prom,
            }
            for i, prom in low_peaks
        ]

        # Cluster nearby levels within SH and SL groups
        clustered_highs = _cluster_levels(raw_highs, min_gap, keep="max")
        clustered_lows  = _cluster_levels(raw_lows,  min_gap, keep="min")

        def _sort_nearest(levels: list[dict]) -> list[dict]:
            if sort_by == "prominent":
                return sorted(levels, key=lambda x: x["prominence"], reverse=True)[:max_levels]
            return sorted(levels, key=lambda x: x["distance"])[:max_levels]

        # Cap H and L to max_levels BEFORE confluence detection so that confluence
        # can only merge existing entries — it never adds new ones.
        capped_highs = _sort_nearest(clustered_highs)
        capped_lows  = _sort_nearest(clustered_lows)

        # Detect SH/SL confluence from the already-capped pools
        remaining_highs, remaining_lows, confluence_levels = _detect_confluence(
            capped_highs, capped_lows, min_gap, current_price
        )

        highs      = remaining_highs
        lows       = remaining_lows
        confluence = confluence_levels

        # Tag types and recompute distance after clustering
        for level in highs:
            level["type"]     = "high"
            level["distance"] = round(abs(level["price"] - current_price), 6)
        for level in lows:
            level["type"]     = "low"
            level["distance"] = round(abs(level["price"] - current_price), 6)
        for level in confluence:
            level["distance"] = round(abs(level["price"] - current_price), 6)

        all_levels = highs + lows + confluence
        nearest_resistance = min(
            (lv for lv in all_levels if lv["price"] > current_price),
            key=lambda lv: lv["distance"],
            default=None,
        )
        nearest_support = min(
            (lv for lv in all_levels if lv["price"] < current_price),
            key=lambda lv: lv["distance"],
            default=None,
        )

        return {
            "timeframe":            timeframe,
            "lookback":             lookback,
            "candles_available":    len(candles),
            "current_price":        current_price,
            "current_price_source": current_price_source,
            "atr":                  round(atr_value, 6) if atr_value else None,
            "min_gap":              min_gap,
            "highs":                highs,
            "lows":                 lows,
            "confluence":           confluence,
            "nearest_resistance":   nearest_resistance,
            "nearest_support":      nearest_support,
        }

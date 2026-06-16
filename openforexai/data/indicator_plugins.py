from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from openforexai.data.indicators import atr, bollinger_bands, ema, rsi, sma, vwap
from openforexai.models.market import Candle

# A single indicator value: scalar or multi-component (Bollinger Bands)
IndicatorValue = float | dict[str, float]


class IndicatorPlugin(ABC):
    """Base class for all indicator plugins.

    Subclass this to add a new indicator to the system.  Register an instance
    with an ``IndicatorRegistry``; agents then get the indicator as a named
    tool automatically.

    Example — custom plugin::

        class MACDPlugin(IndicatorPlugin):
            name = "MACD"
            description = "MACD histogram value."
            min_candles = 35

            def calculate(self, candles, period, history):
                results = []
                for offset in range(history - 1, -1, -1):
                    end = len(candles) - offset
                    val = _macd(candles[:end], period)
                    if val is None:
                        return []
                    results.append(round(val, 6))
                return results

        registry.register(MACDPlugin())
    """

    #: Canonical uppercase name used for tool lookup, e.g. ``"RSI"``.
    name: str
    #: Alternative names accepted at lookup time, e.g. ``["MA"]``.
    aliases: list[str] = []
    #: Short human-readable description shown in LLM tool documentation.
    description: str
    #: Minimum number of candles required to produce a valid result.
    min_candles: int

    @abstractmethod
    def calculate(
        self,
        candles: list[Candle],
        period: int,
        history: int,
    ) -> list[IndicatorValue]:
        """Compute *history* consecutive most-recent values.

        Args:
            candles:  Full candle list (oldest first) for the requested
                      timeframe and pair.
            period:   Lookback period for the indicator (e.g. 14 for RSI).
            history:  How many consecutive historical values to return.
                      ``history=1`` → a list with a single element (latest).
                      ``history=5`` → the five most recent values, oldest first.

        Returns:
            A list of *history* values.  Each value is either a ``float``
            (scalar indicators) or a ``dict[str, float]`` (e.g. Bollinger Bands
            with ``upper``, ``middle``, ``lower`` keys).
            Returns an **empty list** when there are not enough candles.
        """
        ...


# ── Concrete plugins ──────────────────────────────────────────────────────────

class SMAPlugin(IndicatorPlugin):
    name = "SMA"
    aliases = ["MA"]
    description = "Simple Moving Average — arithmetic mean of the last N closes."
    min_candles = 2

    def calculate(self, candles, period, history):
        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            val = sma(candles[:end], period)
            if val is None:
                return []
            results.append(round(val, 6))
        return results


class EMAPlugin(IndicatorPlugin):
    name = "EMA"
    aliases = []
    description = "Exponential Moving Average — weighted average emphasising recent closes."
    min_candles = 2

    def calculate(self, candles, period, history):
        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            val = ema(candles[:end], period)
            if val is None:
                return []
            results.append(round(val, 6))
        return results


class RSIPlugin(IndicatorPlugin):
    name = "RSI"
    aliases = []
    description = (
        "Relative Strength Index (0–100). "
        "Above 70 = overbought, below 30 = oversold."
    )
    min_candles = 15  # needs period + 1 delta values

    def calculate(self, candles, period, history):
        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            val = rsi(candles[:end], period)
            if val is None:
                return []
            results.append(round(val, 6))
        return results


class ATRPlugin(IndicatorPlugin):
    name = "ATR"
    aliases = []
    description = (
        "Average True Range — measures volatility as average true candle range. "
        "Useful for stop-loss sizing and volatility assessment."
    )
    min_candles = 15  # needs period + 1 candles

    def calculate(self, candles, period, history):
        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            val = atr(candles[:end], period)
            if val is None:
                return []
            results.append(round(val, 6))
        return results


class BollingerBandsPlugin(IndicatorPlugin):
    name = "BB"
    aliases = ["BOLLINGER"]
    description = (
        "Bollinger Bands — upper/middle/lower bands based on SMA ± N standard deviations. "
        "Returns a dict with keys 'upper', 'middle', 'lower'."
    )
    min_candles = 20

    def calculate(self, candles, period, history):
        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            val = bollinger_bands(candles[:end], period)
            if val is None:
                return []
            upper, middle, lower = val
            results.append({
                "upper":  round(upper,  6),
                "middle": round(middle, 6),
                "lower":  round(lower,  6),
            })
        return results


def _candle_ts_utc(candle) -> "datetime":
    from datetime import UTC as _UTC
    ts = candle.timestamp
    if ts.tzinfo is None:
        return ts.replace(tzinfo=_UTC)
    return ts.astimezone(_UTC)


def _candle_ts_naive(candle) -> "datetime":
    """Return the candle timestamp as naive datetime (strips tzinfo).

    Preserves the wall-clock time as seen in the broker feed, so 00:00 in the
    result always corresponds to broker-local midnight — regardless of the
    UTC offset attached to the timestamp.
    """
    ts = candle.timestamp
    return ts.replace(tzinfo=None)


class VWAPPlugin(IndicatorPlugin):
    name = "VWAP"
    aliases = []
    description = (
        "Volume Weighted Average Price — average price weighted by volume. "
        "period=0 (default): cumulative VWAP from 00:00 of the broker-local day (daily reset). "
        "period>0: rolling VWAP over the last N candles."
    )
    min_candles = 1

    def calculate(self, candles, period, history):
        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            window = candles[:end]
            if not window:
                return []
            if period == 0:
                # Use broker-local wall-clock time so midnight = 00:00 in candle timestamps
                last_naive = _candle_ts_naive(window[-1])
                day_start = last_naive.replace(hour=0, minute=0, second=0, microsecond=0)
                day_candles = [c for c in window if _candle_ts_naive(c) >= day_start]
                val = vwap(day_candles) if day_candles else None
            else:
                val = vwap(window[max(0, end - period):end])
            if val is None:
                return []
            results.append(round(val, 6))
        return results


# ── Registry ──────────────────────────────────────────────────────────────────

class IndicatorRegistry:
    """Central registry of available indicator plugins.

    Agents receive a registry instance (or the default one) at startup.  The
    tool dispatcher dynamically builds tool descriptions from all registered
    plugins, so adding or removing an indicator is a one-line change.

    Example::

        registry = IndicatorRegistry()
        registry.register(RSIPlugin())
        registry.unregister("VWAP")          # remove if deemed useless
        names = registry.registered_names()  # ["RSI"]
    """

    def __init__(self) -> None:
        # Maps every known name / alias → plugin instance
        self._map: dict[str, IndicatorPlugin] = {}
        # Ordered list of unique plugin instances (insertion order)
        self._plugins: list[IndicatorPlugin] = []

    def register(self, plugin: IndicatorPlugin) -> None:
        """Register *plugin* under its canonical name and all aliases."""
        self._map[plugin.name.upper()] = plugin
        for alias in plugin.aliases:
            self._map[alias.upper()] = plugin
        if plugin not in self._plugins:
            self._plugins.append(plugin)

    def unregister(self, name: str) -> None:
        """Remove the plugin registered under *name* (canonical or alias)."""
        plugin = self._map.get(name.upper())
        if plugin is None:
            return
        for key in list(self._map):
            if self._map[key] is plugin:
                del self._map[key]
        if plugin in self._plugins:
            self._plugins.remove(plugin)

    def get(self, name: str) -> IndicatorPlugin | None:
        """Return the plugin for *name*, or ``None`` if not registered."""
        return self._map.get(name.upper())

    def all_plugins(self) -> list[IndicatorPlugin]:
        """Return all registered plugins in insertion order (unique)."""
        return list(self._plugins)

    def registered_names(self) -> list[str]:
        """Return canonical names of all registered plugins."""
        return [p.name for p in self._plugins]


class DXYPlugin(IndicatorPlugin):
    name = "DXY"
    aliases = []
    description = (
        "Synthetic DXY index (5-component ICE approximation, USDSEK excluded). "
        "Returns dxy_close, dxy_direction ('rising'/'falling'), and correlation "
        "with the trading pair's close price."
    )
    min_candles = 10
    requires_component_pairs = True
    DXY_COMPONENTS: list[str] = ["EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF"]

    def calculate(self, candles: list[Candle], period: int, history: int) -> list[IndicatorValue]:
        pair_closes: list[float] = getattr(self, "_pair_closes", [])
        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            if end < 1:
                return []
            dxy_val = float(candles[end - 1].close)
            direction = "rising" if end >= 2 and dxy_val > float(candles[end - 2].close) else "falling"
            dxy_window = [float(c.close) for c in candles[:end]]
            pair_window = pair_closes[:end]
            n = min(len(dxy_window), len(pair_window))
            if n >= 2:
                corr_matrix = np.corrcoef(pair_window[-n:], dxy_window[-n:])
                corr = float(corr_matrix[0, 1])
                corr = 0.0 if np.isnan(corr) else round(corr, 4)
            else:
                corr = 0.0
            results.append({
                "dxy_close": round(dxy_val, 4),
                "dxy_direction": direction,
                "correlation": corr,
            })
        return results


class EMASlopePlugin(IndicatorPlugin):
    name = "SLOPE_E"
    aliases = ["SLOPE"]
    description = (
        "EMA Slope — change of the Exponential Moving Average from one candle to the next, "
        "expressed in pips (price × 10 000 for 4-digit pairs, × 1 000 for JPY pairs). "
        "Positive values indicate the EMA is rising; negative values indicate it is falling. "
        "Use this to quantify trend strength: a slope near zero means a flat/weak trend "
        "regardless of direction. "
        "period controls the EMA lookback; pair pip size is auto-detected from the price scale."
    )
    min_candles = 3  # need at least 2 EMA values → period + 1 candles

    def calculate(self, candles: list[Candle], period: int, history: int) -> list[IndicatorValue]:
        # Detect pip size from pair price magnitude (JPY pairs ≈ 100, others ≈ 1)
        if candles:
            sample_price = float(candles[-1].close)
            pip_divisor = 0.01 if sample_price > 20 else 0.0001
        else:
            pip_divisor = 0.0001

        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            val_now  = ema(candles[:end],     period)
            val_prev = ema(candles[:end - 1], period) if end > 1 else None
            if val_now is None or val_prev is None:
                return []
            slope_pips = round((val_now - val_prev) / pip_divisor, 3)
            results.append(slope_pips)
        return results


class SMASlopePlugin(IndicatorPlugin):
    name = "SLOPE_S"
    aliases = []
    description = (
        "SMA Slope — change of the Simple Moving Average from one candle to the next, "
        "expressed in pips. Same concept as SLOPE_E but based on the Simple Moving Average. "
        "period controls the SMA lookback."
    )
    min_candles = 3

    def calculate(self, candles: list[Candle], period: int, history: int) -> list[IndicatorValue]:
        if candles:
            sample_price = float(candles[-1].close)
            pip_divisor = 0.01 if sample_price > 20 else 0.0001
        else:
            pip_divisor = 0.0001

        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            val_now  = sma(candles[:end],     period)
            val_prev = sma(candles[:end - 1], period) if end > 1 else None
            if val_now is None or val_prev is None:
                return []
            slope_pips = round((val_now - val_prev) / pip_divisor, 3)
            results.append(slope_pips)
        return results


# ── Default registry — pre-loaded with all built-in plugins ──────────────────

DEFAULT_REGISTRY = IndicatorRegistry()
DEFAULT_REGISTRY.register(SMAPlugin())
DEFAULT_REGISTRY.register(EMAPlugin())
DEFAULT_REGISTRY.register(RSIPlugin())
DEFAULT_REGISTRY.register(ATRPlugin())
DEFAULT_REGISTRY.register(BollingerBandsPlugin())
DEFAULT_REGISTRY.register(VWAPPlugin())
DEFAULT_REGISTRY.register(DXYPlugin())
DEFAULT_REGISTRY.register(EMASlopePlugin())
DEFAULT_REGISTRY.register(SMASlopePlugin())


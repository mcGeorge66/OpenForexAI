from __future__ import annotations

from abc import ABC, abstractmethod

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


class VWAPPlugin(IndicatorPlugin):
    name = "VWAP"
    aliases = []
    description = (
        "Volume Weighted Average Price — average price weighted by volume. "
        "Useful as a fair value / intraday benchmark."
    )
    min_candles = 1

    def calculate(self, candles, period, history):
        # VWAP does not use a traditional period; it is computed over the
        # visible candle window ending at each offset position.
        results: list[IndicatorValue] = []
        for offset in range(history - 1, -1, -1):
            end = len(candles) - offset
            val = vwap(candles[:end])
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


# ── Default registry — pre-loaded with all built-in plugins ──────────────────

DEFAULT_REGISTRY = IndicatorRegistry()
DEFAULT_REGISTRY.register(SMAPlugin())
DEFAULT_REGISTRY.register(EMAPlugin())
DEFAULT_REGISTRY.register(RSIPlugin())
DEFAULT_REGISTRY.register(ATRPlugin())
DEFAULT_REGISTRY.register(BollingerBandsPlugin())
DEFAULT_REGISTRY.register(VWAPPlugin())

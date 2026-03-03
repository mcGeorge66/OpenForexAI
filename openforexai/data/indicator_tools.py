from __future__ import annotations

from typing import Union

from openforexai.data.container import DataContainer
from openforexai.data.indicator_plugins import (
    DEFAULT_REGISTRY,
    IndicatorRegistry,
    IndicatorValue,
)

# Public return type:
#   history=1 → single value (float or dict for BB), or None
#   history>1 → list of values (oldest first), or None
IndicatorResult = Union[IndicatorValue, list[IndicatorValue], None]


class IndicatorToolset:
    """Stateless indicator tool for agents.

    Binds a ``DataContainer`` and an ``IndicatorRegistry`` together.  Agents
    call ``toolset.calculate(...)`` — no DataContainer or registry reference is
    needed at the call-site.

    The registry determines which indicators are available.  Remove a plugin
    from the registry to disable it system-wide; add a new plugin to make it
    instantly available to all agents.

    Examples::

        # Single latest value (default)
        rsi = toolset.calculate("RSI", period=14, timeframe="H1", pair="EURUSD")
        # → 62.4  (float)

        # Last 5 values for trend / divergence analysis
        rsi_series = toolset.calculate("RSI", 14, "H1", "EURUSD", history=5)
        # → [58.1, 59.3, 61.0, 61.8, 62.4]  (oldest → newest)

        # Bollinger Bands, single snapshot
        bands = toolset.calculate("BB", 20, "H1", "EURUSD")
        # → {"upper": 1.099, "middle": 1.097, "lower": 1.095}

        # Bollinger Bands, last 3 snapshots
        bands_series = toolset.calculate("BB", 20, "H1", "EURUSD", history=3)
        # → [
        #     {"upper": 1.097, "middle": 1.095, "lower": 1.093},
        #     {"upper": 1.098, "middle": 1.096, "lower": 1.094},
        #     {"upper": 1.099, "middle": 1.097, "lower": 1.095},
        #   ]
    """

    def __init__(
        self,
        data_container: DataContainer,
        registry: IndicatorRegistry | None = None,
        default_broker: str | None = None,
    ) -> None:
        self._dc = data_container
        self._registry = registry or DEFAULT_REGISTRY
        self._default_broker = default_broker

    def set_broker(self, broker_name: str) -> None:
        """Set the default broker_name used when calculate() is called without one."""
        self._default_broker = broker_name

    async def calculate(
        self,
        indicator: str,
        period: int,
        timeframe: str,
        pair: str,
        history: int = 1,
        broker_name: str | None = None,
    ) -> IndicatorResult:
        """Compute *indicator*(*period*) on *pair* candles at *timeframe*.

        Args:
            indicator:    Indicator name — any name registered in the registry,
                          e.g. ``"RSI"``, ``"ATR"``, ``"BB"``, ``"SMA"``.
            period:       Lookback period (e.g. 14 for RSI / ATR, 20 for SMA / BB).
            timeframe:    M5 | M15 | M30 | H1 | H4 | D1
            pair:         Currency pair, e.g. ``"USDJPY"`` or ``"EURUSD"``.
            history:      Number of consecutive historical values to return.
                          ``1`` (default) → single scalar or dict.
                          ``> 1`` → list of values, oldest first.
            broker_name:  Broker short_name required by the multi-broker DataContainer.
                          Falls back to the instance default set via ``set_broker()``.

        Returns:
            - Single ``float`` or ``dict`` when ``history == 1``.
            - ``list[float | dict]`` when ``history > 1``.
            - ``None`` when there are not enough candles or the indicator
              cannot be computed.

        Raises:
            ValueError: when *indicator* is not registered or broker_name is unknown.
        """
        plugin = self._registry.get(indicator)
        if plugin is None:
            available = ", ".join(self._registry.registered_names())
            raise ValueError(
                f"Unknown indicator {indicator!r}. "
                f"Available: {available}"
            )

        resolved_broker = broker_name or self._default_broker
        if resolved_broker is None:
            raise ValueError(
                "broker_name must be provided or set via set_broker() "
                "before calling calculate()."
            )

        candles = await self._dc.get_candles(resolved_broker, pair.upper(), timeframe.upper())
        if not candles:
            return None

        values = plugin.calculate(candles, period, max(history, 1))
        if not values:
            return None

        return values[0] if history == 1 else values

    @property
    def registry(self) -> IndicatorRegistry:
        """The underlying IndicatorRegistry."""
        return self._registry

    def available_indicators(self) -> list[str]:
        """Return canonical names of all registered indicators."""
        return self._registry.registered_names()

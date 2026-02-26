from __future__ import annotations

from abc import ABC, abstractmethod

from openforexai.models.market import Candle, MarketSnapshot


class AbstractDataFeed(ABC):
    """Port: wraps a broker's data access with a clean feed interface."""

    @abstractmethod
    async def get_snapshot(self, pair: str) -> MarketSnapshot: ...

    @abstractmethod
    async def get_rolling_history(
        self, pair: str, timeframe: str, weeks: int = 4
    ) -> list[Candle]: ...

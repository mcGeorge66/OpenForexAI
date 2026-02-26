from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from openforexai.models.market import Candle, Tick
from openforexai.models.trade import Position, TradeOrder, TradeResult


class AbstractBroker(ABC):
    """Port: every broker adapter must implement this contract."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def place_order(self, order: TradeOrder) -> TradeResult: ...

    @abstractmethod
    async def close_position(self, position_id: str) -> TradeResult: ...

    @abstractmethod
    async def get_open_positions(self) -> list[Position]: ...

    @abstractmethod
    async def get_account_balance(self) -> float: ...

    @abstractmethod
    async def stream_ticks(self, pairs: list[str]) -> AsyncIterator[Tick]: ...

    @abstractmethod
    async def get_historical_candles(
        self, pair: str, timeframe: str, count: int
    ) -> list[Candle]: ...

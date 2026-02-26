from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class Candle(BaseModel):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    timeframe: str  # M1 | M5 | H1 | H4 | D1


class Tick(BaseModel):
    pair: str
    bid: Decimal
    ask: Decimal
    timestamp: datetime

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2


class MarketSnapshot(BaseModel):
    pair: str
    current_tick: Tick
    # Lower timeframes for day-trading (M15/M30 computed from M5, no extra API calls)
    candles_m5: list[Candle] = []
    candles_m15: list[Candle] = []
    candles_m30: list[Candle] = []
    # Higher timeframes fetched directly from broker
    candles_h1: list[Candle] = []
    candles_h4: list[Candle] = []
    candles_d1: list[Candle] = []
    session: str  # london | new_york | tokyo | sydney | overlap | closed
    snapshot_time: datetime

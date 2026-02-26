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
    candles_h1: list[Candle]
    candles_h4: list[Candle]
    candles_d1: list[Candle]
    indicators: dict[str, float]  # RSI, ATR, SMA20, EMA50, BB_upper, BB_lower, VWAP
    session: str  # london | new_york | tokyo | sydney | overlap | closed
    snapshot_time: datetime

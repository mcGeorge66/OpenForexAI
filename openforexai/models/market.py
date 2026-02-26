from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class Candle(BaseModel):
    """A single OHLC bar.

    Bid-based prices throughout (ask = bid + spread * pip_size).
    spread is in pips at the moment the candle closed.
    tick_volume is the number of price changes during the period — a proxy
    for activity / liquidity in the absence of real volume data.
    """

    timestamp: datetime        # UTC open time of the bar
    open: Decimal              # bid open
    high: Decimal              # bid high
    low: Decimal               # bid low
    close: Decimal             # bid close
    tick_volume: int           # price-change count during this bar
    spread: Decimal            # bid-ask spread in pips at bar close
    timeframe: str             # M5 | M15 | M30 | H1 | H4 | D1


class Tick(BaseModel):
    """A single bid/ask quote — kept for components that still need a live price."""

    pair: str
    bid: Decimal
    ask: Decimal
    timestamp: datetime

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2


class MarketSnapshot(BaseModel):
    """Complete market context for one pair at one point in time.

    current_tick is derived from the last M5 candle close so agents still
    have a single bid/ask reference without requiring a live tick stream.
    All candle lists are oldest-first.
    """

    pair: str
    broker_name: str           # short_name of the broker this data came from
    current_tick: Tick         # derived from last M5 close + spread
    candles_m5: list[Candle] = []
    candles_m15: list[Candle] = []
    candles_m30: list[Candle] = []
    candles_h1: list[Candle] = []
    candles_h4: list[Candle] = []
    candles_d1: list[Candle] = []
    session: str               # london | new_york | tokyo | sydney | overlap | closed
    snapshot_time: datetime

from __future__ import annotations

from abc import ABC, abstractmethod

from openforexai.models.account import AccountStatus
from openforexai.models.market import Candle
from openforexai.models.trade import Position, TradeOrder, TradeResult


class AbstractBroker(ABC):
    """Port: every broker adapter must implement this contract.

    The adapter exposes only pure data/order primitives.  The background
    loops (M5 streaming, account polling, order-book sync) live in the base
    class ``BrokerBase`` (adapters/brokers/base.py) and call these methods.

    Naming convention
    -----------------
    Each adapter instance has a ``short_name`` that is used throughout the
    system to identify data and order-book entries.  The same broker type
    can be connected multiple times with different accounts by giving each
    instance a unique short_name (e.g. "OANDA_DEMO", "OANDA_LIVE").

    Table names derive from short_name::

        {short_name}_{pair}_{timeframe}   →  OANDA_DEMO_EURUSD_M5
    """

    # ── Identity ──────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def short_name(self) -> str:
        """Unique identifier for this broker instance, e.g. 'OANDA_DEMO'."""
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection / authenticate.  Called once at startup."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close the connection."""
        ...

    # ── Market data ───────────────────────────────────────────────────────────

    @abstractmethod
    async def fetch_latest_m5_candle(self, pair: str) -> Candle | None:
        """Return the most recently *completed* M5 candle for *pair*.

        Called by the M5 streaming loop every 5 minutes.  Must return None
        if the candle is not yet available rather than raising.
        """
        ...

    @abstractmethod
    async def get_historical_m5_candles(self, pair: str, count: int) -> list[Candle]:
        """Fetch up to *count* historical M5 candles, oldest first.

        Used during initial load and gap repair.  Only M5 is fetched from
        the broker; all other timeframes are derived by the DataContainer.
        """
        ...

    # ── Account ───────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_account_status(self) -> AccountStatus:
        """Return a fresh AccountStatus snapshot.

        Fields required: balance, equity, margin, margin_free, leverage,
        currency, trade_allowed, margin_level.
        """
        ...

    # ── Orders / positions ────────────────────────────────────────────────────

    @abstractmethod
    async def place_order(self, order: TradeOrder) -> TradeResult:
        """Submit an order to the broker.

        The order_type field on *order* determines which order variant is
        sent.  Implementations should raise NotImplementedError for order
        types they do not support (e.g. TRAILING_STOP on MT5).
        """
        ...

    @abstractmethod
    async def close_position(self, position_id: str) -> TradeResult:
        """Close an open position identified by its broker-side ID."""
        ...

    @abstractmethod
    async def get_open_positions(self) -> list[Position]:
        """Return all currently open positions at the broker.

        Used by the order-book sync loop to detect SL/TP hits.
        """
        ...


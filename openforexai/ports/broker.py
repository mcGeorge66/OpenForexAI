from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

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
    async def modify_position(
        self,
        position_id: str,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> TradeResult:
        """Modify the SL/TP limits of an open position identified by its broker-side ID."""
        ...

    @abstractmethod
    async def close_position(self, position_id: str, units: int | None = None, pair: str | None = None) -> TradeResult:
        """Close an open position fully or partially, identified by its broker-side ID."""
        ...

    @abstractmethod
    async def get_open_positions(self) -> list[Position]:
        """Return all currently open positions at the broker.

        Used by the order-book sync loop to detect SL/TP hits.
        """
        ...

    async def get_closed_trade_result(
        self,
        position_id: str,
        *,
        pair: str | None = None,
        sync_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Best-effort lookup for a broker-side closed trade result.

        Used when the sync loop notices that a once-open local order no longer
        exists at the broker. Implementations may return None if the broker does
        not expose the information cheaply enough.
        """
        return None

    async def find_closed_trade_by_sync_key(
        self,
        sync_key: str,
        pair: str | None = None,
    ) -> dict[str, Any] | None:
        """Search broker history for a closed trade matching *sync_key*.

        Used to recover orphaned PENDING entries that were filled and closed
        before the first sync ran (no broker_order_id stored locally).
        Returns the same structure as get_closed_trade_result plus
        'broker_order_id', or None if not found / not supported.
        """
        return None


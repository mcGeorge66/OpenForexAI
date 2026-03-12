from __future__ import annotations

from abc import ABC, abstractmethod

from openforexai.models.account import AccountStatus
from openforexai.models.agent import AgentDecision
from openforexai.models.market import Candle
from openforexai.models.optimization import BacktestResult, PromptCandidate, TradePattern
from openforexai.models.trade import OrderBookEntry


class AbstractRepository(ABC):
    """Port: all database adapters must implement this unified interface.

    Table naming for candles
    ------------------------
    Every (broker_name, pair, timeframe) combination maps to its own table::

        {broker_name}_{pair}_{timeframe}  →  OANDA_DEMO_EURUSD_M5

    The adapter is responsible for creating the table on first write if it
    does not already exist.  Higher timeframes (M15, M30, H1, H4, D1) are
    managed the same way — their population strategy depends on the backend:
    PostgreSQL uses triggers; SQLite uses the adapter itself.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Create all required tables / schemas.  Idempotent."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release connections and clean up."""
        ...

    # ── Candle storage ────────────────────────────────────────────────────────

    @abstractmethod
    async def save_candle(
        self, broker_name: str, pair: str, candle: Candle
    ) -> None:
        """Insert or upsert a single candle.

        Table name: {broker_name}_{pair}_{candle.timeframe}
        """
        ...

    @abstractmethod
    async def save_candles_bulk(
        self, broker_name: str, pair: str, candles: list[Candle]
    ) -> None:
        """Bulk-insert / upsert candles.  All candles must share the same timeframe."""
        ...

    @abstractmethod
    async def get_candles(
        self,
        broker_name: str,
        pair: str,
        timeframe: str,
        limit: int = 500,
    ) -> list[Candle]:
        """Return up to *limit* candles (newest first) from the persistent store."""
        ...

    @abstractmethod
    async def get_candle_count(self, broker_name: str, pair: str, timeframe: str) -> int:
        """Return the number of stored candles for a given series."""
        ...

    # ── Account status ────────────────────────────────────────────────────────

    @abstractmethod
    async def save_account_status(self, status: AccountStatus) -> None:
        """Persist an account snapshot.  One row per (broker_name, recorded_at)."""
        ...

    @abstractmethod
    async def get_latest_account_status(
        self, broker_name: str
    ) -> AccountStatus | None:
        """Return the most recent account snapshot for *broker_name*."""
        ...

    # ── Order book ────────────────────────────────────────────────────────────

    @abstractmethod
    async def save_order_book_entry(self, entry: OrderBookEntry) -> str:
        """Insert a new order book entry.  Returns the entry UUID as string."""
        ...

    @abstractmethod
    async def update_order_book_entry(
        self, entry_id: str, updates: dict
    ) -> None:
        """Apply a partial update (dict of field → value) to an existing entry."""
        ...

    @abstractmethod
    async def get_order_book_entry(self, entry_id: str) -> OrderBookEntry | None:
        """Load a single order book entry by its UUID."""
        ...

    @abstractmethod
    async def get_open_order_book_entries(
        self, broker_name: str, pair: str | None = None
    ) -> list[OrderBookEntry]:
        """Return all entries with status PENDING or OPEN for a given broker.

        Optionally filter by *pair*.  Used by the sync loop to detect positions
        that were closed broker-side.
        """
        ...

    @abstractmethod
    async def get_order_book_entries(
        self,
        broker_name: str,
        pair: str | None = None,
        limit: int = 200,
    ) -> list[OrderBookEntry]:
        """Return order book entries (newest first).

        Used by the OptimizationAgent to analyse historical trading decisions.
        Optionally filter by *pair*.
        """
        ...

    # ── Agent decisions ───────────────────────────────────────────────────────

    @abstractmethod
    async def save_agent_decision(self, decision: AgentDecision) -> str: ...

    # ── Optimization ─────────────────────────────────────────────────────────

    @abstractmethod
    async def save_pattern(self, pattern: TradePattern) -> str: ...

    @abstractmethod
    async def get_patterns(
        self, pair: str | None = None, limit: int = 100
    ) -> list[TradePattern]: ...

    @abstractmethod
    async def save_prompt_candidate(self, candidate: PromptCandidate) -> str: ...

    @abstractmethod
    async def get_best_prompt(self, pair: str) -> PromptCandidate | None: ...

    @abstractmethod
    async def get_prompt_candidates(self, pair: str) -> list[PromptCandidate]: ...

    @abstractmethod
    async def save_backtest_result(self, result: BacktestResult) -> str: ...




from __future__ import annotations

from abc import ABC, abstractmethod

from openforexai.models.agent import AgentDecision
from openforexai.models.optimization import BacktestResult, PromptCandidate, TradePattern
from openforexai.models.trade import TradeResult


class AbstractRepository(ABC):
    """Port: all DB adapters implement this unified repository interface."""

    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    # ── Trades ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def save_trade(self, trade: TradeResult) -> str: ...

    @abstractmethod
    async def get_trades(
        self, pair: str | None = None, limit: int = 500
    ) -> list[TradeResult]: ...

    # ── Agent decisions ──────────────────────────────────────────────────────

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

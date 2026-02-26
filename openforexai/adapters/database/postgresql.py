from __future__ import annotations

# PostgreSQL adapter skeleton — uses asyncpg under the hood.
# Full implementation mirrors SQLiteRepository; swap aiosqlite for asyncpg
# and adjust placeholder syntax (? -> $1, $2, ...).

from openforexai.models.agent import AgentDecision
from openforexai.models.optimization import BacktestResult, PromptCandidate, TradePattern
from openforexai.models.trade import TradeResult
from openforexai.ports.database import AbstractRepository


class PostgreSQLRepository(AbstractRepository):
    """Async PostgreSQL repository using asyncpg."""

    def __init__(self, database_url: str, pool_size: int = 5) -> None:
        self._database_url = database_url
        self._pool_size = pool_size
        self._pool: object | None = None

    async def initialize(self) -> None:
        import asyncpg  # type: ignore[import]

        self._pool = await asyncpg.create_pool(
            dsn=self._database_url, min_size=1, max_size=self._pool_size
        )
        # TODO: run migrations via asyncpg

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()  # type: ignore[union-attr]

    async def save_trade(self, trade: TradeResult) -> str:
        raise NotImplementedError("PostgreSQLRepository.save_trade not yet implemented")

    async def get_trades(
        self, pair: str | None = None, limit: int = 500
    ) -> list[TradeResult]:
        raise NotImplementedError

    async def save_agent_decision(self, decision: AgentDecision) -> str:
        raise NotImplementedError

    async def save_pattern(self, pattern: TradePattern) -> str:
        raise NotImplementedError

    async def get_patterns(
        self, pair: str | None = None, limit: int = 100
    ) -> list[TradePattern]:
        raise NotImplementedError

    async def save_prompt_candidate(self, candidate: PromptCandidate) -> str:
        raise NotImplementedError

    async def get_best_prompt(self, pair: str) -> PromptCandidate | None:
        raise NotImplementedError

    async def get_prompt_candidates(self, pair: str) -> list[PromptCandidate]:
        raise NotImplementedError

    async def save_backtest_result(self, result: BacktestResult) -> str:
        raise NotImplementedError

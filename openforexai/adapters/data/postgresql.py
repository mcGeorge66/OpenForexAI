"""PostgreSQLDataContainer — unified persistent data store backed by PostgreSQL.

This adapter extends PostgreSQLRepository (which itself extends AbstractRepository)
and adds the agent memory methods required by AbstractDataContainer.

Implementation status: the candle / account / order / trade / optimization methods
from the old PostgreSQLRepository are stubs that raise NotImplementedError.
Full implementation follows the same pattern as SQLiteDataContainer but uses
asyncpg with $1/$2/… placeholders instead of ?.

Self-registers at import time:

    PluginRegistry.register_data_container("postgresql", PostgreSQLDataContainer)
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from openforexai.adapters.database.postgresql import PostgreSQLRepository
from openforexai.ports.data_container import AbstractDataContainer


class PostgreSQLDataContainer(PostgreSQLRepository, AbstractDataContainer):
    """PostgreSQL implementation of AbstractDataContainer.

    Inherits the (stub) candle / account / order / trade / optimization methods
    from PostgreSQLRepository and adds full agent memory implementations.

    The agent memory methods use asyncpg directly via self._pool.

    NOTE: All candle / trade / order methods still raise NotImplementedError
    until the full PostgreSQL adapter is implemented.  Agent memory methods are
    fully implemented and ready to use.
    """

    # ── Agent decision memory ──────────────────────────────────────────────────

    async def save_agent_decision_with_reasoning(
        self,
        agent_id: str,
        pair: str | None,
        decision_type: str,
        reasoning: str,
        llm_model: str,
        input_tokens: int,
        output_tokens: int,
        market_snapshot: dict,
        prompt_version: str | None = None,
        latency_ms: float | None = None,
        decided_at: datetime | None = None,
    ) -> str:
        """Insert a full agent decision record.  Returns the UUID string."""
        record_id = str(uuid.uuid4())
        ts = (decided_at or datetime.now(UTC)).isoformat()
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                """
                INSERT INTO agent_decisions (
                    id, agent_id, agent_role, pair, decision_type,
                    decision_type_new, input_context, output,
                    llm_model, tokens_used, latency_ms, decided_at,
                    reasoning, market_snapshot
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                ON CONFLICT (id) DO NOTHING
                """,
                record_id,
                agent_id,
                "trading",
                pair,
                decision_type,
                decision_type,
                "{}",
                "{}",
                llm_model,
                input_tokens + output_tokens,
                latency_ms,
                ts,
                reasoning,
                json.dumps(market_snapshot, default=str, ensure_ascii=False),
            )
        return record_id

    async def get_recent_agent_decisions(
        self,
        agent_id: str,
        limit: int = 20,
        pair: str | None = None,
    ) -> list[dict]:
        """Return recent decisions for *agent_id*, newest first."""
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            if pair:
                rows = await conn.fetch(
                    """
                    SELECT id, agent_id, pair, decision_type_new AS decision_type,
                           reasoning, market_snapshot, llm_model,
                           tokens_used, latency_ms, decided_at
                    FROM agent_decisions
                    WHERE agent_id=$1 AND pair=$2
                    ORDER BY decided_at DESC LIMIT $3
                    """,
                    agent_id, pair, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, agent_id, pair, decision_type_new AS decision_type,
                           reasoning, market_snapshot, llm_model,
                           tokens_used, latency_ms, decided_at
                    FROM agent_decisions
                    WHERE agent_id=$1
                    ORDER BY decided_at DESC LIMIT $2
                    """,
                    agent_id, limit,
                )
        result = []
        for row in rows:
            r = dict(row)
            try:
                r["market_snapshot"] = json.loads(r["market_snapshot"]) if r.get("market_snapshot") else {}
            except (json.JSONDecodeError, TypeError):
                r["market_snapshot"] = {}
            result.append(r)
        return result

    # ── LLM conversation memory ────────────────────────────────────────────────

    async def save_llm_conversation(
        self,
        agent_id: str,
        session_id: str,
        messages: list[dict],
        turn_count: int,
        started_at: datetime | None = None,
    ) -> None:
        """Upsert the complete LLM messages list for one trading cycle."""
        now = datetime.now(UTC).isoformat()
        start = (started_at or datetime.now(UTC)).isoformat()
        record_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                """
                INSERT INTO agent_conversations
                    (id, agent_id, session_id, messages, turn_count, started_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (agent_id, session_id) DO UPDATE SET
                    messages   = EXCLUDED.messages,
                    turn_count = EXCLUDED.turn_count,
                    updated_at = EXCLUDED.updated_at
                """,
                record_id,
                agent_id,
                session_id,
                json.dumps(messages, default=str, ensure_ascii=False),
                turn_count,
                start,
                now,
            )

    async def get_last_llm_conversation(
        self,
        agent_id: str,
    ) -> list[dict] | None:
        """Return the messages list from the most recent session, or None."""
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            row = await conn.fetchrow(
                """
                SELECT messages FROM agent_conversations
                WHERE agent_id=$1
                ORDER BY updated_at DESC LIMIT 1
                """,
                agent_id,
            )
        if not row:
            return None
        try:
            return json.loads(row["messages"])
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    # ── Performance metrics ────────────────────────────────────────────────────

    async def save_performance_snapshot(
        self,
        agent_id: str,
        pair: str,
        total_decisions: int,
        trades_opened: int,
        trades_closed: int,
        win_count: int,
        loss_count: int,
        total_pnl: float,
        period_start: datetime,
        period_end: datetime,
    ) -> None:
        """Append a performance snapshot."""
        record_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                """
                INSERT INTO agent_performance (
                    id, agent_id, pair,
                    total_decisions, trades_opened, trades_closed,
                    win_count, loss_count, total_pnl,
                    period_start, period_end, recorded_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """,
                record_id, agent_id, pair,
                total_decisions, trades_opened, trades_closed,
                win_count, loss_count, float(total_pnl),
                period_start.isoformat(), period_end.isoformat(), now,
            )

    async def get_performance_summary(
        self,
        agent_id: str,
        pair: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return performance snapshots, newest first."""
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            if pair and since:
                rows = await conn.fetch(
                    (
                        "SELECT * FROM agent_performance "
                        "WHERE agent_id=$1 AND pair=$2 AND recorded_at>=$3 "
                        "ORDER BY recorded_at DESC LIMIT $4"
                    ),
                    agent_id, pair, since.isoformat(), limit,
                )
            elif pair:
                rows = await conn.fetch(
                    "SELECT * FROM agent_performance WHERE agent_id=$1 AND pair=$2 ORDER BY recorded_at DESC LIMIT $3",
                    agent_id, pair, limit,
                )
            elif since:
                rows = await conn.fetch(
                    (
                        "SELECT * FROM agent_performance "
                        "WHERE agent_id=$1 AND recorded_at>=$2 "
                        "ORDER BY recorded_at DESC LIMIT $3"
                    ),
                    agent_id, since.isoformat(), limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM agent_performance WHERE agent_id=$1 ORDER BY recorded_at DESC LIMIT $2",
                    agent_id, limit,
                )
        return [dict(r) for r in rows]


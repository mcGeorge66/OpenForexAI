"""SQLiteDataContainer — unified persistent data store backed by SQLite.

Extends SQLiteRepository with agent memory methods (decision reasoning,
LLM conversation history, performance snapshots).

Self-registers at import time:

    PluginRegistry.register_data_container("sqlite", SQLiteDataContainer)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from openforexai.adapters.database.sqlite import SQLiteRepository
from openforexai.ports.data_container import AbstractDataContainer


class SQLiteDataContainer(SQLiteRepository, AbstractDataContainer):
    """SQLite implementation of AbstractDataContainer.

    Inherits all candle / account / order / trade / optimization methods from
    SQLiteRepository.  Adds agent memory persistence (decisions, conversations,
    performance).

    SQLite WAL mode is enabled on first connection for better concurrent access.
    All writes use ``await self._db().commit()`` immediately — no data is held in
    an uncommitted transaction.
    """

    async def initialize(self) -> None:
        """Initialize connection and run all migrations (001, 002, 003 …)."""
        await super().initialize()
        # Enable WAL mode for better crash-safety and concurrent reads
        await self._db().execute("PRAGMA journal_mode=WAL")
        await self._db().execute("PRAGMA synchronous=FULL")
        await self._db().commit()

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
        ts = (decided_at or datetime.now(timezone.utc)).isoformat()
        await self._db().execute(
            """
            INSERT INTO agent_decisions (
                id, agent_id, agent_role, pair, decision_type,
                decision_type_new, input_context, output,
                llm_model, tokens_used, latency_ms, decided_at,
                reasoning, market_snapshot
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record_id,
                agent_id,
                "trading",                      # agent_role (legacy field)
                pair,
                decision_type,                  # legacy decision_type
                decision_type,                  # new decision_type_new
                json.dumps({}),                 # input_context (legacy, kept for compat)
                json.dumps({}),                 # output (legacy, kept for compat)
                llm_model,
                input_tokens + output_tokens,   # tokens_used = total
                latency_ms,
                ts,
                reasoning,                      # complete LLM text — no truncation
                json.dumps(market_snapshot),    # complete market context — no truncation
            ),
        )
        await self._db().commit()
        return record_id

    async def get_recent_agent_decisions(
        self,
        agent_id: str,
        limit: int = 20,
        pair: str | None = None,
    ) -> list[dict]:
        """Return recent decisions for *agent_id*, newest first."""
        if pair:
            cursor = await self._db().execute(
                """
                SELECT id, agent_id, pair, decision_type_new AS decision_type,
                       reasoning, market_snapshot, llm_model,
                       tokens_used, latency_ms, decided_at
                FROM agent_decisions
                WHERE agent_id=? AND pair=?
                ORDER BY decided_at DESC
                LIMIT ?
                """,
                (agent_id, pair, limit),
            )
        else:
            cursor = await self._db().execute(
                """
                SELECT id, agent_id, pair, decision_type_new AS decision_type,
                       reasoning, market_snapshot, llm_model,
                       tokens_used, latency_ms, decided_at
                FROM agent_decisions
                WHERE agent_id=?
                ORDER BY decided_at DESC
                LIMIT ?
                """,
                (agent_id, limit),
            )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            r = dict(row)
            # Deserialize JSON fields
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
        now = datetime.now(timezone.utc).isoformat()
        start = (started_at or datetime.now(timezone.utc)).isoformat()
        record_id = str(uuid.uuid4())
        await self._db().execute(
            """
            INSERT INTO agent_conversations
                (id, agent_id, session_id, messages, turn_count, started_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(agent_id, session_id) DO UPDATE SET
                messages   = excluded.messages,
                turn_count = excluded.turn_count,
                updated_at = excluded.updated_at
            """,
            (
                record_id,
                agent_id,
                session_id,
                json.dumps(messages, default=str, ensure_ascii=False),  # full list, no truncation
                turn_count,
                start,
                now,
            ),
        )
        await self._db().commit()

    async def get_last_llm_conversation(
        self,
        agent_id: str,
    ) -> list[dict] | None:
        """Return the messages list from the most recent session, or None."""
        cursor = await self._db().execute(
            """
            SELECT messages FROM agent_conversations
            WHERE agent_id=?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (agent_id,),
        )
        row = await cursor.fetchone()
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
        """Append a performance snapshot (append-only, never updated)."""
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self._db().execute(
            """
            INSERT INTO agent_performance (
                id, agent_id, pair,
                total_decisions, trades_opened, trades_closed,
                win_count, loss_count, total_pnl,
                period_start, period_end, recorded_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record_id,
                agent_id,
                pair,
                total_decisions,
                trades_opened,
                trades_closed,
                win_count,
                loss_count,
                float(total_pnl),
                period_start.isoformat(),
                period_end.isoformat(),
                now,
            ),
        )
        await self._db().commit()

    async def get_performance_summary(
        self,
        agent_id: str,
        pair: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return performance snapshots, newest first."""
        params: list = [agent_id]
        where = ["agent_id=?"]
        if pair:
            where.append("pair=?")
            params.append(pair)
        if since:
            where.append("recorded_at>=?")
            params.append(since.isoformat())
        params.append(limit)

        cursor = await self._db().execute(
            f"""
            SELECT * FROM agent_performance
            WHERE {' AND '.join(where)}
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

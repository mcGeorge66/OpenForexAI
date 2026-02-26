from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import aiosqlite

from openforexai.models.agent import AgentDecision, AgentRole
from openforexai.models.optimization import BacktestResult, PromptCandidate, TradePattern
from openforexai.models.trade import (
    TradeDirection,
    TradeOrder,
    TradeResult,
    TradeSignal,
    TradeStatus,
)
from openforexai.ports.database import AbstractRepository


class SQLiteRepository(AbstractRepository):
    """Async SQLite repository using aiosqlite."""

    def __init__(self, db_path: str = "./data/openforexai.db") -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._run_migrations()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteRepository: call initialize() first")
        return self._conn

    async def _run_migrations(self) -> None:
        migrations_dir = Path(__file__).parent.parent.parent.parent / "migrations"
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            sql = sql_file.read_text()
            await self._db().executescript(sql)
        await self._db().commit()

    # ── Trades ──────────────────────────────────────────────────────────────

    async def save_trade(self, trade: TradeResult) -> str:
        trade_id = str(trade.id)
        signal = trade.order.signal
        await self._db().execute(
            """
            INSERT OR REPLACE INTO trades (
                id, pair, direction, units, entry_price, stop_loss, take_profit,
                fill_price, pnl, status, opened_at, closed_at, close_reason,
                agent_id, broker_order_id, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                trade_id,
                signal.pair,
                signal.direction.value,
                trade.order.units,
                str(signal.entry_price),
                str(signal.stop_loss),
                str(signal.take_profit),
                str(trade.fill_price) if trade.fill_price else None,
                str(trade.pnl) if trade.pnl else None,
                trade.status.value,
                trade.opened_at.isoformat() if trade.opened_at else None,
                trade.closed_at.isoformat() if trade.closed_at else None,
                trade.close_reason,
                signal.agent_id,
                trade.broker_order_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await self._db().commit()
        return trade_id

    async def get_trades(
        self, pair: str | None = None, limit: int = 500
    ) -> list[TradeResult]:
        if pair:
            cursor = await self._db().execute(
                "SELECT * FROM trades WHERE pair=? ORDER BY created_at DESC LIMIT ?",
                (pair, limit),
            )
        else:
            cursor = await self._db().execute(
                "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        return [self._row_to_trade_result(r) for r in rows]

    def _row_to_trade_result(self, row: aiosqlite.Row) -> TradeResult:
        r = dict(row)
        signal = TradeSignal(
            pair=r["pair"],
            direction=TradeDirection(r["direction"]),
            entry_price=Decimal(r["entry_price"]),
            stop_loss=Decimal(r["stop_loss"]),
            take_profit=Decimal(r["take_profit"]),
            confidence=0.0,
            reasoning="",
            generated_at=datetime.now(timezone.utc),
            agent_id=r["agent_id"],
        )
        order = TradeOrder(signal=signal, units=r["units"], risk_pct=0.0, approved_by="supervisor")
        return TradeResult(
            id=uuid.UUID(r["id"]),
            order=order,
            broker_order_id=r.get("broker_order_id") or "",
            status=TradeStatus(r["status"]),
            fill_price=Decimal(r["fill_price"]) if r.get("fill_price") else None,
            pnl=Decimal(r["pnl"]) if r.get("pnl") else None,
            opened_at=datetime.fromisoformat(r["opened_at"]) if r.get("opened_at") else None,
            closed_at=datetime.fromisoformat(r["closed_at"]) if r.get("closed_at") else None,
            close_reason=r.get("close_reason"),
        )

    # ── Agent decisions ──────────────────────────────────────────────────────

    async def save_agent_decision(self, decision: AgentDecision) -> str:
        decision_id = str(decision.id)
        await self._db().execute(
            """
            INSERT OR REPLACE INTO agent_decisions (
                id, agent_id, agent_role, pair, decision_type,
                input_context, output, llm_model, tokens_used, latency_ms, decided_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                decision_id,
                decision.agent_id,
                decision.agent_role.value,
                decision.pair,
                decision.decision_type,
                json.dumps(decision.input_context),
                json.dumps(decision.output),
                decision.llm_model,
                decision.tokens_used,
                decision.latency_ms,
                decision.decided_at.isoformat(),
            ),
        )
        await self._db().commit()
        return decision_id

    # ── Optimization ─────────────────────────────────────────────────────────

    async def save_pattern(self, pattern: TradePattern) -> str:
        pattern_id = str(pattern.id)
        await self._db().execute(
            """
            INSERT OR REPLACE INTO trade_patterns (
                id, pair, pattern_type, description, frequency,
                win_rate_when_present, avg_pnl_when_present, conditions,
                detected_at, sample_size
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pattern_id,
                pattern.pair,
                pattern.pattern_type,
                pattern.description,
                pattern.frequency,
                pattern.win_rate_when_present,
                pattern.avg_pnl_when_present,
                json.dumps(pattern.conditions),
                pattern.detected_at.isoformat(),
                pattern.sample_size,
            ),
        )
        await self._db().commit()
        return pattern_id

    async def get_patterns(
        self, pair: str | None = None, limit: int = 100
    ) -> list[TradePattern]:
        if pair:
            cursor = await self._db().execute(
                "SELECT * FROM trade_patterns WHERE pair=? ORDER BY detected_at DESC LIMIT ?",
                (pair, limit),
            )
        else:
            cursor = await self._db().execute(
                "SELECT * FROM trade_patterns ORDER BY detected_at DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        return [
            TradePattern(
                id=uuid.UUID(r["id"]),
                pair=r["pair"],
                pattern_type=r["pattern_type"],
                description=r["description"],
                frequency=r["frequency"],
                win_rate_when_present=r["win_rate_when_present"],
                avg_pnl_when_present=r["avg_pnl_when_present"],
                conditions=json.loads(r["conditions"]),
                detected_at=datetime.fromisoformat(r["detected_at"]),
                sample_size=r["sample_size"],
            )
            for r in rows
        ]

    async def save_prompt_candidate(self, candidate: PromptCandidate) -> str:
        cid = str(candidate.id)
        await self._db().execute(
            """
            INSERT OR REPLACE INTO prompt_candidates (
                id, pair, version, system_prompt, rationale,
                source_patterns, is_active, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                cid,
                candidate.pair,
                candidate.version,
                candidate.system_prompt,
                candidate.rationale,
                json.dumps(candidate.source_patterns),
                int(candidate.is_active),
                candidate.created_at.isoformat(),
            ),
        )
        await self._db().commit()
        return cid

    async def get_best_prompt(self, pair: str) -> PromptCandidate | None:
        cursor = await self._db().execute(
            "SELECT * FROM prompt_candidates WHERE pair=? AND is_active=1 ORDER BY version DESC LIMIT 1",
            (pair,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        r = dict(row)
        return PromptCandidate(
            id=uuid.UUID(r["id"]),
            pair=r["pair"],
            version=r["version"],
            system_prompt=r["system_prompt"],
            rationale=r["rationale"],
            source_patterns=json.loads(r["source_patterns"]),
            is_active=bool(r["is_active"]),
            created_at=datetime.fromisoformat(r["created_at"]),
        )

    async def get_prompt_candidates(self, pair: str) -> list[PromptCandidate]:
        cursor = await self._db().execute(
            "SELECT * FROM prompt_candidates WHERE pair=? ORDER BY version DESC",
            (pair,),
        )
        rows = await cursor.fetchall()
        return [
            PromptCandidate(
                id=uuid.UUID(r["id"]),
                pair=r["pair"],
                version=r["version"],
                system_prompt=r["system_prompt"],
                rationale=r["rationale"],
                source_patterns=json.loads(r["source_patterns"]),
                is_active=bool(r["is_active"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    async def save_backtest_result(self, result: BacktestResult) -> str:
        rid = str(result.id)
        await self._db().execute(
            """
            INSERT OR REPLACE INTO backtest_results (
                id, prompt_candidate_id, pair, period_start, period_end,
                total_trades, win_rate, total_pnl, max_drawdown, sharpe_ratio,
                vs_baseline_pnl_delta, completed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                rid,
                result.prompt_candidate_id,
                result.pair,
                result.period_start.isoformat(),
                result.period_end.isoformat(),
                result.total_trades,
                result.win_rate,
                result.total_pnl,
                result.max_drawdown,
                result.sharpe_ratio,
                result.vs_baseline_pnl_delta,
                result.completed_at.isoformat(),
            ),
        )
        await self._db().commit()
        return rid

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from openforexai.models.account import AccountStatus
from openforexai.models.agent import AgentDecision
from openforexai.models.market import Candle
from openforexai.models.optimization import BacktestResult, PromptCandidate, TradePattern
from openforexai.models.trade import (
    CloseReason,
    OrderBookEntry,
    OrderStatus,
    TradeDirection,
    TradeOrder,
    TradeResult,
    TradeSignal,
    TradeStatus,
)
from openforexai.ports.database import AbstractRepository


class PostgreSQLRepository(AbstractRepository):
    """Async PostgreSQL repository using asyncpg.

    Feature parity target: mirrors SQLiteRepository behavior.
    """

    def __init__(self, database_url: str, pool_size: int = 5) -> None:
        self._database_url = database_url
        self._pool_size = pool_size
        self._pool: Any | None = None

    async def initialize(self) -> None:
        import asyncpg  # type: ignore[import]

        self._pool = await asyncpg.create_pool(
            dsn=self._database_url,
            min_size=1,
            max_size=self._pool_size,
        )
        await self._ensure_core_tables()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _p(self) -> Any:
        if self._pool is None:
            raise RuntimeError("PostgreSQLRepository: call initialize() first")
        return self._pool

    async def _execute(self, sql: str, *args: Any) -> str:
        async with self._p().acquire() as conn:
            return await conn.execute(sql, *args)

    async def _fetch(self, sql: str, *args: Any) -> list[Any]:
        async with self._p().acquire() as conn:
            return await conn.fetch(sql, *args)

    async def _fetchrow(self, sql: str, *args: Any) -> Any:
        async with self._p().acquire() as conn:
            return await conn.fetchrow(sql, *args)

    async def _ensure_core_tables(self) -> None:
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id              TEXT PRIMARY KEY,
                pair            TEXT NOT NULL,
                direction       TEXT NOT NULL,
                units           INTEGER NOT NULL,
                entry_price     TEXT NOT NULL,
                stop_loss       TEXT NOT NULL,
                take_profit     TEXT NOT NULL,
                fill_price      TEXT,
                pnl             TEXT,
                status          TEXT NOT NULL,
                opened_at       TEXT,
                closed_at       TEXT,
                close_reason    TEXT,
                agent_id        TEXT NOT NULL,
                broker_order_id TEXT,
                created_at      TEXT NOT NULL
            )
            """
        )
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS agent_decisions (
                id            TEXT PRIMARY KEY,
                agent_id      TEXT NOT NULL,
                agent_role    TEXT NOT NULL,
                pair          TEXT,
                decision_type TEXT NOT NULL,
                input_context TEXT NOT NULL,
                output        TEXT NOT NULL,
                llm_model     TEXT NOT NULL,
                tokens_used   INTEGER,
                latency_ms    DOUBLE PRECISION,
                decided_at    TEXT NOT NULL
            )
            """
        )
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS trade_patterns (
                id                    TEXT PRIMARY KEY,
                pair                  TEXT NOT NULL,
                pattern_type          TEXT NOT NULL,
                description           TEXT,
                frequency             INTEGER,
                win_rate_when_present DOUBLE PRECISION,
                avg_pnl_when_present  DOUBLE PRECISION,
                conditions            TEXT,
                detected_at           TEXT NOT NULL,
                sample_size           INTEGER
            )
            """
        )
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_candidates (
                id              TEXT PRIMARY KEY,
                pair            TEXT NOT NULL,
                version         INTEGER NOT NULL,
                system_prompt   TEXT NOT NULL,
                rationale       TEXT,
                source_patterns TEXT,
                is_active       BOOLEAN DEFAULT FALSE,
                created_at      TEXT NOT NULL
            )
            """
        )
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_results (
                id                    TEXT PRIMARY KEY,
                prompt_candidate_id   TEXT NOT NULL,
                pair                  TEXT NOT NULL,
                period_start          TEXT,
                period_end            TEXT,
                total_trades          INTEGER,
                win_rate              DOUBLE PRECISION,
                total_pnl             DOUBLE PRECISION,
                max_drawdown          DOUBLE PRECISION,
                sharpe_ratio          DOUBLE PRECISION,
                vs_baseline_pnl_delta DOUBLE PRECISION,
                completed_at          TEXT NOT NULL
            )
            """
        )
        await self._ensure_account_status_table()
        await self._ensure_order_book_table()

    # ── Trades ──────────────────────────────────────────────────────────────

    async def save_trade(self, trade: TradeResult) -> str:
        trade_id = str(trade.id)
        signal = trade.order.signal
        await self._execute(
            """
            INSERT INTO trades (
                id, pair, direction, units, entry_price, stop_loss, take_profit,
                fill_price, pnl, status, opened_at, closed_at, close_reason,
                agent_id, broker_order_id, created_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16
            )
            ON CONFLICT (id) DO UPDATE SET
                pair=EXCLUDED.pair,
                direction=EXCLUDED.direction,
                units=EXCLUDED.units,
                entry_price=EXCLUDED.entry_price,
                stop_loss=EXCLUDED.stop_loss,
                take_profit=EXCLUDED.take_profit,
                fill_price=EXCLUDED.fill_price,
                pnl=EXCLUDED.pnl,
                status=EXCLUDED.status,
                opened_at=EXCLUDED.opened_at,
                closed_at=EXCLUDED.closed_at,
                close_reason=EXCLUDED.close_reason,
                agent_id=EXCLUDED.agent_id,
                broker_order_id=EXCLUDED.broker_order_id,
                created_at=EXCLUDED.created_at
            """,
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
            datetime.now(UTC).isoformat(),
        )
        return trade_id

    async def get_trades(self, pair: str | None = None, limit: int = 500) -> list[TradeResult]:
        if pair:
            rows = await self._fetch(
                "SELECT * FROM trades WHERE pair=$1 ORDER BY created_at DESC LIMIT $2",
                pair,
                limit,
            )
        else:
            rows = await self._fetch(
                "SELECT * FROM trades ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return [self._row_to_trade_result(dict(r)) for r in rows]

    def _row_to_trade_result(self, r: dict[str, Any]) -> TradeResult:
        signal = TradeSignal(
            pair=r["pair"],
            direction=TradeDirection(r["direction"]),
            entry_price=Decimal(r["entry_price"]),
            stop_loss=Decimal(r["stop_loss"]),
            take_profit=Decimal(r["take_profit"]),
            confidence=0.0,
            reasoning="",
            generated_at=datetime.now(UTC),
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
        await self._execute(
            """
            INSERT INTO agent_decisions (
                id, agent_id, agent_role, pair, decision_type,
                input_context, output, llm_model, tokens_used, latency_ms, decided_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (id) DO UPDATE SET
                agent_id=EXCLUDED.agent_id,
                agent_role=EXCLUDED.agent_role,
                pair=EXCLUDED.pair,
                decision_type=EXCLUDED.decision_type,
                input_context=EXCLUDED.input_context,
                output=EXCLUDED.output,
                llm_model=EXCLUDED.llm_model,
                tokens_used=EXCLUDED.tokens_used,
                latency_ms=EXCLUDED.latency_ms,
                decided_at=EXCLUDED.decided_at
            """,
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
        )
        return decision_id

    # ── Optimization ─────────────────────────────────────────────────────────

    async def save_pattern(self, pattern: TradePattern) -> str:
        pattern_id = str(pattern.id)
        await self._execute(
            """
            INSERT INTO trade_patterns (
                id, pair, pattern_type, description, frequency,
                win_rate_when_present, avg_pnl_when_present, conditions,
                detected_at, sample_size
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (id) DO UPDATE SET
                pair=EXCLUDED.pair,
                pattern_type=EXCLUDED.pattern_type,
                description=EXCLUDED.description,
                frequency=EXCLUDED.frequency,
                win_rate_when_present=EXCLUDED.win_rate_when_present,
                avg_pnl_when_present=EXCLUDED.avg_pnl_when_present,
                conditions=EXCLUDED.conditions,
                detected_at=EXCLUDED.detected_at,
                sample_size=EXCLUDED.sample_size
            """,
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
        )
        return pattern_id

    async def get_patterns(self, pair: str | None = None, limit: int = 100) -> list[TradePattern]:
        if pair:
            rows = await self._fetch(
                "SELECT * FROM trade_patterns WHERE pair=$1 ORDER BY detected_at DESC LIMIT $2",
                pair,
                limit,
            )
        else:
            rows = await self._fetch(
                "SELECT * FROM trade_patterns ORDER BY detected_at DESC LIMIT $1",
                limit,
            )
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
            for r in [dict(x) for x in rows]
        ]

    async def save_prompt_candidate(self, candidate: PromptCandidate) -> str:
        cid = str(candidate.id)
        await self._execute(
            """
            INSERT INTO prompt_candidates (
                id, pair, version, system_prompt, rationale,
                source_patterns, is_active, created_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (id) DO UPDATE SET
                pair=EXCLUDED.pair,
                version=EXCLUDED.version,
                system_prompt=EXCLUDED.system_prompt,
                rationale=EXCLUDED.rationale,
                source_patterns=EXCLUDED.source_patterns,
                is_active=EXCLUDED.is_active,
                created_at=EXCLUDED.created_at
            """,
            cid,
            candidate.pair,
            candidate.version,
            candidate.system_prompt,
            candidate.rationale,
            json.dumps(candidate.source_patterns),
            bool(candidate.is_active),
            candidate.created_at.isoformat(),
        )
        return cid

    async def get_best_prompt(self, pair: str) -> PromptCandidate | None:
        row = await self._fetchrow(
            """
            SELECT * FROM prompt_candidates
            WHERE pair=$1 AND is_active=TRUE
            ORDER BY version DESC
            LIMIT 1
            """,
            pair,
        )
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
        rows = await self._fetch(
            "SELECT * FROM prompt_candidates WHERE pair=$1 ORDER BY version DESC",
            pair,
        )
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
            for r in [dict(x) for x in rows]
        ]

    async def save_backtest_result(self, result: BacktestResult) -> str:
        rid = str(result.id)
        await self._execute(
            """
            INSERT INTO backtest_results (
                id, prompt_candidate_id, pair, period_start, period_end,
                total_trades, win_rate, total_pnl, max_drawdown, sharpe_ratio,
                vs_baseline_pnl_delta, completed_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            ON CONFLICT (id) DO UPDATE SET
                prompt_candidate_id=EXCLUDED.prompt_candidate_id,
                pair=EXCLUDED.pair,
                period_start=EXCLUDED.period_start,
                period_end=EXCLUDED.period_end,
                total_trades=EXCLUDED.total_trades,
                win_rate=EXCLUDED.win_rate,
                total_pnl=EXCLUDED.total_pnl,
                max_drawdown=EXCLUDED.max_drawdown,
                sharpe_ratio=EXCLUDED.sharpe_ratio,
                vs_baseline_pnl_delta=EXCLUDED.vs_baseline_pnl_delta,
                completed_at=EXCLUDED.completed_at
            """,
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
        )
        return rid

    # --- Dynamic candle series helpers ---

    @staticmethod
    def _series_table(broker_name: str, pair: str, timeframe: str) -> str:
        def _sanitize(s: str) -> str:
            return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in s)

        return f"{_sanitize(broker_name.upper())}_{_sanitize(pair.upper())}_{_sanitize(timeframe.upper())}"

    @staticmethod
    def _q_ident(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    async def _ensure_candle_table(self, broker_name: str, pair: str, timeframe: str) -> None:
        table = self._series_table(broker_name, pair, timeframe)
        table_ident = self._q_ident(table)
        await self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_ident} (
                timestamp   TEXT PRIMARY KEY,
                open        TEXT NOT NULL,
                high        TEXT NOT NULL,
                low         TEXT NOT NULL,
                close       TEXT NOT NULL,
                tick_volume INTEGER NOT NULL,
                spread      TEXT NOT NULL
            )
            """
        )

    async def _candle_table_exists(self, broker_name: str, pair: str, timeframe: str) -> bool:
        table = self._series_table(broker_name, pair, timeframe)
        row = await self._fetchrow(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = $1
            ) AS exists_flag
            """,
            table,
        )
        return bool(row["exists_flag"]) if row else False

    @staticmethod
    def _row_to_candle(row: dict[str, Any], timeframe: str) -> Candle:
        return Candle(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            open=Decimal(row["open"]),
            high=Decimal(row["high"]),
            low=Decimal(row["low"]),
            close=Decimal(row["close"]),
            tick_volume=int(row["tick_volume"]),
            spread=Decimal(row["spread"]),
            timeframe=timeframe,
        )

    # --- Candles ---

    async def save_candle(self, broker_name: str, pair: str, candle: Candle) -> None:
        await self._ensure_candle_table(broker_name, pair, candle.timeframe)
        table = self._q_ident(self._series_table(broker_name, pair, candle.timeframe))
        await self._execute(
            f"""
            INSERT INTO {table} (
                timestamp, open, high, low, close, tick_volume, spread
            ) VALUES ($1,$2,$3,$4,$5,$6,$7)
            ON CONFLICT (timestamp) DO UPDATE SET
                open=EXCLUDED.open,
                high=EXCLUDED.high,
                low=EXCLUDED.low,
                close=EXCLUDED.close,
                tick_volume=EXCLUDED.tick_volume,
                spread=EXCLUDED.spread
            """,
            candle.timestamp.isoformat(),
            str(candle.open),
            str(candle.high),
            str(candle.low),
            str(candle.close),
            candle.tick_volume,
            str(candle.spread),
        )

    async def save_candles_bulk(self, broker_name: str, pair: str, candles: list[Candle]) -> None:
        if not candles:
            return
        timeframe = candles[0].timeframe
        await self._ensure_candle_table(broker_name, pair, timeframe)
        table = self._q_ident(self._series_table(broker_name, pair, timeframe))
        sql = (
            f"INSERT INTO {table} "
            "(timestamp, open, high, low, close, tick_volume, spread) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7) "
            "ON CONFLICT (timestamp) DO UPDATE SET "
            "open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, "
            "close=EXCLUDED.close, tick_volume=EXCLUDED.tick_volume, spread=EXCLUDED.spread"
        )
        rows = [
            (
                c.timestamp.isoformat(),
                str(c.open),
                str(c.high),
                str(c.low),
                str(c.close),
                c.tick_volume,
                str(c.spread),
            )
            for c in candles
        ]
        async with self._p().acquire() as conn:
            async with conn.transaction():
                await conn.executemany(sql, rows)

    async def get_candles(
        self,
        broker_name: str,
        pair: str,
        timeframe: str,
        limit: int = 500,
    ) -> list[Candle]:
        if not await self._candle_table_exists(broker_name, pair, timeframe):
            return []
        table = self._q_ident(self._series_table(broker_name, pair, timeframe))
        rows = await self._fetch(
            f"SELECT * FROM {table} ORDER BY timestamp DESC LIMIT $1",
            limit,
        )
        return [self._row_to_candle(dict(r), timeframe) for r in rows]

    async def get_candle_count(self, broker_name: str, pair: str, timeframe: str) -> int:
        if not await self._candle_table_exists(broker_name, pair, timeframe):
            return 0
        table = self._q_ident(self._series_table(broker_name, pair, timeframe))
        row = await self._fetchrow(f"SELECT COUNT(*)::bigint AS c FROM {table}")
        return int(row["c"]) if row else 0

    # --- Account status ---

    async def _ensure_account_status_table(self) -> None:
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS account_status (
                broker_name   TEXT NOT NULL,
                balance       TEXT NOT NULL,
                equity        TEXT NOT NULL,
                margin        TEXT NOT NULL,
                margin_free   TEXT NOT NULL,
                leverage      INTEGER NOT NULL,
                currency      TEXT NOT NULL,
                trade_allowed BOOLEAN NOT NULL,
                margin_level  DOUBLE PRECISION,
                recorded_at   TEXT NOT NULL,
                PRIMARY KEY (broker_name, recorded_at)
            )
            """
        )

    async def save_account_status(self, status: AccountStatus) -> None:
        await self._ensure_account_status_table()
        await self._execute(
            """
            INSERT INTO account_status (
                broker_name, balance, equity, margin, margin_free,
                leverage, currency, trade_allowed, margin_level, recorded_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (broker_name, recorded_at) DO UPDATE SET
                balance=EXCLUDED.balance,
                equity=EXCLUDED.equity,
                margin=EXCLUDED.margin,
                margin_free=EXCLUDED.margin_free,
                leverage=EXCLUDED.leverage,
                currency=EXCLUDED.currency,
                trade_allowed=EXCLUDED.trade_allowed,
                margin_level=EXCLUDED.margin_level
            """,
            status.broker_name,
            str(status.balance),
            str(status.equity),
            str(status.margin),
            str(status.margin_free),
            int(status.leverage),
            status.currency,
            bool(status.trade_allowed),
            float(status.margin_level) if status.margin_level is not None else None,
            status.recorded_at.isoformat(),
        )

    async def get_latest_account_status(self, broker_name: str) -> AccountStatus | None:
        await self._ensure_account_status_table()
        row = await self._fetchrow(
            """
            SELECT * FROM account_status
            WHERE broker_name=$1
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            broker_name,
        )
        if not row:
            return None
        r = dict(row)
        return AccountStatus(
            broker_name=r["broker_name"],
            balance=Decimal(r["balance"]),
            equity=Decimal(r["equity"]),
            margin=Decimal(r["margin"]),
            margin_free=Decimal(r["margin_free"]),
            leverage=int(r["leverage"]),
            currency=r["currency"],
            trade_allowed=bool(r["trade_allowed"]),
            margin_level=float(r["margin_level"]) if r.get("margin_level") is not None else None,
            recorded_at=datetime.fromisoformat(r["recorded_at"]),
        )

    # --- Order book ---

    async def _ensure_order_book_table(self) -> None:
        await self._execute(
            """
            CREATE TABLE IF NOT EXISTS order_book_entries (
                id                     TEXT PRIMARY KEY,
                broker_name            TEXT NOT NULL,
                broker_order_id        TEXT,
                pair                   TEXT NOT NULL,
                direction              TEXT NOT NULL,
                order_type             TEXT NOT NULL,
                units                  INTEGER NOT NULL,
                requested_price        TEXT NOT NULL,
                fill_price             TEXT,
                stop_loss              TEXT,
                take_profit            TEXT,
                trailing_stop_distance TEXT,
                limit_price            TEXT,
                stop_price             TEXT,
                status                 TEXT NOT NULL,
                agent_id               TEXT NOT NULL,
                prompt_version         INTEGER,
                entry_reasoning        TEXT NOT NULL,
                signal_confidence      DOUBLE PRECISION NOT NULL,
                market_context_snapshot TEXT NOT NULL,
                requested_at           TEXT NOT NULL,
                opened_at              TEXT,
                closed_at              TEXT,
                last_broker_sync       TEXT,
                close_reason           TEXT,
                close_price            TEXT,
                close_reasoning        TEXT,
                pnl_pips               TEXT,
                pnl_account_currency   TEXT,
                sync_confirmed         BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )

    async def save_order_book_entry(self, entry: OrderBookEntry) -> str:
        await self._ensure_order_book_table()
        eid = str(entry.id)
        await self._execute(
            """
            INSERT INTO order_book_entries (
                id, broker_name, broker_order_id, pair, direction, order_type, units,
                requested_price, fill_price, stop_loss, take_profit, trailing_stop_distance,
                limit_price, stop_price, status, agent_id, prompt_version, entry_reasoning,
                signal_confidence, market_context_snapshot, requested_at, opened_at, closed_at,
                last_broker_sync, close_reason, close_price, close_reasoning, pnl_pips,
                pnl_account_currency, sync_confirmed
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                $21,$22,$23,$24,$25,$26,$27,$28,$29,$30
            )
            ON CONFLICT (id) DO UPDATE SET
                broker_name=EXCLUDED.broker_name,
                broker_order_id=EXCLUDED.broker_order_id,
                pair=EXCLUDED.pair,
                direction=EXCLUDED.direction,
                order_type=EXCLUDED.order_type,
                units=EXCLUDED.units,
                requested_price=EXCLUDED.requested_price,
                fill_price=EXCLUDED.fill_price,
                stop_loss=EXCLUDED.stop_loss,
                take_profit=EXCLUDED.take_profit,
                trailing_stop_distance=EXCLUDED.trailing_stop_distance,
                limit_price=EXCLUDED.limit_price,
                stop_price=EXCLUDED.stop_price,
                status=EXCLUDED.status,
                agent_id=EXCLUDED.agent_id,
                prompt_version=EXCLUDED.prompt_version,
                entry_reasoning=EXCLUDED.entry_reasoning,
                signal_confidence=EXCLUDED.signal_confidence,
                market_context_snapshot=EXCLUDED.market_context_snapshot,
                requested_at=EXCLUDED.requested_at,
                opened_at=EXCLUDED.opened_at,
                closed_at=EXCLUDED.closed_at,
                last_broker_sync=EXCLUDED.last_broker_sync,
                close_reason=EXCLUDED.close_reason,
                close_price=EXCLUDED.close_price,
                close_reasoning=EXCLUDED.close_reasoning,
                pnl_pips=EXCLUDED.pnl_pips,
                pnl_account_currency=EXCLUDED.pnl_account_currency,
                sync_confirmed=EXCLUDED.sync_confirmed
            """,
            eid,
            entry.broker_name,
            entry.broker_order_id,
            entry.pair,
            entry.direction.value,
            entry.order_type.value,
            entry.units,
            str(entry.requested_price),
            str(entry.fill_price) if entry.fill_price is not None else None,
            str(entry.stop_loss) if entry.stop_loss is not None else None,
            str(entry.take_profit) if entry.take_profit is not None else None,
            str(entry.trailing_stop_distance) if entry.trailing_stop_distance is not None else None,
            str(entry.limit_price) if entry.limit_price is not None else None,
            str(entry.stop_price) if entry.stop_price is not None else None,
            entry.status.value,
            entry.agent_id,
            entry.prompt_version,
            entry.entry_reasoning,
            float(entry.signal_confidence),
            json.dumps(entry.market_context_snapshot),
            entry.requested_at.isoformat(),
            entry.opened_at.isoformat() if entry.opened_at else None,
            entry.closed_at.isoformat() if entry.closed_at else None,
            entry.last_broker_sync.isoformat() if entry.last_broker_sync else None,
            (
                entry.close_reason.value
                if isinstance(entry.close_reason, CloseReason)
                else (entry.close_reason if entry.close_reason else None)
            ),
            str(entry.close_price) if entry.close_price is not None else None,
            entry.close_reasoning,
            str(entry.pnl_pips) if entry.pnl_pips is not None else None,
            str(entry.pnl_account_currency) if entry.pnl_account_currency is not None else None,
            bool(entry.sync_confirmed),
        )
        return eid

    async def update_order_book_entry(self, entry_id: str, updates: dict[str, Any]) -> None:
        await self._ensure_order_book_table()

        def _to_db(v: Any) -> Any:
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, Decimal):
                return str(v)
            if isinstance(v, bool):
                return v
            if isinstance(v, (CloseReason, OrderStatus)):
                return v.value
            if isinstance(v, dict):
                return json.dumps(v)
            return v

        items = list(updates.items())
        set_clause = ", ".join(f"{k}=${idx + 1}" for idx, (k, _) in enumerate(items))
        values = [_to_db(v) for _, v in items]
        values.append(entry_id)
        await self._execute(
            f"UPDATE order_book_entries SET {set_clause} WHERE id=${len(values)}",
            *values,
        )

    async def _row_to_order_book_entry(self, row: dict[str, Any]) -> OrderBookEntry:
        cr_val = row.get("close_reason")
        close_reason: CloseReason | str | None = None
        if cr_val:
            try:
                close_reason = CloseReason(cr_val)
            except ValueError:
                close_reason = cr_val

        from openforexai.models.trade import OrderType as _OrderType

        return OrderBookEntry(
            id=uuid.UUID(row["id"]),
            broker_name=row["broker_name"],
            broker_order_id=row.get("broker_order_id"),
            pair=row["pair"],
            direction=TradeDirection(row["direction"]),
            order_type=_OrderType(row["order_type"]),
            units=int(row["units"]),
            requested_price=Decimal(row["requested_price"]),
            fill_price=Decimal(row["fill_price"]) if row.get("fill_price") else None,
            stop_loss=Decimal(row["stop_loss"]) if row.get("stop_loss") else None,
            take_profit=Decimal(row["take_profit"]) if row.get("take_profit") else None,
            trailing_stop_distance=Decimal(row["trailing_stop_distance"]) if row.get("trailing_stop_distance") else None,
            limit_price=Decimal(row["limit_price"]) if row.get("limit_price") else None,
            stop_price=Decimal(row["stop_price"]) if row.get("stop_price") else None,
            status=OrderStatus(row["status"]),
            agent_id=row["agent_id"],
            prompt_version=row.get("prompt_version"),
            entry_reasoning=row["entry_reasoning"],
            signal_confidence=float(row["signal_confidence"]),
            market_context_snapshot=json.loads(row["market_context_snapshot"]),
            requested_at=datetime.fromisoformat(row["requested_at"]),
            opened_at=datetime.fromisoformat(row["opened_at"]) if row.get("opened_at") else None,
            closed_at=datetime.fromisoformat(row["closed_at"]) if row.get("closed_at") else None,
            last_broker_sync=datetime.fromisoformat(row["last_broker_sync"]) if row.get("last_broker_sync") else None,
            close_reason=close_reason,
            close_price=Decimal(row["close_price"]) if row.get("close_price") else None,
            close_reasoning=row.get("close_reasoning"),
            pnl_pips=Decimal(row["pnl_pips"]) if row.get("pnl_pips") else None,
            pnl_account_currency=Decimal(row["pnl_account_currency"]) if row.get("pnl_account_currency") else None,
            sync_confirmed=bool(row["sync_confirmed"]),
        )

    async def get_order_book_entry(self, entry_id: str) -> OrderBookEntry | None:
        await self._ensure_order_book_table()
        row = await self._fetchrow("SELECT * FROM order_book_entries WHERE id=$1", entry_id)
        return await self._row_to_order_book_entry(dict(row)) if row else None

    async def get_open_order_book_entries(
        self,
        broker_name: str,
        pair: str | None = None,
    ) -> list[OrderBookEntry]:
        await self._ensure_order_book_table()
        if pair:
            rows = await self._fetch(
                """
                SELECT * FROM order_book_entries
                WHERE broker_name=$1 AND pair=$2
                  AND status IN ('PENDING','OPEN','PARTIALLY_FILLED')
                ORDER BY requested_at DESC
                """,
                broker_name,
                pair,
            )
        else:
            rows = await self._fetch(
                """
                SELECT * FROM order_book_entries
                WHERE broker_name=$1
                  AND status IN ('PENDING','OPEN','PARTIALLY_FILLED')
                ORDER BY requested_at DESC
                """,
                broker_name,
            )
        return [await self._row_to_order_book_entry(dict(r)) for r in rows]

    async def get_order_book_entries(
        self,
        broker_name: str,
        pair: str | None = None,
        limit: int = 200,
    ) -> list[OrderBookEntry]:
        await self._ensure_order_book_table()
        if pair:
            rows = await self._fetch(
                """
                SELECT * FROM order_book_entries
                WHERE broker_name=$1 AND pair=$2
                ORDER BY requested_at DESC
                LIMIT $3
                """,
                broker_name,
                pair,
                limit,
            )
        else:
            rows = await self._fetch(
                """
                SELECT * FROM order_book_entries
                WHERE broker_name=$1
                ORDER BY requested_at DESC
                LIMIT $2
                """,
                broker_name,
                limit,
            )
        return [await self._row_to_order_book_entry(dict(r)) for r in rows]

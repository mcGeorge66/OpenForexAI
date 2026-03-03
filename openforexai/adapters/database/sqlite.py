from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import aiosqlite

from openforexai.models.agent import AgentDecision, AgentRole
from openforexai.models.market import Candle
from openforexai.models.account import AccountStatus
from openforexai.models.optimization import BacktestResult, PromptCandidate, TradePattern
from openforexai.models.trade import (
    CloseReason,
    OrderBookEntry,
    OrderStatus,
    OrderType,
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
        await self._db().executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        await self._db().commit()

        # Bootstrap: if schema_migrations is empty but the DB already has tables
        # from prior runs (before migration tracking was introduced), detect which
        # migrations have already been applied and register them without re-running.
        cursor = await self._db().execute("SELECT COUNT(*) FROM schema_migrations")
        row = await cursor.fetchone()
        if row and row[0] == 0:
            await self._bootstrap_migration_history()

        migrations_dir = Path(__file__).parent.parent.parent.parent / "migrations"
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            cursor = await self._db().execute(
                "SELECT 1 FROM schema_migrations WHERE filename=?",
                (sql_file.name,),
            )
            already_applied = await cursor.fetchone()
            if already_applied:
                continue

            sql = sql_file.read_text()
            await self._db().executescript(sql)
            await self._db().execute(
                "INSERT INTO schema_migrations (filename) VALUES (?)",
                (sql_file.name,),
            )
            await self._db().commit()

    async def _bootstrap_migration_history(self) -> None:
        """Pre-register migrations that were applied before tracking was introduced.

        Checks for observable proof that each migration was applied (table or
        column existence) and records it in schema_migrations without re-running.
        """
        # 001_initial_schema.sql — trades + agent_decisions tables
        cursor = await self._db().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trades'"
        )
        if await cursor.fetchone():
            await self._db().execute(
                "INSERT OR IGNORE INTO schema_migrations (filename) VALUES (?)",
                ("001_initial_schema.sql",),
            )

        # 002_optimization_tables.sql — trade_patterns + prompt_candidates + backtest_results
        cursor = await self._db().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_patterns'"
        )
        if await cursor.fetchone():
            await self._db().execute(
                "INSERT OR IGNORE INTO schema_migrations (filename) VALUES (?)",
                ("002_optimization_tables.sql",),
            )

        # 003_agent_memory.sql — reasoning column + agent_conversations + agent_performance
        cursor = await self._db().execute("PRAGMA table_info(agent_decisions)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "reasoning" in columns:
            await self._db().execute(
                "INSERT OR IGNORE INTO schema_migrations (filename) VALUES (?)",
                ("003_agent_memory.sql",),
            )

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

    # --- Dynamic candle series helpers ---

    @staticmethod
    def _series_table(broker_name: str, pair: str, timeframe: str) -> str:
        def _sanitize(s: str) -> str:
            return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in s)
        return f"{_sanitize(broker_name.upper())}_{_sanitize(pair.upper())}_{_sanitize(timeframe.upper())}"

    async def _ensure_candle_table(self, broker_name: str, pair: str, timeframe: str) -> None:
        table = self._series_table(broker_name, pair, timeframe)
        await self._db().execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                timestamp   TEXT PRIMARY KEY,
                open        TEXT NOT NULL,
                high        TEXT NOT NULL,
                low         TEXT NOT NULL,
                close       TEXT NOT NULL,
                tick_volume INTEGER NOT NULL,
                spread      TEXT NOT NULL
            );
            """
        )
        await self._db().commit()

    @staticmethod
    def _row_to_candle(row: aiosqlite.Row, timeframe: str) -> Candle:
        r = dict(row)
        return Candle(
            timestamp=datetime.fromisoformat(r["timestamp"]),
            open=Decimal(r["open"]),
            high=Decimal(r["high"]),
            low=Decimal(r["low"]),
            close=Decimal(r["close"]),
            tick_volume=int(r["tick_volume"]),
            spread=Decimal(r["spread"]),
            timeframe=timeframe,
        )

    # --- Candles ---

    async def save_candle(
        self, broker_name: str, pair: str, candle: Candle
    ) -> None:
        await self._ensure_candle_table(broker_name, pair, candle.timeframe)
        table = self._series_table(broker_name, pair, candle.timeframe)
        await self._db().execute(
            f"""
            INSERT OR REPLACE INTO {table} (
                timestamp, open, high, low, close, tick_volume, spread
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                candle.timestamp.isoformat(),
                str(candle.open),
                str(candle.high),
                str(candle.low),
                str(candle.close),
                candle.tick_volume,
                str(candle.spread),
            ),
        )
        await self._db().commit()

    async def save_candles_bulk(
        self, broker_name: str, pair: str, candles: list[Candle]
    ) -> None:
        if not candles:
            return
        timeframe = candles[0].timeframe
        await self._ensure_candle_table(broker_name, pair, timeframe)
        table = self._series_table(broker_name, pair, timeframe)
        values = [
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
        await self._db().executemany(
            f"INSERT OR REPLACE INTO {table} (timestamp, open, high, low, close, tick_volume, spread) VALUES (?,?,?,?,?,?,?)",
            values,
        )
        await self._db().commit()

    async def get_candles(
        self,
        broker_name: str,
        pair: str,
        timeframe: str,
        limit: int = 500,
    ) -> list[Candle]:
        await self._ensure_candle_table(broker_name, pair, timeframe)
        table = self._series_table(broker_name, pair, timeframe)
        cursor = await self._db().execute(
            f"SELECT * FROM {table} ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_candle(r, timeframe) for r in rows]

    async def get_candle_count(self, broker_name: str, pair: str, timeframe: str) -> int:
        await self._ensure_candle_table(broker_name, pair, timeframe)
        table = self._series_table(broker_name, pair, timeframe)
        cursor = await self._db().execute(f"SELECT COUNT(*) AS c FROM {table}")
        row = await cursor.fetchone()
        return int(row["c"]) if row else 0

    # --- Account status ---

    async def _ensure_account_status_table(self) -> None:
        await self._db().execute(
            """
            CREATE TABLE IF NOT EXISTS account_status (
                broker_name TEXT NOT NULL,
                balance TEXT NOT NULL,
                equity TEXT NOT NULL,
                margin TEXT NOT NULL,
                margin_free TEXT NOT NULL,
                leverage INTEGER NOT NULL,
                currency TEXT NOT NULL,
                trade_allowed INTEGER NOT NULL,
                margin_level REAL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (broker_name, recorded_at)
            );
            """
        )
        await self._db().execute(
            """
            CREATE INDEX IF NOT EXISTS idx_account_status_latest
            ON account_status(broker_name, recorded_at DESC);
            """
        )
        await self._db().commit()

    async def save_account_status(self, status: AccountStatus) -> None:
        await self._ensure_account_status_table()
        await self._db().execute(
            """
            INSERT OR REPLACE INTO account_status (
                broker_name, balance, equity, margin, margin_free,
                leverage, currency, trade_allowed, margin_level, recorded_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                status.broker_name,
                str(status.balance),
                str(status.equity),
                str(status.margin),
                str(status.margin_free),
                int(status.leverage),
                status.currency,
                int(bool(status.trade_allowed)),
                float(status.margin_level) if status.margin_level is not None else None,
                status.recorded_at.isoformat(),
            ),
        )
        await self._db().commit()

    async def get_latest_account_status(self, broker_name: str) -> AccountStatus | None:
        await self._ensure_account_status_table()
        cursor = await self._db().execute(
            """
            SELECT * FROM account_status
            WHERE broker_name=?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (broker_name,),
        )
        row = await cursor.fetchone()
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
        await self._db().execute(
            """
            CREATE TABLE IF NOT EXISTS order_book_entries (
                id TEXT PRIMARY KEY,
                broker_name TEXT NOT NULL,
                broker_order_id TEXT,
                pair TEXT NOT NULL,
                direction TEXT NOT NULL,
                order_type TEXT NOT NULL,
                units INTEGER NOT NULL,
                requested_price TEXT NOT NULL,
                fill_price TEXT,
                stop_loss TEXT,
                take_profit TEXT,
                trailing_stop_distance TEXT,
                limit_price TEXT,
                stop_price TEXT,
                status TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                prompt_version INTEGER,
                entry_reasoning TEXT NOT NULL,
                signal_confidence REAL NOT NULL,
                market_context_snapshot TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                opened_at TEXT,
                closed_at TEXT,
                last_broker_sync TEXT,
                close_reason TEXT,
                close_price TEXT,
                close_reasoning TEXT,
                pnl_pips TEXT,
                pnl_account_currency TEXT,
                sync_confirmed INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        await self._db().execute(
            """
            CREATE INDEX IF NOT EXISTS idx_obe_broker_status
            ON order_book_entries(broker_name, status);
            """
        )
        await self._db().execute(
            """
            CREATE INDEX IF NOT EXISTS idx_obe_broker_pair
            ON order_book_entries(broker_name, pair);
            """
        )
        await self._db().commit()

    async def save_order_book_entry(self, entry: OrderBookEntry) -> str:
        await self._ensure_order_book_table()
        eid = str(entry.id)
        await self._db().execute(
            """
            INSERT OR REPLACE INTO order_book_entries (
                id, broker_name, broker_order_id, pair, direction, order_type, units,
                requested_price, fill_price, stop_loss, take_profit, trailing_stop_distance,
                limit_price, stop_price, status, agent_id, prompt_version, entry_reasoning,
                signal_confidence, market_context_snapshot, requested_at, opened_at, closed_at,
                last_broker_sync, close_reason, close_price, close_reasoning, pnl_pips,
                pnl_account_currency, sync_confirmed
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
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
                entry.close_reason.value if isinstance(entry.close_reason, CloseReason) else (entry.close_reason if entry.close_reason else None),
                str(entry.close_price) if entry.close_price is not None else None,
                entry.close_reasoning,
                str(entry.pnl_pips) if entry.pnl_pips is not None else None,
                str(entry.pnl_account_currency) if entry.pnl_account_currency is not None else None,
                int(bool(entry.sync_confirmed)),
            ),
        )
        await self._db().commit()
        return eid

    async def update_order_book_entry(self, entry_id: str, updates: dict) -> None:
        await self._ensure_order_book_table()
        def _to_db(v):
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, Decimal):
                return str(v)
            if isinstance(v, bool):
                return int(v)
            if isinstance(v, (CloseReason, OrderStatus)):
                return v.value
            if isinstance(v, dict):
                return json.dumps(v)
            return v

        set_clause = ", ".join(f"{k}=?" for k in updates.keys())
        values = tuple(_to_db(v) for v in updates.values()) + (entry_id,)
        await self._db().execute(
            f"UPDATE order_book_entries SET {set_clause} WHERE id=?",
            values,
        )
        await self._db().commit()

    async def _row_to_order_book_entry(self, row: aiosqlite.Row):
        r = dict(row)
        # Convert CloseReason if it matches enum values, else keep string/None
        cr_val = r.get("close_reason")
        close_reason = None
        if cr_val:
            try:
                close_reason = CloseReason(cr_val)
            except ValueError:
                close_reason = cr_val
        from openforexai.models.trade import OrderType as _OrderType  # avoid forward ref issues
        return OrderBookEntry(
            id=uuid.UUID(r["id"]),
            broker_name=r["broker_name"],
            broker_order_id=r.get("broker_order_id"),
            pair=r["pair"],
            direction=TradeDirection(r["direction"]),
            order_type=_OrderType(r["order_type"]),
            units=int(r["units"]),
            requested_price=Decimal(r["requested_price"]),
            fill_price=Decimal(r["fill_price"]) if r.get("fill_price") else None,
            stop_loss=Decimal(r["stop_loss"]) if r.get("stop_loss") else None,
            take_profit=Decimal(r["take_profit"]) if r.get("take_profit") else None,
            trailing_stop_distance=Decimal(r["trailing_stop_distance"]) if r.get("trailing_stop_distance") else None,
            limit_price=Decimal(r["limit_price"]) if r.get("limit_price") else None,
            stop_price=Decimal(r["stop_price"]) if r.get("stop_price") else None,
            status=OrderStatus(r["status"]),
            agent_id=r["agent_id"],
            prompt_version=r.get("prompt_version"),
            entry_reasoning=r["entry_reasoning"],
            signal_confidence=float(r["signal_confidence"]),
            market_context_snapshot=json.loads(r["market_context_snapshot"]),
            requested_at=datetime.fromisoformat(r["requested_at"]),
            opened_at=datetime.fromisoformat(r["opened_at"]) if r.get("opened_at") else None,
            closed_at=datetime.fromisoformat(r["closed_at"]) if r.get("closed_at") else None,
            last_broker_sync=datetime.fromisoformat(r["last_broker_sync"]) if r.get("last_broker_sync") else None,
            close_reason=close_reason,
            close_price=Decimal(r["close_price"]) if r.get("close_price") else None,
            close_reasoning=r.get("close_reasoning"),
            pnl_pips=Decimal(r["pnl_pips"]) if r.get("pnl_pips") else None,
            pnl_account_currency=Decimal(r["pnl_account_currency"]) if r.get("pnl_account_currency") else None,
            sync_confirmed=bool(r["sync_confirmed"]),
        )

    async def get_order_book_entry(self, entry_id: str):
        await self._ensure_order_book_table()
        cursor = await self._db().execute(
            "SELECT * FROM order_book_entries WHERE id=?",
            (entry_id,),
        )
        row = await cursor.fetchone()
        return await self._row_to_order_book_entry(row) if row else None

    async def get_open_order_book_entries(
        self, broker_name: str, pair: str | None = None
    ) -> list[OrderBookEntry]:
        await self._ensure_order_book_table()
        if pair:
            cursor = await self._db().execute(
                """
                SELECT * FROM order_book_entries
                WHERE broker_name=? AND pair=? AND status IN ('PENDING','OPEN','PARTIALLY_FILLED')
                ORDER BY requested_at DESC
                """,
                (broker_name, pair),
            )
        else:
            cursor = await self._db().execute(
                """
                SELECT * FROM order_book_entries
                WHERE broker_name=? AND status IN ('PENDING','OPEN','PARTIALLY_FILLED')
                ORDER BY requested_at DESC
                """,
                (broker_name,),
            )
        rows = await cursor.fetchall()
        return [await self._row_to_order_book_entry(r) for r in rows]

    async def get_order_book_entries(
        self,
        broker_name: str,
        pair: str | None = None,
        limit: int = 200,
    ) -> list[OrderBookEntry]:
        await self._ensure_order_book_table()
        if pair:
            cursor = await self._db().execute(
                """
                SELECT * FROM order_book_entries
                WHERE broker_name=? AND pair=?
                ORDER BY requested_at DESC
                LIMIT ?
                """,
                (broker_name, pair, limit),
            )
        else:
            cursor = await self._db().execute(
                """
                SELECT * FROM order_book_entries
                WHERE broker_name=?
                ORDER BY requested_at DESC
                LIMIT ?
                """,
                (broker_name, limit),
            )
        rows = await cursor.fetchall()
        return [await self._row_to_order_book_entry(r) for r in rows]

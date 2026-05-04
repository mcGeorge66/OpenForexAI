-- Migration 003: Agent memory — full decision reasoning + conversation history + performance

-- Extend agent_decisions with full reasoning text and new fields.
-- ALTER TABLE is safe to run multiple times (SQLite ignores duplicate column errors
-- at the executescript level when wrapped in a try block by the adapter).
-- We use a safe pattern: add columns only if they don't exist yet.

-- SQLite does not support "ADD COLUMN IF NOT EXISTS" directly; we rely on the
-- adapter running CREATE TABLE IF NOT EXISTS for the extended schema below.
-- For existing databases, the ALTER TABLE statements handle the migration path.

-- Attempt to add new columns to agent_decisions (will fail silently if they
-- already exist — the adapter's _run_migrations uses executescript which
-- continues on non-fatal errors for ALTER TABLE statements).

ALTER TABLE agent_decisions ADD COLUMN reasoning         TEXT;
ALTER TABLE agent_decisions ADD COLUMN decision_type_new TEXT;
ALTER TABLE agent_decisions ADD COLUMN market_snapshot   TEXT;   -- JSON
ALTER TABLE agent_decisions ADD COLUMN confidence        REAL;

-- Full LLM conversation history per agent session.
-- One row per (agent_id, session_id) — upserted after each trading cycle.
CREATE TABLE IF NOT EXISTS agent_conversations (
    id          TEXT     PRIMARY KEY,          -- UUID
    agent_id    TEXT     NOT NULL,
    session_id  TEXT     NOT NULL,             -- UUID, one per run_cycle() call
    messages    TEXT     NOT NULL,             -- complete JSON messages list (no truncation)
    turn_count  INTEGER  NOT NULL DEFAULT 0,
    started_at  TEXT     NOT NULL,             -- ISO-8601 UTC
    updated_at  TEXT     NOT NULL              -- ISO-8601 UTC
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_conv_session
    ON agent_conversations(agent_id, session_id);
CREATE INDEX IF NOT EXISTS idx_agent_conv_latest
    ON agent_conversations(agent_id, updated_at DESC);

-- Aggregated performance metrics snapshots.
-- Append-only; each snapshot covers a specific time window.
CREATE TABLE IF NOT EXISTS agent_performance (
    id              TEXT     PRIMARY KEY,       -- UUID
    agent_id        TEXT     NOT NULL,
    pair            TEXT     NOT NULL,
    total_decisions INTEGER  NOT NULL DEFAULT 0,
    trades_opened   INTEGER  NOT NULL DEFAULT 0,
    trades_closed   INTEGER  NOT NULL DEFAULT 0,
    win_count       INTEGER  NOT NULL DEFAULT 0,
    loss_count      INTEGER  NOT NULL DEFAULT 0,
    total_pnl       REAL     NOT NULL DEFAULT 0.0,
    period_start    TEXT     NOT NULL,          -- ISO-8601 UTC
    period_end      TEXT     NOT NULL,          -- ISO-8601 UTC
    recorded_at     TEXT     NOT NULL           -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_agent_perf_agent
    ON agent_performance(agent_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_perf_pair
    ON agent_performance(agent_id, pair, recorded_at DESC);

-- Migration 002: Optimization tables

CREATE TABLE IF NOT EXISTS trade_patterns (
    id                    TEXT PRIMARY KEY,
    pair                  TEXT    NOT NULL,
    pattern_type          TEXT    NOT NULL,  -- session_bias | direction_bias | entry_timing | sl_placement
    description           TEXT,
    frequency             INTEGER,
    win_rate_when_present REAL,
    avg_pnl_when_present  REAL,
    conditions            TEXT,              -- JSON
    detected_at           TEXT    NOT NULL,
    sample_size           INTEGER
);

CREATE INDEX IF NOT EXISTS idx_patterns_pair ON trade_patterns(pair);

CREATE TABLE IF NOT EXISTS prompt_candidates (
    id              TEXT PRIMARY KEY,
    pair            TEXT    NOT NULL,
    version         INTEGER NOT NULL,
    system_prompt   TEXT    NOT NULL,
    rationale       TEXT,
    source_patterns TEXT,                    -- JSON array of pattern IDs
    is_active       INTEGER DEFAULT 0,       -- SQLite boolean
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prompts_pair_active ON prompt_candidates(pair, is_active);

CREATE TABLE IF NOT EXISTS backtest_results (
    id                   TEXT PRIMARY KEY,
    prompt_candidate_id  TEXT    NOT NULL,
    pair                 TEXT    NOT NULL,
    period_start         TEXT,
    period_end           TEXT,
    total_trades         INTEGER,
    win_rate             REAL,
    total_pnl            REAL,
    max_drawdown         REAL,
    sharpe_ratio         REAL,
    vs_baseline_pnl_delta REAL,
    completed_at         TEXT    NOT NULL,
    FOREIGN KEY (prompt_candidate_id) REFERENCES prompt_candidates(id)
);

CREATE INDEX IF NOT EXISTS idx_backtest_pair ON backtest_results(pair);

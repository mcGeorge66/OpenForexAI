-- Migration 006: EventComposer run log

CREATE TABLE IF NOT EXISTS ec_runs (
    id             TEXT PRIMARY KEY,
    ec_id          TEXT    NOT NULL,
    trigger        TEXT    NOT NULL,
    input_json     TEXT    NOT NULL DEFAULT '{}',   -- JSON
    config_snapshot TEXT   NOT NULL DEFAULT '{}',   -- JSON: config at run time
    tool_calls     TEXT    NOT NULL DEFAULT '[]',   -- JSON array of {tool, args, result, success, error}
    output_json    TEXT,                            -- JSON or NULL
    success        INTEGER NOT NULL DEFAULT 1,      -- 0 | 1
    error          TEXT,
    latency_ms     REAL,
    run_at         TEXT    NOT NULL,
    correlation_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_ec_runs_ec_id  ON ec_runs(ec_id);
CREATE INDEX IF NOT EXISTS idx_ec_runs_run_at ON ec_runs(run_at);

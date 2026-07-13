-- Migration 001: Core trading tables

CREATE TABLE IF NOT EXISTS trades (
    id           TEXT PRIMARY KEY,
    pair         TEXT    NOT NULL,
    direction    TEXT    NOT NULL,   -- BUY | SELL
    units        INTEGER NOT NULL,
    entry_price  TEXT    NOT NULL,
    stop_loss    TEXT    NOT NULL,
    take_profit  TEXT    NOT NULL,
    fill_price   TEXT,
    pnl          TEXT,
    status       TEXT    NOT NULL,   -- PENDING | OPEN | CLOSED | REJECTED
    opened_at    TEXT,
    closed_at    TEXT,
    close_reason TEXT,               -- TP | SL | manual | timeout
    agent_id     TEXT    NOT NULL,
    broker_order_id TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_pair_status  ON trades(pair, status);
CREATE INDEX IF NOT EXISTS idx_trades_closed_at    ON trades(closed_at);
CREATE INDEX IF NOT EXISTS idx_trades_agent_id     ON trades(agent_id);

CREATE TABLE IF NOT EXISTS agent_decisions (
    id            TEXT PRIMARY KEY,
    agent_id      TEXT    NOT NULL,
    agent_role    TEXT    NOT NULL,   -- trading | technical_analysis | supervisor | optimization
    pair          TEXT,
    decision_type TEXT    NOT NULL,   -- signal | hold | approve | reject | analyze | optimize
    input_context TEXT    NOT NULL,   -- JSON
    output        TEXT    NOT NULL,   -- JSON
    llm_model     TEXT    NOT NULL,
    tokens_used   INTEGER,
    latency_ms    REAL,
    decided_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decisions_agent_id  ON agent_decisions(agent_id);
CREATE INDEX IF NOT EXISTS idx_decisions_pair      ON agent_decisions(pair);
CREATE INDEX IF NOT EXISTS idx_decisions_decided_at ON agent_decisions(decided_at);

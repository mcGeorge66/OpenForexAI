[Back to Documentation Index](./README.md)

# database.md — OpenForexAI Database Reference

Complete description of all tables: purpose, population timing, writers, readers, and possible analyses.

---

## Overview

OpenForexAI supports two backends (configurable via `OPENFOREXAI_DB_BACKEND`):

| Backend      | Adapter                | Default Path            |
| ------------ | ---------------------- | ----------------------- |
| `sqlite`     | `SQLiteRepository`     | `./data/openforexai.db` |
| `postgresql` | `PostgreSQLRepository` | via connection string   |

The schema is migrated automatically at startup. Migration is idempotent — already applied files are skipped.

### Migration Tracking

```
schema_migrations
  filename    TEXT PRIMARY KEY   -- e.g. "001_initial_schema.sql"
  applied_at  TEXT               -- UTC timestamp of application
```

Managed internally by the adapter. Not intended for external queries.

---

## Table Overview

| Table | Migration | Purpose |
|---|---|---|
| `{BROKER}_{PAIR}_{TF}` | dynamic | Candle data (M5 primary) |
| `account_status` | dynamic | Account balance snapshots |
| `order_book_entries` | dynamic | Authoritative local order book copy |
| `trades` | 001 | Legacy trade results (backward compatible) |
| `agent_decisions` | 001 + 003 | Every LLM decision of every agent |
| `trade_patterns` | 002 | Detected statistical patterns in trade history |
| `prompt_candidates` | 002 | Versioned system prompts per pair |
| `backtest_results` | 002 | Backtesting results per prompt candidate |
| `agent_conversations` | 003 | Full LLM conversation history per cycle |
| `agent_performance` | 003 | Aggregated performance snapshots per agent |

---

## Dynamic Candle Tables

### `{BROKER}_{PAIR}_{TIMEFRAME}`

Examples: `OAPR1_EURUSD_M5`, `OAPR1_GBPUSD_M5`

```sql
timestamp    TEXT PRIMARY KEY   -- ISO-8601 UTC, e.g. "2026-03-03T08:00:00+00:00"
open         TEXT               -- decimal price as string (Decimal precision)
high         TEXT
low          TEXT
close        TEXT
tick_volume  INTEGER
spread       TEXT
```

**Why:** Only M5 candles are fetched from the broker via API. All higher timeframes (M15, M30, H1, H4, D1) are calculated on demand from M5 by the `DataContainer` resampler. Primarily the raw M5 data is persisted; higher TFs can also be persisted if needed (same table structure, different TF suffix).

**When populated:**
- Initial at system startup: `BrokerBase` loads historical M5 candles via bulk insert (`save_candles_bulk`)
- Continuously every 5 minutes: broker adapter publishes `m5_candle_available`; `DataContainer` persists via `save_candle`

**Writer:** `BrokerBase` → `SQLiteRepository.save_candle / save_candles_bulk`

**Readers:**
- `DataContainer` — loads missing history from DB at startup
- `get_candles` tool — provides candle history to agents
- `Backtester` — uses historical M5 data for prompt tests
- Management API — `/candles/{pair}` endpoint

**Analysis options:**
```sql
-- How many M5 candles are stored for EURUSD?
SELECT COUNT(*) FROM OAPR1_EURUSD_M5;

-- Last 10 EURUSD candles
SELECT * FROM OAPR1_EURUSD_M5 ORDER BY timestamp DESC LIMIT 10;

-- Day range for a specific day
SELECT MIN(CAST(low AS REAL)), MAX(CAST(high AS REAL))
FROM OAPR1_EURUSD_M5
WHERE timestamp LIKE '2026-03-03%';
```

---

## `account_status`

```sql
broker_name    TEXT NOT NULL
balance        TEXT               -- account balance (Decimal as string)
equity         TEXT               -- equity incl. unrealized PnL
margin         TEXT               -- used margin
margin_free    TEXT               -- free margin
leverage       INTEGER
currency       TEXT               -- account currency, e.g. "EUR"
trade_allowed  INTEGER            -- 0 | 1 (SQLite boolean)
margin_level   REAL               -- margin level in %, can be NULL
recorded_at    TEXT NOT NULL      -- ISO-8601 UTC
PRIMARY KEY (broker_name, recorded_at)
```

**Why:** Historical account balance progression enables equity-curve analysis. The current value is queried by agents via the `get_account_status` tool.

**When populated:** `BrokerBase` polls account status from broker every 5 minutes and stores each snapshot via `save_account_status`.

**Writer:** `BrokerBase` (account poll loop)

**Readers:**
- `get_account_status` tool → agents (position sizing, risk checks)
- Management API — `/account/{broker}` endpoint
- Supervisor agent — checks margin level before trade approval

**Analysis options:**
```sql
-- Equity curve for the last 7 days
SELECT recorded_at, CAST(equity AS REAL) AS equity
FROM account_status
WHERE broker_name = 'OAPR1'
  AND recorded_at > datetime('now', '-7 days')
ORDER BY recorded_at;

-- Lowest free margin (critical moments)
SELECT recorded_at, CAST(margin_free AS REAL) AS free
FROM account_status
WHERE broker_name = 'OAPR1'
ORDER BY CAST(margin_free AS REAL) ASC
LIMIT 5;
```

---

## `order_book_entries`

The **central trade table** of the system. One row per placed order — from signal approval to closure.

```sql
id                       TEXT PRIMARY KEY          -- UUID
broker_name              TEXT NOT NULL             -- e.g. "OAPR1"
broker_order_id          TEXT                      -- broker-side order ID (after confirmation)
pair                     TEXT NOT NULL             -- e.g. "EURUSD"
direction                TEXT NOT NULL             -- "BUY" | "SELL"
order_type               TEXT NOT NULL             -- MARKET | LIMIT | STOP | STOP_LIMIT | TRAILING_STOP
units                    INTEGER NOT NULL

-- Prices
requested_price          TEXT NOT NULL             -- agent-calculated entry price
fill_price               TEXT                      -- actual fill price (after broker confirmation)
stop_loss                TEXT
take_profit              TEXT
trailing_stop_distance   TEXT                      -- in pips (TRAILING_STOP only)
limit_price              TEXT                      -- LIMIT / STOP_LIMIT
stop_price               TEXT                      -- STOP / STOP_LIMIT

-- Status
status                   TEXT NOT NULL             -- PENDING | OPEN | PARTIALLY_FILLED | CLOSED | REJECTED | CANCELLED

-- Agent context (key for optimization)
agent_id                 TEXT NOT NULL             -- e.g. "OAPR1_EURUSD_AA_ANLYS"
prompt_version           INTEGER                   -- prompt version at signal time
entry_reasoning          TEXT NOT NULL             -- agent reasoning text
signal_confidence        REAL NOT NULL             -- 0.0–1.0
market_context_snapshot  TEXT NOT NULL             -- JSON: last M5 candle + indicator values

-- Timestamps
requested_at             TEXT NOT NULL             -- signal timestamp
opened_at                TEXT                      -- broker confirmation
closed_at                TEXT
last_broker_sync         TEXT                      -- last sync check

-- Exit data
close_reason             TEXT                      -- SL_HIT | TP_HIT | TRAILING_STOP | AGENT_CLOSED | BROKER_CLOSED | SYNC_DETECTED
close_price              TEXT
close_reasoning          TEXT                      -- free-text closure note
pnl_pips                 TEXT
pnl_account_currency     TEXT

-- Sync
sync_confirmed           INTEGER NOT NULL DEFAULT 0  -- 1 = broker confirmed position
```

**Why:** This table is the single source of truth for all trades in the system. It contains the full decision context (`market_context_snapshot`, `entry_reasoning`) — the primary raw material for the `OptimizationAgent`.

**When populated:**
- `PENDING` entry at signal approval (supervisor approved)
- Update to `OPEN` + `fill_price` after broker confirmation
- Update to `CLOSED` on closure (SL/TP/agent/sync)
- `last_broker_sync` updated on every sync cycle

**Writer:** Broker agent (`BA`) via `place_order` tool → `save_order_book_entry`; sync loop via `update_order_book_entry`

**Readers:**
- `get_open_positions` tool — shows open positions to agents
- `get_order_book` tool — historical overview
- `OptimizationAgent` — analyzes `market_context_snapshot` + outcomes
- Sync loop — checks PENDING/OPEN entries against broker API
- Management API — `/orders/{broker}` endpoint

**Analysis options:**
```sql
-- Win rate by pair
SELECT pair,
       COUNT(*) AS total,
       SUM(CASE WHEN CAST(pnl_account_currency AS REAL) > 0 THEN 1 ELSE 0 END) AS wins,
       ROUND(100.0 * SUM(CASE WHEN CAST(pnl_account_currency AS REAL) > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate_pct
FROM order_book_entries
WHERE status = 'CLOSED'
GROUP BY pair;

-- Average PnL by close reason
SELECT close_reason, AVG(CAST(pnl_account_currency AS REAL)) AS avg_pnl, COUNT(*) AS cnt
FROM order_book_entries
WHERE status = 'CLOSED'
GROUP BY close_reason;

-- All trades with high confidence that still lost
SELECT id, pair, direction, signal_confidence, pnl_account_currency, entry_reasoning
FROM order_book_entries
WHERE status = 'CLOSED'
  AND signal_confidence > 0.8
  AND CAST(pnl_account_currency AS REAL) < 0
ORDER BY pnl_account_currency ASC;

-- Slippage (requested vs. fill)
SELECT pair, AVG(ABS(CAST(fill_price AS REAL) - CAST(requested_price AS REAL))) AS avg_slippage
FROM order_book_entries
WHERE fill_price IS NOT NULL
GROUP BY pair;
```

---

## `trades`

**Legacy table** — kept for backward compatibility. Newer deployments primarily use `order_book_entries`.

```sql
id              TEXT PRIMARY KEY
pair            TEXT NOT NULL
direction       TEXT NOT NULL          -- "BUY" | "SELL"
units           INTEGER NOT NULL
entry_price     TEXT NOT NULL
stop_loss       TEXT NOT NULL
take_profit     TEXT NOT NULL
fill_price      TEXT
pnl             TEXT
status          TEXT NOT NULL          -- PENDING | OPEN | CLOSED | REJECTED
opened_at       TEXT
closed_at       TEXT
close_reason    TEXT                   -- TP | SL | manual | timeout
agent_id        TEXT NOT NULL
broker_order_id TEXT
created_at      TEXT NOT NULL
```

**When populated:** Via `save_trade` (rarely called directly in newer code; `order_book_entries` is the standard).

**Analysis:** Same basic patterns as `order_book_entries`, but without `market_context_snapshot` and `entry_reasoning`.

---

## `agent_decisions`

Logs **every LLM decision** of every agent — the complete audit log of the AI system.

```sql
id               TEXT PRIMARY KEY
agent_id         TEXT NOT NULL          -- e.g. "OAPR1_EURUSD_AA_ANLYS"
agent_role       TEXT NOT NULL          -- trading | technical_analysis | supervisor | optimization
pair             TEXT
decision_type    TEXT NOT NULL          -- signal | hold | approve | reject | analyze | optimize
input_context    TEXT NOT NULL          -- JSON: what input the agent received
output           TEXT NOT NULL          -- JSON: what the agent decided
llm_model        TEXT NOT NULL          -- e.g. "claude-sonnet-4-6"
tokens_used      INTEGER                -- total token count (input + output)
latency_ms       REAL                   -- response time in ms
decided_at       TEXT NOT NULL          -- ISO-8601 UTC

-- Fields from migration 003:
reasoning        TEXT                   -- full LLM reasoning text
market_snapshot  TEXT                   -- JSON: market data at decision time
confidence       REAL                   -- 0.0–1.0 (if emitted by agent)
```

**Why:** Complete traceability of all AI decisions. Enables post-mortem analysis, debugging, and cost tracking.

**When populated:** At the end of each `run_cycle()` — after every LLM response, regardless of outcome.

**Writer:** Every agent via `save_agent_decision` after completed LLM turn.

**Readers:**
- `OptimizationAgent` — pattern detection over decision sequences
- Management API — `/decisions/{agent_id}` endpoint
- Monitoring / debugging

**Analysis options:**
```sql
-- Token cost per agent per day
SELECT agent_id,
       DATE(decided_at) AS day,
       SUM(tokens_used) AS total_tokens,
       COUNT(*) AS decisions
FROM agent_decisions
GROUP BY agent_id, day
ORDER BY day DESC, total_tokens DESC;

-- Average LLM latency by model
SELECT llm_model, AVG(latency_ms) AS avg_ms, MAX(latency_ms) AS max_ms
FROM agent_decisions
GROUP BY llm_model;

-- Supervisor approve/reject ratio
SELECT decision_type, COUNT(*) AS cnt
FROM agent_decisions
WHERE agent_role = 'supervisor'
GROUP BY decision_type;

-- Which decisions resulted in signal "hold"?
SELECT decided_at, pair, output
FROM agent_decisions
WHERE decision_type = 'hold'
ORDER BY decided_at DESC
LIMIT 20;
```

---

## `agent_conversations`

Stores the **full LLM message history** per agent cycle (session).

```sql
id          TEXT PRIMARY KEY       -- UUID
agent_id    TEXT NOT NULL          -- e.g. "OAPR1_EURUSD_AA_ANLYS"
session_id  TEXT NOT NULL          -- UUID, one new one per run_cycle() call
messages    TEXT NOT NULL          -- full JSON message list (system, user, assistant, tool_result)
turn_count  INTEGER DEFAULT 0      -- number of LLM turns in this session
started_at  TEXT NOT NULL          -- ISO-8601 UTC
updated_at  TEXT NOT NULL          -- ISO-8601 UTC (upsert on each turn)
UNIQUE (agent_id, session_id)
```

**Why:** Full reproducibility of each cycle. Enables precise analysis of why an agent reached a specific decision — including all tool calls and intermediate steps.

**When populated:** Upsert after each LLM turn within `run_cycle()`. A session ends with the cycle.

**Writer:** Agent (`agent.py`) via repository after each turn.

**Readers:**
- Debugging and post-mortem analysis
- Prompt engineering (review of real conversation flows)
- Potentially `OptimizationAgent` for deep behavior analysis

**Analysis options:**
```sql
-- Sessions with many turns (complex decisions)
SELECT agent_id, session_id, turn_count, started_at
FROM agent_conversations
ORDER BY turn_count DESC
LIMIT 10;

-- All sessions of one agent today
SELECT session_id, turn_count, started_at, updated_at
FROM agent_conversations
WHERE agent_id = 'OAPR1_EURUSD_AA_ANLYS'
  AND DATE(started_at) = DATE('now')
ORDER BY started_at DESC;
```

---

## `agent_performance`

Append-only table with **aggregated performance snapshots** per agent and pair.

```sql
id               TEXT PRIMARY KEY       -- UUID
agent_id         TEXT NOT NULL
pair             TEXT NOT NULL
total_decisions  INTEGER DEFAULT 0
trades_opened    INTEGER DEFAULT 0
trades_closed    INTEGER DEFAULT 0
win_count        INTEGER DEFAULT 0
loss_count       INTEGER DEFAULT 0
total_pnl        REAL DEFAULT 0.0
period_start     TEXT NOT NULL          -- ISO-8601 UTC (start of evaluation window)
period_end       TEXT NOT NULL          -- ISO-8601 UTC
recorded_at      TEXT NOT NULL          -- ISO-8601 UTC (snapshot timestamp)
```

**Why:** Lightweight access to performance metrics without expensive aggregation over `order_book_entries` or `agent_decisions`. Serves as a time series for trend analysis.

**When populated:** Periodically by `OptimizationAgent` or supervisor — after completed evaluation windows.

**Writer:** `OptimizationAgent` / supervisor via `save_agent_performance` (repository method).

**Readers:**
- Management API — performance dashboard
- `OptimizationAgent` — baseline for prompt comparison
- External reporting tools

**Analysis options:**
```sql
-- Agent win-rate trend over time
SELECT recorded_at,
       ROUND(100.0 * win_count / NULLIF(trades_closed, 0), 1) AS win_rate_pct,
       total_pnl
FROM agent_performance
WHERE agent_id = 'OAPR1_EURUSD_AA_ANLYS'
ORDER BY recorded_at;

-- Best agent by cumulative PnL
SELECT agent_id, pair, SUM(total_pnl) AS cum_pnl
FROM agent_performance
GROUP BY agent_id, pair
ORDER BY cum_pnl DESC;
```

---

## `trade_patterns`

Statistically detected patterns in trade history. Input for the prompt evolver.

```sql
id                    TEXT PRIMARY KEY
pair                  TEXT NOT NULL
pattern_type          TEXT NOT NULL   -- session_bias | direction_bias | entry_timing | sl_placement
description           TEXT            -- human-readable description
frequency             INTEGER         -- how often pattern appeared in data
win_rate_when_present REAL            -- win rate of trades where pattern was present
avg_pnl_when_present  REAL            -- average PnL with pattern
conditions            TEXT            -- JSON: e.g. {"session": "london", "rsi": ">70"}
detected_at           TEXT NOT NULL
sample_size           INTEGER         -- number of analyzed trades
```

**Why:** Formalized memory of the `OptimizationAgent`. Detected patterns are persisted as knowledge for prompt evolution and referenced later.

**When populated:** `OptimizationAgent` after analyzing `order_book_entries` history — typically after a minimum number of closed trades.

**Writer:** `OptimizationAgent` via `save_pattern`

**Readers:**
- `OptimizationAgent` — basis for `PromptCandidate` creation
- `get_patterns` — Management API / debugging

**Analysis options:**
```sql
-- Highest win-rate patterns (min. 20 samples)
SELECT pair, pattern_type, description, win_rate_when_present, sample_size
FROM trade_patterns
WHERE sample_size >= 20
ORDER BY win_rate_when_present DESC
LIMIT 10;

-- All known patterns for EURUSD
SELECT pattern_type, description, win_rate_when_present, avg_pnl_when_present
FROM trade_patterns
WHERE pair = 'EURUSD'
ORDER BY detected_at DESC;
```

---

## `prompt_candidates`

Versioned system prompts per currency pair. Only one candidate per pair is active at a time (`is_active = 1`).

```sql
id              TEXT PRIMARY KEY
pair            TEXT NOT NULL
version         INTEGER NOT NULL       -- monotonically increasing per pair
system_prompt   TEXT NOT NULL          -- full system prompt text
rationale       TEXT                   -- rationale for the change
source_patterns TEXT                   -- JSON array of TradePattern UUIDs that motivated this prompt
is_active       INTEGER DEFAULT 0      -- 0 | 1 (SQLite boolean)
created_at      TEXT NOT NULL
```

**Why:** Enables controlled, data-driven prompt evolution. Every change is versioned and traceable to specific patterns. Rollback to older versions is always possible.

**When populated:** `OptimizationAgent` creates a new candidate after successful pattern detection. Activation occurs after positive backtest (`is_active` is set via UPDATE).

**Writer:** `OptimizationAgent` via `save_prompt_candidate`

**Readers:**
- `ConfigService` — provides active prompt to agents via `AGENT_CONFIG_RESPONSE`
- `get_best_prompt` — returns current active prompt
- Management API — prompt version history

**Analysis options:**
```sql
-- All prompt versions for EURUSD (newest first)
SELECT version, is_active, rationale, created_at
FROM prompt_candidates
WHERE pair = 'EURUSD'
ORDER BY version DESC;

-- Which patterns motivated the currently active prompt?
SELECT source_patterns
FROM prompt_candidates
WHERE pair = 'EURUSD' AND is_active = 1;
```

---

## `backtest_results`

Results of simulating a `PromptCandidate` on historical M5 data.

```sql
id                    TEXT PRIMARY KEY
prompt_candidate_id   TEXT NOT NULL      -- FK → prompt_candidates.id
pair                  TEXT NOT NULL
period_start          TEXT               -- backtest period start
period_end            TEXT               -- backtest period end
total_trades          INTEGER
win_rate              REAL               -- 0.0–1.0
total_pnl             REAL
max_drawdown          REAL
sharpe_ratio          REAL
vs_baseline_pnl_delta REAL               -- PnL delta vs previous active prompt (positive = better)
completed_at          TEXT NOT NULL
FOREIGN KEY (prompt_candidate_id) REFERENCES prompt_candidates(id)
```

**Why:** Before activating a new prompt, it is tested on historical data. Only if `vs_baseline_pnl_delta > 0` (and other thresholds are met), the candidate is activated.

**When populated:** `Backtester` via `scripts/run_backtest.py` or automatically by `OptimizationAgent` after prompt creation.

**Writer:** `Backtester` via `save_backtest_result`

**Readers:**
- `OptimizationAgent` — decision on prompt activation
- Management API — backtest dashboard
- External reporting tools

**Analysis options:**
```sql
-- All backtests for EURUSD, sorted by Sharpe ratio
SELECT b.completed_at, b.total_trades, b.win_rate, b.total_pnl,
       b.sharpe_ratio, b.vs_baseline_pnl_delta, p.version
FROM backtest_results b
JOIN prompt_candidates p ON b.prompt_candidate_id = p.id
WHERE b.pair = 'EURUSD'
ORDER BY b.sharpe_ratio DESC;

-- Did the last prompt switch actually improve performance?
SELECT p.version, b.vs_baseline_pnl_delta, b.win_rate, b.total_pnl
FROM backtest_results b
JOIN prompt_candidates p ON b.prompt_candidate_id = p.id
WHERE p.is_active = 1
ORDER BY b.completed_at DESC
LIMIT 1;
```

---

## Data Flow Diagram

```
Broker API (every 5 min)
    │
    ├─► {BROKER}_{PAIR}_M5          (save_candle / save_candles_bulk)
    └─► account_status              (save_account_status)

Agent (LLM cycle)
    │
    ├─► agent_decisions             (save_agent_decision)     — every LLM decision
    └─► agent_conversations         (upsert)                  — full conversation history

Signal approved → order placed
    │
    └─► order_book_entries          (save_order_book_entry)   — PENDING

Broker confirms fill
    │
    └─► order_book_entries          (update_order_book_entry) — OPEN + fill_price

Trade closed (SL/TP/agent)
    │
    └─► order_book_entries          (update_order_book_entry) — CLOSED + PnL

OptimizationAgent (periodic)
    │
    ├─► trade_patterns              (save_pattern)
    ├─► prompt_candidates           (save_prompt_candidate)
    ├─► backtest_results            (save_backtest_result)
    └─► agent_performance           (save_agent_performance)
```

---

## Useful General Queries

```sql
-- Database size per table (SQLite)
SELECT name,
       SUM(pgsize) / 1024 AS size_kb
FROM dbstat
GROUP BY name
ORDER BY size_kb DESC;

-- Which candle tables exist?
SELECT name FROM sqlite_master
WHERE type = 'table'
  AND name GLOB '*_M5'
ORDER BY name;

-- Overall view: open positions
SELECT broker_name, pair, direction, units, requested_price, signal_confidence, requested_at
FROM order_book_entries
WHERE status IN ('PENDING', 'OPEN', 'PARTIALLY_FILLED')
ORDER BY requested_at DESC;

-- Migration status
SELECT filename, applied_at FROM schema_migrations ORDER BY applied_at;
```

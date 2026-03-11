# migrations — Database Schema

SQL migration files that define the database schema for OpenForexAI. Migrations are applied automatically at startup by the SQLite adapter, or manually via `scripts/db_migrate.py`.

## Files

| File | Contents |
|---|---|
| `001_initial_schema.sql` | Core trading tables: `trades`, `agent_decisions` |
| `002_optimization_tables.sql` | Optimization tables: `trade_patterns`, `prompt_candidates`, `backtest_results` |
| `003_agent_memory.sql` | Agent memory and extended decision history |

---

## Schema Overview

### `trades` (001)

All trade orders and their lifecycle:

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Unique order ID |
| `pair` | TEXT | Currency pair (e.g. `EURUSD`) |
| `direction` | TEXT | `BUY` \| `SELL` |
| `units` | INTEGER | Order size |
| `entry_price` | TEXT | Requested entry price |
| `stop_loss` | TEXT | Stop-loss price |
| `take_profit` | TEXT | Take-profit price |
| `fill_price` | TEXT | Actual fill price (set when filled) |
| `pnl` | TEXT | Realized P&L (set when closed) |
| `status` | TEXT | `PENDING` \| `OPEN` \| `CLOSED` \| `REJECTED` |
| `opened_at` | TEXT | UTC timestamp of position open |
| `closed_at` | TEXT | UTC timestamp of close |
| `close_reason` | TEXT | `TP` \| `SL` \| `manual` \| `timeout` |
| `agent_id` | TEXT | Agent that placed the order |
| `broker_order_id` | TEXT | Broker's internal order ID |

**Indexes:** `(pair, status)`, `closed_at`, `agent_id`

---

### `agent_decisions` (001)

Complete history of all agent decision cycles:

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Unique decision ID |
| `agent_id` | TEXT | Agent that made this decision |
| `agent_role` | TEXT | `trading` \| `technical_analysis` \| `supervisor` \| `optimization` |
| `pair` | TEXT | Currency pair (nullable for global agents) |
| `decision_type` | TEXT | `signal` \| `hold` \| `approve` \| `reject` \| `analyze` \| `optimize` |
| `input_context` | TEXT | JSON: full context passed to the LLM |
| `output` | TEXT | JSON: agent's structured output |
| `llm_model` | TEXT | LLM model used |
| `tokens_used` | INTEGER | Total tokens consumed |
| `latency_ms` | REAL | Cycle latency in milliseconds |
| `decided_at` | TEXT | UTC timestamp |

**Indexes:** `agent_id`, `pair`, `decided_at`

---

### `trade_patterns` (002)

Recurring patterns detected by the pattern detector:

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Unique pattern ID |
| `pair` | TEXT | Currency pair |
| `pattern_type` | TEXT | `session_bias` \| `direction_bias` \| `entry_timing` \| `sl_placement` |
| `description` | TEXT | Human-readable description |
| `frequency` | INTEGER | How often this pattern was observed |
| `win_rate_when_present` | REAL | Historical win rate when this pattern is present |
| `avg_pnl_when_present` | REAL | Average P&L when this pattern is present |
| `conditions` | TEXT | JSON: conditions that define the pattern |
| `sample_size` | INTEGER | Number of trades in the analysis |

---

### `prompt_candidates` (002)

System prompt versions for optimization:

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Unique candidate ID |
| `pair` | TEXT | Currency pair this prompt targets |
| `version` | INTEGER | Candidate generation number |
| `system_prompt` | TEXT | Full system prompt text |
| `rationale` | TEXT | Why this prompt was generated |
| `source_patterns` | TEXT | JSON array of pattern IDs that inspired this prompt |
| `is_active` | INTEGER | 1 = currently active for this pair |

---

### `backtest_results` (002)

Performance metrics for backtested prompt candidates:

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Unique result ID |
| `prompt_candidate_id` | TEXT FK | References `prompt_candidates.id` |
| `pair` | TEXT | Currency pair |
| `period_start` / `period_end` | TEXT | Backtest time range |
| `total_trades` | INTEGER | Number of trades in backtest |
| `win_rate` | REAL | Win rate (0.0–1.0) |
| `total_pnl` | REAL | Total P&L over the period |
| `max_drawdown` | REAL | Maximum drawdown |
| `sharpe_ratio` | REAL | Sharpe ratio |
| `vs_baseline_pnl_delta` | REAL | P&L improvement vs. baseline prompt |

---

## Migration System

### How Migrations Run

The SQLite adapter tracks applied migrations in a `schema_migrations` table:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename  TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

On each startup:
1. The `schema_migrations` table is created (if not exists)
2. For each `*.sql` file in `migrations/` (sorted alphabetically):
   - If the filename is already in `schema_migrations` → skip
   - Otherwise → apply the migration, record it
3. Existing databases are bootstrapped: already-applied migrations are detected by inspecting the schema directly

### Applying Migrations Manually

```bash
python scripts/db_migrate.py
python scripts/db_migrate.py --config config/system.json5
```

### Adding a New Migration

1. Create `migrations/NNN_description.sql` (increment NNN)
2. Write idempotent SQL using `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`
3. The next system startup will apply it automatically

> **Important:** Use `IF NOT EXISTS` everywhere — migrations can be re-run in some circumstances and must be idempotent.

### PostgreSQL

PostgreSQL migrations are not yet automated. Apply SQL files manually with `psql` or a migration tool.


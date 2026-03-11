[Back to Documentation Index](./README.md)

# scripts — CLI Utilities

Standalone command-line scripts for database management, data export, and backtesting. These scripts operate independently of the running system — they don't require the main application to be running.

## Scripts

| Script | Purpose |
|---|---|
| `db_migrate.py` | Apply database migrations |
| `export_prompts.py` | Export agent system prompts from config |
| `run_backtest.py` | Run backtests on prompt candidates |

---

## `db_migrate.py` — Database Migrator

Applies all pending SQL migration files from `migrations/` to the configured database.

```bash
# Using default config (config/system.json5)
python scripts/db_migrate.py

# Using a custom config file
python scripts/db_migrate.py --config path/to/system.json5
```

### What it does

1. Reads `database.backend` and `database.sqlite_path` from `system.json5`
2. Scans `migrations/*.sql` in alphabetical order
3. Applies each file via `executescript()`
4. Prints the name of each applied file

### Notes

- Currently automated for **SQLite only**. For PostgreSQL, apply migrations manually.
- This script is provided for manual/one-off use. The main application also applies migrations automatically on startup via the SQLite adapter's `_run_migrations()` method.
- Migrations are idempotent (`CREATE TABLE IF NOT EXISTS`) — safe to run multiple times.

---

## `export_prompts.py` — Prompt Exporter

Exports the system prompts for all agents defined in `system.json5` to readable files or stdout.

```bash
# Print all agent prompts to stdout
python scripts/export_prompts.py

# Export to individual files in a directory
python scripts/export_prompts.py --output-dir ./exported_prompts/

# Export for a specific agent
python scripts/export_prompts.py --agent OAPR1_EURUSD_AA_ANLYS
```

**Use cases:**
- Review and audit agent prompts before deployment
- Version-control prompt snapshots
- Prepare prompts for manual editing or A/B testing

---

## `run_backtest.py` — Backtest Runner

Runs the backtesting pipeline on one or more prompt candidates using historical trade data.

```bash
# Backtest all prompt candidates for EURUSD
python scripts/run_backtest.py --pair EURUSD

# Backtest a specific candidate
python scripts/run_backtest.py --candidate-id <id>

# Backtest with a custom time range
python scripts/run_backtest.py --pair EURUSD \
    --start 2025-01-01 --end 2025-12-31
```

**What it does:**
1. Loads prompt candidates from the database
2. Replays historical M5 candles through the analysis pipeline
3. Simulates trade signals and outcomes
4. Records `BacktestResult` to the database
5. Prints a performance summary (win rate, P&L, Sharpe ratio, max drawdown)

**Requirements:** The database must have M5 candle history for the target pair (populated by running the main system for at least the backtest period).

---

## General Notes

All scripts:
- Use `asyncio.run()` — they are fully async internally
- Load config via `config/json_loader.py` (supports `${ENV_VAR:-default}`)
- Do not require the main system to be running
- Write to `stderr` for errors, `stdout` for results
- Exit with code 0 on success, non-zero on error


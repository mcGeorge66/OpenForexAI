[Back to Documentation Index](./README.md)

# adapters/database — Database Adapters

Concrete implementations of `AbstractRepository` for persistent storage. Handles all database I/O: candles, trades, agent decisions, optimization results.

## Files

| File | Backend | Library |
|---|---|---|
| `__init__.py` | — | Self-registration |
| `sqlite.py` | SQLite | `aiosqlite` |
| `postgresql.py` | PostgreSQL | `asyncpg` |

---

## `sqlite.py` — SQLite Adapter

Default backend. Uses `aiosqlite` for fully async, non-blocking I/O within the asyncio event loop.

### Database File

Default: `./data/openforexai.db`
Override: `OPENFOREXAI_DB_PATH=/path/to/custom.db`

### Key Implementation Details

**WAL Mode:** The database runs in WAL (Write-Ahead Logging) mode for better concurrent read performance — multiple readers can proceed while a write is in progress.

**Candle Upsert:** Candles use `INSERT OR REPLACE INTO` — duplicate candles (same timestamp + pair) are silently replaced. This makes the data pipeline idempotent: re-fetching candles on gap repair never creates duplicates.

**Migration Tracking:** Applied migrations are recorded in `schema_migrations(filename, applied_at)`. The adapter bootstraps this for existing databases by inspecting the schema directly before writing migration records.

**Connection Pooling:** A single `aiosqlite` connection is reused throughout the session. `pool_size` in config is reserved for PostgreSQL.

### Migration Bootstrap Logic

```python
# On startup: _run_migrations()
1. CREATE TABLE IF NOT EXISTS schema_migrations(...)
2. If schema_migrations is empty:
   → _bootstrap_migration_history()
      - Check if 'trades' table exists → mark 001 as applied
      - Check if 'prompt_candidates' table exists → mark 002 as applied
      - (etc. for each known migration)
3. For each *.sql file in migrations/ (sorted):
   → If not in schema_migrations → apply and record
   → If already recorded → skip
```

This handles the one-time transition from "no migration tracking" (legacy) to "tracked migrations" without re-running already-applied SQL.

### Performance Notes

SQLite is well-suited for this workload:
- Mostly sequential M5 candle inserts (one row every 5 minutes per pair)
- Periodic bulk reads for resampling (300–8,000 rows at a time)
- Infrequent writes for trades and decisions

On an SSD, expect:
- Single candle insert: < 1ms
- 8,000-row M5 read (D1 resampling): 10–50ms

---

## `postgresql.py` — PostgreSQL Adapter

Production-grade backend for high-availability or multi-process deployments.

### When to Use PostgreSQL

- Multiple processes reading/writing simultaneously
- Remote database (separate server from the trading system)
- Higher write throughput requirements
- Integration with existing PostgreSQL infrastructure

### Config

```bash
OPENFOREXAI_DB_BACKEND=postgresql
DATABASE_URL=postgresql://user:password@host:5432/openforexai
```

### Differences from SQLite

| Feature | SQLite | PostgreSQL |
|---|---|---|
| Concurrent writes | Single writer | Multiple writers |
| Connection | File-based | TCP/IP |
| Migration automation | ✓ | Manual |
| Decimal precision | TEXT storage | NUMERIC type |
| Auto-migrations | ✓ (built-in) | Manual (`psql` or migration tool) |

### Migration for PostgreSQL

Migrations are **not yet automated** for PostgreSQL. Apply `migrations/*.sql` manually:

```bash
psql postgresql://user:pass@host/dbname < migrations/001_initial_schema.sql
psql postgresql://user:pass@host/dbname < migrations/002_optimization_tables.sql
psql postgresql://user:pass@host/dbname < migrations/003_agent_memory.sql
```

---

## Selecting a Backend

```bash
# SQLite (default — recommended for single-machine deployments)
OPENFOREXAI_DB_BACKEND=sqlite
OPENFOREXAI_DB_PATH=./data/openforexai.db

# PostgreSQL
OPENFOREXAI_DB_BACKEND=postgresql
DATABASE_URL=postgresql://user:pass@localhost/openforexai
```

Both backends implement the same `AbstractRepository` interface — the rest of the system is unaware of which backend is in use.


[Back to Documentation Index](./README.md)

# openforexai/data — Market Data Management

All market data handling: storage, retrieval, resampling, technical indicators, and correlation analysis.

## Files

| File | Purpose |
|---|---|
| `container.py` | `DataContainer` — central market data hub |
| `resampler.py` | Aggregates M5 bars into higher timeframes |
| `indicators.py` | Technical indicator calculations (pure functions) |
| `indicator_tools.py` | Tool-facing dispatcher for indicator requests |
| `indicator_plugins.py` | Pluggable indicator registry |
| `correlation.py` | Pair correlation matrix computation |
| `normalizer.py` | Data normalisation utilities |

---

## `container.py` — DataContainer

The single source of truth for all market data in the running system.

### Architecture

```
Broker adapter
    │  M5_CANDLE_AVAILABLE event
    ▼
DataContainer._on_m5_candle()
    │  INSERT OR REPLACE into DB
    │  gap detection
    ▼
AbstractDataContainer (DB)
    │
    ├── get_candles("M5", ...) → reads DB directly
    └── get_candles("H1", ...) → reads M5 from DB → resampler → H1 bars
```

**Key principle**: Only M5 candles are stored in the database. All higher timeframes (M15, M30, H1, H4, D1) are derived **on-demand** by the resampler — no separate broker API calls needed.

### Memory Footprint

`DataContainer` stores almost nothing in RAM:
- `_last_ts: dict[str, datetime]` — one timestamp per `(broker, pair)` for cheap duplicate detection
- `_registered: set[str]` — registered `(broker, pair)` pairs
- `_write_locks: dict[str, asyncio.Lock]` — per-pair write serialisation

All candle data lives in the database.

### Candle Deduplication

Two layers prevent duplicate candles:
1. **In-memory**: `_last_ts` — if the incoming timestamp ≤ last known, discard
2. **Database**: `INSERT OR REPLACE` — silently replaces any duplicate (same primary key)

### Backfill on Startup

When a pair has no data in the DB, `initialize()` back-fills ~4 weeks of M5 candles (`8 064` bars) from the broker API before the agent run loop starts.

### Gap Detection and Repair

After each incoming M5 candle, the container checks the last `200` stored bars for gaps (missing 5-minute intervals). Gaps trigger a `CANDLE_GAP_DETECTED` event, which causes the broker adapter to fetch the missing bars and re-insert them.

### Timeframe Limits

| Timeframe | Default max candles returned |
|---|---|
| M5 | 300 |
| M15 | 150 |
| M30 | 100 |
| H1 | 200 |
| H4 | 100 |
| D1 | 60 |

### Key Methods

```python
await container.get_candles(broker_name, pair, timeframe, count=None)
# Returns list[Candle]
# M5 → direct DB query
# H1, H4, D1, M15, M30 → DB query for sufficient M5 bars → resampler

await container.get_snapshot(broker_name, pair)
# Returns MarketSnapshot with candles at all timeframes

container.register_broker(broker, pairs)
# Registers a broker and its pairs, creates DB tables if needed

await container.initialize()
# Back-fills data for all registered pairs
```

---

## `resampler.py` — Candle Resampler

Aggregates M5 candles into higher timeframes using UTC floor boundaries.

### Boundary Alignment

OANDA uses **open-time timestamps**, so a 09:05 M5 candle covers the interval 09:05–09:10. The resampler assigns candles to their timeframe bucket by flooring the timestamp to the nearest boundary:

```
M5 candles 09:05, 09:10, 09:15, 09:20, 09:25, 09:30
H1 bucket  09:00 ─────────────────────────────────────► open=09:05, close=09:30
```

The first M5 within a bucket sets the `open`; the last sets `close`; `high`/`low` are the max/min across all bars; `volume` is summed.

### M5 Multipliers

| Timeframe | M5 bars needed |
|---|---|
| M15 | 3 |
| M30 | 6 |
| H1 | 12 |
| H4 | 48 |
| D1 | 288 |

### Example: Requesting the Last D1 Candle

1. Container queries DB for the last `288 × 60 = 17,280` M5 bars (a month's worth, capped at DB extent)
2. Resampler groups them into D1 buckets
3. Returns the last complete D1 candle

This happens entirely in RAM for small counts; no separate API call is made.

---

## `indicators.py` — Technical Indicators

Pure NumPy functions. No side effects, no I/O. All functions take `list[Candle]` and return a numeric result or series.

### Available Indicators

| Indicator | Function | Returns |
|---|---|---|
| EMA | `ema(candles, period)` | Last value (float) |
| SMA | `sma(candles, period)` | Last value (float) |
| RSI | `rsi(candles, period)` | Last value (float) |
| Stochastic | `stochastic(candles, k, d)` | `(k_value, d_value)` |
| MACD | `macd(candles, fast, slow, signal)` | `(macd, signal, histogram)` |
| Bollinger Bands | `bollinger_bands(candles, period, std)` | `(upper, middle, lower)` |
| ATR | `atr(candles, period)` | Last value (float) |
| VWAP | `vwap(candles)` | Value (float) |

---

## `indicator_tools.py` — Tool-Facing Dispatcher

Bridges the `calculate_indicator` LLM tool with the underlying indicator functions. When an agent calls `calculate_indicator(indicator="RSI", period=14, pair="EURUSD")`:

1. `IndicatorToolset.calculate()` is called (async)
2. Fetches candles from `DataContainer.get_candles()` for the requested pair/timeframe
3. Dispatches to the correct function in `indicators.py`
4. Returns a JSON-serialisable dict with the result

---

## `correlation.py` — Pair Correlation

Computes rolling Pearson correlation between currency pairs using close prices. Used by `supervisor/correlation_checker.py` to enforce portfolio diversification (e.g., block a EURUSD long if GBPUSD long is already open and correlation is > 0.85).

---

## `normalizer.py` — Data Normalisation

Utilities for standardising candle and price data:
- OHLCV format conversion
- Pip normalisation (4-digit vs 5-digit pairs)
- Timestamp normalisation to UTC


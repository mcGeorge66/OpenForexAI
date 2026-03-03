# tests/unit — Unit Tests

Fast, isolated unit tests. No file I/O, no network access, no asyncio event loops running. Tests execute in milliseconds.

## Test Files

| File | Component tested |
|---|---|
| `test_models.py` | Pydantic domain models |
| `test_data_container.py` | DataContainer candle logic, resampling, gap detection |
| `test_analysis_tools.py` | Technical indicator calculations |
| `test_correlation.py` | Pair correlation matrix |
| `test_pattern_detector.py` | Trade pattern detection |
| `test_risk_engine.py` | Risk assessment engine |

---

## Running

```bash
pytest tests/unit/         # run all unit tests
pytest tests/unit/ -v      # verbose output
pytest tests/unit/ -x      # stop on first failure
pytest tests/unit/test_data_container.py  # single file
```

---

## Key Test Areas

### `test_models.py`
- Pydantic field validation (required fields, type coercion)
- Enum value constraints
- Default values
- JSON serialisation / deserialisation roundtrips

### `test_data_container.py`
- Resampler boundary alignment (M30 candle covers exactly 6 M5 bars at the correct UTC floor)
- Gap detection logic (missing M5 intervals flagged correctly)
- Duplicate candle filtering (`_last_ts` deduplication)
- `get_candles()` with various timeframes and counts

### `test_analysis_tools.py`
- RSI calculation correctness (verified against known reference values)
- EMA vs SMA behaviour
- ATR on volatile vs calm data
- MACD signal line calculation
- Bollinger Bands standard deviation multiplier

### `test_risk_engine.py`
- Drawdown limit enforcement
- Max position count enforcement
- Risk-per-trade calculation
- Correlated pair rejection

---

## Conventions

- Test functions are `def` (not `async def`) unless testing async code
- Candle data built with `conftest.make_candle()` or local factories
- No external dependencies imported in test bodies
- Assertions are explicit — no magic matchers

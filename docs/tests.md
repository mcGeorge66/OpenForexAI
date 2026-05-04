[Back to Documentation Index](./README.md)

# tests — Test Suite

Three-tier test pyramid: fast unit tests, adapter-mocked integration tests, and a full end-to-end system test.

## Structure

```
tests/
├── conftest.py          # Shared fixtures and mock implementations
├── unit/                # Fast, no I/O, no external dependencies
├── integration/         # Per-agent tests with mocked adapters
└── e2e/                 # Full bootstrap + complete cycle test
```

## Running Tests

```bash
# All tests
pytest

# Fast tests only (unit)
pytest tests/unit/

# Integration tests
pytest tests/integration/

# End-to-end test
pytest tests/e2e/

# With verbose output
pytest -v

# With coverage
pytest --cov=openforexai --cov-report=html
```

All tests use `asyncio_mode = "auto"` (configured in `pyproject.toml`) — no `@pytest.mark.asyncio` decorator needed.

---

## `conftest.py` — Shared Fixtures

Provides reusable mock implementations and factory functions used across all test tiers.

### Mock Adapters

#### `MockLLMProvider`
Implements `AbstractLLMProvider`. Configurable responses:
```python
# In tests
mock_llm = MockLLMProvider(
    responses=["BIAS_LONG", "HOLD"],     # sequential responses
    tool_calls=[{"name": "get_candles", "arguments": {...}}]
)
```

#### `MockBroker`
Implements `AbstractBroker`. Records all calls for assertion:
```python
mock_broker = MockBroker(short_name="MOCKB")
await mock_broker.place_order(order)
assert len(mock_broker.placed_orders) == 1
```

#### `MockRepository`
Implements `AbstractRepository`. In-memory storage (no file I/O):
```python
repo = MockRepository()
await repo.save_candles("MOCKB", "EURUSD", candles)
result = await repo.get_candles("MOCKB", "EURUSD", "M5", limit=50)
```

### Factory Functions

```python
make_candle(close=1.1000, timeframe="H1")     # → Candle
make_tick(pair="EURUSD", bid=1.1000)          # → Tick
make_snapshot(pair="EURUSD")                  # → MarketSnapshot
make_account_status(broker_name="MOCKB")      # → AccountStatus
```

---

## `tests/unit/` — Unit Tests

Fast, pure unit tests. No file I/O, no network, no asyncio overhead.

| File | Tests |
|---|---|
| `test_models.py` | Pydantic model validation, field constraints |
| `test_data_container.py` | DataContainer logic (gap detection, resampling boundaries) |
| `test_analysis_tools.py` | Technical indicator calculations |
| `test_correlation.py` | Correlation matrix computation |
| `test_pattern_detector.py` | Trade pattern detection algorithm |
| `test_risk_engine.py` | Risk assessment rules |

### Example

```python
# tests/unit/test_data_container.py
def test_m30_boundary_alignment():
    """M30 candle from 13:00 must include M5 bars 13:05–13:30."""
    m5_bars = [make_candle_at(t) for t in [
        "13:05", "13:10", "13:15", "13:20", "13:25", "13:30"
    ]]
    result = resample_candles(m5_bars, "M30")
    assert result[0].timestamp.hour == 13
    assert result[0].timestamp.minute == 0  # floor to M30 boundary
    assert result[0].open == m5_bars[0].open
    assert result[0].close == m5_bars[-1].close
```

---

## `tests/integration/` — Integration Tests

Per-agent integration tests. The agent, EventBus, and ToolDispatcher are real; LLM and broker are mocked.

| File | Tests |
|---|---|
| `test_technical_analysis_agent.py` | AA agent: full cycle from M5 candle event to analysis output |
| `test_trading_agent.py` | BA agent: signal processing, order placement, risk checks |
| `test_supervisor_agent.py` | Supervisor: signal approval/rejection based on risk parameters |
| `test_optimization_agent.py` | Optimization GA: prompt evolution and backtest integration |

### Example

```python
# tests/integration/test_technical_analysis_agent.py
async def test_aa_agent_publishes_analysis_on_m5_candle(
    event_bus, mock_llm, mock_broker, mock_repo
):
    """AA agent should publish ANALYSIS_RESULT when M5 candle arrives."""
    agent = Agent("OAPR1_EURUSD_AA_ANLYS", event_bus, data_container, mock_repo)
    asyncio.create_task(agent.start())

    # Simulate M5 candle arriving
    await event_bus.publish(AgentMessage(
        event_type=EventType.M5_CANDLE_AVAILABLE,
        source_agent_id="broker:oanda",
        payload={"broker": "OAPR1", "pair": "EURUSD"}
    ))

    # Wait for agent to process
    await asyncio.sleep(0.1)

    # Verify analysis was published
    assert mock_llm.call_count == 1
    assert len(captured_analysis_results) == 1
```

---

## `tests/e2e/` — End-to-End Tests

Full system test: bootstraps all components, runs one complete cycle, verifies the output.

| File | Tests |
|---|---|
| `test_full_cycle.py` | Full bootstrap → agent cycle → DB record → shutdown |

```bash
pytest tests/e2e/ -v
```

The E2E test:
1. Bootstraps the complete system with mock adapters (no real broker/LLM)
2. Injects a synthetic M5 candle event
3. Verifies the AA agent runs a complete LLM cycle
4. Verifies the BA agent receives the analysis result
5. Verifies the agent decision is persisted to the (in-memory) repository
6. Shuts down gracefully

---

## Live Connectivity Tests (Root Level)

```bash
# Requires real credentials
python test_broker.py    # Tests OANDA or MT5 connection
python test_llm.py       # Tests Azure OpenAI / OpenAI / Anthropic connection
```

These are manual tests, not part of the pytest suite. Run them to verify credentials and connectivity before deploying.

---

## Test Configuration

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

No `@pytest.mark.asyncio` decorators are needed — pytest-asyncio runs all async test functions automatically.


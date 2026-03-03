# tests/e2e — End-to-End Tests

Full system test: bootstraps all components, runs a complete agent cycle, verifies end-to-end behaviour from event to database record.

## Test Files

| File | What it tests |
|---|---|
| `test_full_cycle.py` | Complete bootstrap → candle event → agent cycle → DB persistence → shutdown |

---

## Running

```bash
pytest tests/e2e/
pytest tests/e2e/ -v -s   # with stdout output (useful to see the full cycle)
```

**Note:** E2E tests take longer than unit/integration tests (several seconds) because they boot the full system and run real asyncio tasks. They use mocked LLM and broker adapters, so no real API credentials are needed.

---

## What `test_full_cycle.py` Tests

```
1. Bootstrap
   └── Load config, init EventBus, RoutingTable, ConfigService
   └── Create MockBroker, MockLLM, MockRepository
   └── Create DataContainer
   └── Create ManagementServer (on random free port)
   └── Create Agent(s) from system.json definitions
   └── Start all tasks in asyncio.TaskGroup

2. Inject M5 Candle
   └── Publish M5_CANDLE_AVAILABLE event for EURUSD
   └── Wait for DataContainer to store candle

3. Agent Cycle
   └── AA agent wakes, requests config, initialises, runs LLM cycle
   └── LLM (mock) calls get_candles + calculate_indicator
   └── LLM returns ANALYSIS_RESULT payload
   └── Agent publishes ANALYSIS_RESULT

4. BA Agent Receives Analysis
   └── BA agent wakes on ANALYSIS_RESULT
   └── BA evaluates signal, checks account (via MockBroker)
   └── If signal warrants trade: calls place_order → MockBroker records it

5. Verify Side Effects
   └── assert MockBroker.placed_orders has expected entries (or none)
   └── assert MockRepository.agent_decisions has decision records
   └── assert ANALYSIS_RESULT was published to bus

6. Graceful Shutdown
   └── Cancel TaskGroup
   └── Verify no error logs
   └── Verify all asyncio tasks cleaned up
```

---

## Test Configuration

The E2E test uses the real `system.json` with mock adapters injected at bootstrap time:

```python
@pytest.fixture
async def full_system():
    config = load_json_config(Path("config/system.json"))
    mock_llm = MockLLMProvider(...)
    mock_broker = MockBroker(short_name="OAPR1")
    mock_repo = MockRepository()

    # Override registry to inject mocks
    RuntimeRegistry.set_llm("azure_openai", mock_llm)
    RuntimeRegistry.set_broker("oanda", mock_broker)

    # Bootstrap with mocks
    system = await bootstrap(config, repository=mock_repo)
    yield system
    await system.shutdown()
```

---

## Debugging E2E Failures

If the E2E test fails:

1. **Run with `-s`** to see all log output:
   ```bash
   pytest tests/e2e/ -v -s
   ```

2. **Increase timeouts** — if agents take longer than expected:
   ```python
   await asyncio.sleep(2.0)  # was 0.1 — increase if agents are slow
   ```

3. **Check routing rules** — if agents don't receive events, the routing table may not match the test setup. Print the routing table with:
   ```python
   print(routing_table.rules)
   ```

4. **Check MockLLM responses** — the mock must return valid JSON in the format the BA agent expects. Mismatched JSON structure causes silent failures.

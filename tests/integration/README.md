# tests/integration — Integration Tests

Per-agent integration tests. The agent class, EventBus, ToolDispatcher, and DataContainer are real. External dependencies (LLM, broker, database) are mocked.

These tests verify that the full agent lifecycle works correctly: config bootstrap, event handling, LLM tool-use loop, tool execution, and event publishing.

## Test Files

| File | Agent under test |
|---|---|
| `test_technical_analysis_agent.py` | AA agent — analysis cycle |
| `test_trading_agent.py` | BA agent — trade execution cycle |
| `test_supervisor_agent.py` | Supervisor — signal approval/rejection |
| `test_optimization_agent.py` | GA agent — prompt optimization cycle |

---

## Running

```bash
pytest tests/integration/
pytest tests/integration/ -v
pytest tests/integration/test_technical_analysis_agent.py
```

---

## Test Architecture

Each integration test:

1. **Creates real components:**
   - `EventBus` with a real routing table
   - `Agent` instance
   - `ToolDispatcher` with real tool implementations

2. **Injects mocks via `conftest.py`:**
   - `MockLLMProvider` — returns scripted responses or tool calls
   - `MockBroker` — records placed orders, returns mock positions
   - `MockRepository` — in-memory storage

3. **Drives the agent via events:**
   ```python
   await bus.publish(AgentMessage(
       event_type=EventType.M5_CANDLE_AVAILABLE,
       source_agent_id="broker:oanda",
       payload={"broker": "OAPR1", "pair": "EURUSD"},
   ))
   await asyncio.sleep(0.1)  # let the agent process
   ```

4. **Asserts on side effects:**
   - Messages published to the bus
   - Orders recorded in `MockBroker.placed_orders`
   - Decisions recorded in `MockRepository`
   - LLM call count and arguments

---

## Key Test Scenarios

### AA Agent (`test_technical_analysis_agent.py`)

- **M5 candle triggers analysis:** Agent wakes on `M5_CANDLE_AVAILABLE` and publishes `ANALYSIS_RESULT`
- **Tool-use loop:** Agent calls `get_candles` and `calculate_indicator` before providing output
- **Context tier downgrade:** When `MockLLM` returns high token counts, fewer tools are available in subsequent turns
- **Query response:** Agent responds to `AGENT_QUERY` with a complete answer
- **Timer trigger:** Agent runs a cycle when the timer fires (even without an event)

### BA Agent (`test_trading_agent.py`)

- **Analysis result → order:** Agent places an order when receiving a positive analysis result
- **Supervisor approval flow:** `place_order` with `approval_mode=supervisor` waits for approval event
- **Risk breach → close all:** Agent closes positions when receiving `RISK_BREACH`
- **Account check before order:** Agent calls `get_account_status` before placing

### Supervisor (`test_supervisor_agent.py`)

- **Signal approved:** Low-risk signal is approved within 15s
- **Signal rejected:** High-drawdown signal is rejected with reason
- **Correlation rejection:** Second position in correlated pair rejected

---

## Mock LLM Configuration

```python
# Single scripted response
mock_llm = MockLLMProvider(responses=[
    '{"bias": "BIAS_LONG", "reasoning": "EMA50 above EMA200"}'
])

# Multi-turn with tool calls
mock_llm = MockLLMProvider(turns=[
    # Turn 0: LLM wants to call get_candles
    LLMResponseWithTools(
        content=None,
        stop_reason="tool_use",
        tool_calls=[ToolCall(id="t1", name="get_candles", arguments={"timeframe": "H1"})]
    ),
    # Turn 1: After seeing candles, LLM gives final answer
    LLMResponseWithTools(
        content='{"bias": "BIAS_LONG"}',
        stop_reason="end_turn",
    ),
])
```

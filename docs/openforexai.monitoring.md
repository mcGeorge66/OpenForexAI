[Back to Documentation Index](./README.md)

# openforexai/monitoring — Observability Bus

Fire-and-forget event bus for system-wide observability. Every significant action in the system emits a `MonitoringEvent` — LLM calls, tool executions, candle fetches, account updates, errors. These events power the `tools/monitor.py` console tool.

## Files

| File | Purpose |
|---|---|
| `bus.py` | `MonitoringBus` — in-process event bus with ring buffer |

---

## `bus.py` — MonitoringBus

### Design Principles

1. **Never blocks the main system** — `emit()` is synchronous and never raises. If a subscriber queue is full, the event is silently dropped.
2. **Fire-and-forget** — emitters don't wait for subscribers. No backpressure.
3. **Ring buffer** — the last 1,000 events are always accessible via `recent_events()`, enabling HTTP polling by `monitor.py`.

### Architecture

```
Any component → MonitoringBus.emit(event)
                    │
                    ├── Appended to ring buffer (deque, maxlen=1000)
                    │
                    └── put_nowait() into each subscriber queue
                            (dropped silently if queue is full)

HTTP polling ← recent_events(since=last_timestamp, limit=100)
```

### Ring Buffer

Capacity: **1,000 events** (configurable via `RING_BUFFER_SIZE`). Old events are automatically evicted as new ones arrive. The `GET /monitoring/events` API endpoint reads from this buffer — the `tools/monitor.py` tool polls it every 2 seconds by default.

### Subscriber Queues

Subscribers (e.g., a live dashboard, test assertions) can register queues:

```python
queue = monitoring_bus.subscribe()   # asyncio.Queue(maxsize=10_000)

# In a consumer task:
event = await queue.get()
```

The default queue size is 10,000. Events are dropped for slow consumers (no blocking).

### Key Methods

```python
bus = MonitoringBus()

# Emit an event (fire-and-forget, never raises)
bus.emit(MonitoringEvent(
    timestamp=datetime.now(timezone.utc),
    source_module="agent",
    event_type=MonitoringEventType.LLM_RESPONSE,
    broker_name="OAPR1",
    pair="EURUSD",
    payload={"turn": 2, "tokens": 450, "stop_reason": "end_turn"},
))

# Subscribe a consumer queue
queue = bus.subscribe()

# Unsubscribe
bus.unsubscribe(queue)

# HTTP polling (for monitor.py)
events = bus.recent_events(since=last_poll_ts, limit=100)

# Convenience factory
event = bus.build_event(
    source_module="broker",
    event_type=MonitoringEventType.M5_CANDLE_FETCHED,
    broker_name="OAPR1",
    pair="EURUSD",
    open=1.0821, close=1.0824,
)
bus.emit(event)
```

---

## MonitoringEventType Values

Defined in `openforexai/models/monitoring.py`:

| Event Type | Emitted by | Meaning |
|---|---|---|
| `LLM_REQUEST` | Agent | LLM call started (system prompt, messages, tools) |
| `LLM_RESPONSE` | Agent | LLM call completed (content, tokens, stop reason) |
| `LLM_ERROR` | Agent | LLM call failed |
| `TOOL_CALL_STARTED` | ToolDispatcher | Tool invocation started (name, arguments) |
| `TOOL_CALL_COMPLETED` | ToolDispatcher | Tool call succeeded (result) |
| `TOOL_CALL_FAILED` | ToolDispatcher | Tool call raised an exception |
| `EVENT_BUS_MESSAGE` | EventBus | Message dispatched on EventBus |
| `AGENT_QUEUE_FULL` | EventBus | Agent's inbox queue was full — event dropped |
| `DATA_CONTAINER_ACCESS` | DataContainer | Candle read or snapshot |
| `M5_CANDLE_FETCHED` | BrokerBase | Incoming M5 candle (OHLCV + spread) |
| `ACCOUNT_STATUS_UPDATED` | BrokerBase | Account balance/equity updated |
| `BROKER_CONNECTED` | BrokerBase | Broker connection established |
| `BROKER_DISCONNECTED` | BrokerBase | Broker connection lost |
| `CANDLE_GAP_DETECTED` | DataContainer | Gap in M5 sequence detected |
| `CANDLE_REPAIR_REQUESTED` | DataContainer | Gap repair initiated |
| `CANDLE_REPAIR_COMPLETED` | DataContainer | Gap repair finished |
| `SYNC_DISCREPANCY_FOUND` | OrderBook | Order book sync mismatch |
| `SYSTEM_ERROR` | Any | Unhandled exception or critical error |
| `ROUTING_RELOADED` | EventBus | Routing table hot-reloaded |
| `ROUTING_RELOAD_FAILED` | EventBus | Routing table reload failed |
| `UNMATCHED_EVENT` | EventBus | Published event had no matching routing rule |

---

## Integration with monitor.py

`tools/monitor.py` polls `GET /monitoring/events` every 2 seconds (configurable). The Management API reads from `MonitoringBus.recent_events()` and returns the events as JSON. The monitor then displays them with colour-coded formatting.

See [`tools/README.md`](./openforexai.tools.md) for full monitor.py documentation.

---

## Performance

- `emit()` is O(n) where n = number of subscribers (typically 1–2)
- The ring buffer is a `collections.deque(maxlen=1000)` — O(1) append
- No asyncio overhead in the emit path — `put_nowait()` is used
- The monitoring subsystem adds zero latency to the main system under normal conditions


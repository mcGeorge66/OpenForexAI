# openforexai/messaging — EventBus & Routing

The message-passing backbone of OpenForexAI. All inter-component and inter-agent communication flows through the `EventBus`. Routing is rule-based and hot-reloadable.

## Files

| File | Purpose |
|---|---|
| `bus.py` | `EventBus` — async pub/sub with two delivery modes |
| `routing.py` | `RoutingTable` — rule-based target resolution |
| `agent_id.py` | Agent ID parsing and pattern matching |

---

## `bus.py` — EventBus

The central message bus. All components communicate by publishing `AgentMessage` objects and either:
- **registering a queue** (agents), or
- **subscribing a handler** (infrastructure: DataContainer, BrokerBase, Management API)

### Two Delivery Modes

```
publish(message)
    │
    ▼
dispatch loop (asyncio.Task)
    │
    ├── Legacy handlers (always called, bypass routing rules)
    │   subscribe(EventType.M5_CANDLE_AVAILABLE, handler)
    │
    ├── Direct targeting (target_agent_id set, bypass routing)
    │   → put into that agent's personal Queue
    │
    └── Routing table resolution
        → resolved agent IDs → put into their Queues
```

**Mode 1 — Queue-based (agents):** Each agent registers with `register_agent(agent_id)` and receives a personal `asyncio.Queue(maxsize=1000)`. The routing table decides which agent queues receive each published message.

**Mode 2 — Handler-based (infrastructure):** Infrastructure components call `subscribe(event_type, handler)`. These handlers are called for every matching message, bypassing routing rules entirely (backward compatibility).

### Direct Targeting

If a message has `target_agent_id` set, it bypasses the routing table entirely and goes directly into that agent's queue. Used for:
- `AGENT_CONFIG_RESPONSE` (ConfigService → specific agent)
- `AGENT_QUERY` (Management API → specific agent)

### Dispatch Loop

A single long-running asyncio task reads from the internal inbound queue and dispatches messages:

```python
asyncio.create_task(bus.start_dispatch_loop())
```

The loop processes messages sequentially to preserve order while remaining non-blocking.

### Backpressure

Agent queues are bounded at `1,000` messages. If a queue is full, the message is **dropped** (not buffered indefinitely). A `AGENT_QUEUE_FULL` monitoring event is emitted.

### Hot-Reload

```python
await bus.reload_routing()
```

Atomically swaps the routing table. Safe to call while the system is running.

### Usage Example

```python
routing = RoutingTable()
routing.load(Path("config/event_routing.json"))
bus = EventBus(routing)

# Agent registers its inbox
queue = bus.register_agent("OAPR1_EURUSD_AA_ANLYS")

# Infrastructure subscribes a handler
bus.subscribe(EventType.M5_CANDLE_AVAILABLE, data_container._on_m5_candle)

# Start the dispatch loop
asyncio.create_task(bus.start_dispatch_loop())

# Publish a message
await bus.publish(AgentMessage(
    event_type=EventType.M5_CANDLE_AVAILABLE,
    source_agent_id="broker:oanda",
    payload={"broker": "OAPR1", "pair": "EURUSD", ...}
))
```

---

## `routing.py` — RoutingTable

Loads and evaluates routing rules from `config/event_routing.json`.

### Rule Format

```json
{
  "rules": [
    {
      "id":          "aa_to_ba_analysis",
      "description": "Analysis results from AA go to the same-broker BA",
      "event":       "analysis_result",
      "from":        "OAPR1_*_AA_*",
      "to":          "OAPR1_ALL..._BA_TRADE",
      "priority":    10
    }
  ]
}
```

### `to` Target Types

| Type | Example | Behaviour |
|---|---|---|
| Literal agent ID | `"OAPR1_ALL..._BA_TRADE"` | Delivered to that single agent |
| Template | `"OAPR1_{sender.pair}_AA_*"` | Substitutes sender's broker/pair/type/name |
| Wildcard pattern | `"*_EURUSD_AA_*"` | Fan-out to all matching registered agents |
| Global broadcast | `"*"` | Delivered to all registered agents |
| `"@handlers"` | `"@handlers"` | Delivered only to legacy handler-subscribers |

### Priority

Rules are evaluated in **ascending priority order** (lower number = higher priority). All matching rules are applied — the union of their resolved targets receives the message.

### Thread Safety

The rule list is replaced atomically on hot-reload (Python GIL-safe list assignment). Safe for concurrent reads.

---

## `agent_id.py` — Agent ID Helpers

Parses and pattern-matches agent IDs in the standard format:

```
[BROKER(5)]_[PAIR(6)]_[TYPE(2)]_[NAME(1-5)]
```

### Examples

| ID | broker | pair | type | name |
|---|---|---|---|---|
| `OAPR1_EURUSD_AA_ANLYS` | `OAPR1` | `EURUSD` | `AA` | `ANLYS` |
| `OAPR1_ALL..._BA_TRADE` | `OAPR1` | `ALL...` | `BA` | `TRADE` |
| `SYSTM_ALL..._GA_CFGSV` | `SYSTM` | `ALL...` | `GA` | `CFGSV` |

### Pattern Matching

Used by routing rules with wildcards:

```python
AgentId.try_parse("OAPR1_EURUSD_AA_ANLYS").matches("OAPR1_*_AA_*")  # → True
AgentId.try_parse("OAPR1_EURUSD_AA_ANLYS").matches("*_EURUSD_*_*")  # → True
AgentId.try_parse("OAPR1_EURUSD_AA_ANLYS").matches("OAPR1_*_BA_*")  # → False
```

### Template Substitution

Used by routing rules with `{sender.*}` placeholders:

```python
substitute_template("OAPR1_{sender.pair}_BA_TRADE", sender_aid)
# → "OAPR1_EURUSD_BA_TRADE"
```

---

## Event Flow Overview

```
Broker (M5 candle arrives)
    ↓
bus.publish(M5_CANDLE_AVAILABLE)
    ├── handler: DataContainer._on_m5_candle() → stores to DB
    └── routing: → OAPR1_EURUSD_AA_ANLYS queue

AA Agent (woken by M5_CANDLE_AVAILABLE)
    ↓ runs LLM cycle ↓
bus.publish(ANALYSIS_RESULT)
    └── routing rule "aa_to_ba" → OAPR1_ALL..._BA_TRADE queue

BA Agent (woken by ANALYSIS_RESULT)
    ↓ evaluates signal ↓
bus.publish(ORDER_PLACED)
    └── routing: → monitoring, GA, etc.
```

---

## Unmatched Events

If no routing rule matches AND no handler is registered for an event, the message is **silently discarded** and a `UNMATCHED_EVENT` monitoring entry is emitted (at DEBUG level). This is expected for events that are intentionally local (e.g., `AGENT_CONFIG_RESPONSE` is direct-targeted and never goes through routing rules).

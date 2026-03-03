# openforexai/utils — Utilities

Shared helper utilities used throughout the codebase. No business logic — pure infrastructure helpers.

## Files

| File | Purpose |
|---|---|
| `logging.py` | Structlog configuration and `get_logger()` factory |
| `retry.py` | Exponential backoff decorator for async functions |
| `time_utils.py` | UTC helpers and forex session detection |
| `metrics.py` | Performance metrics collection |

---

## `logging.py` — Structured Logging

All logging in OpenForexAI uses **structlog** for structured, context-rich log output.

### Usage

```python
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)

# Simple log
_log.info("Agent starting", agent_id="OAPR1_EURUSD_AA_ANLYS")

# Bound context (all subsequent calls include agent_id automatically)
logger = _log.bind(agent_id=self.agent_id, pair="EURUSD")
logger.debug("Fetching candles", timeframe="H1", count=200)
logger.error("Tool call failed", tool="get_candles", error=str(exc))
```

### Configuration

Log level is set via environment variable:

```bash
OPENFOREXAI_LOG_LEVEL=DEBUG    # verbose (tool calls, every event)
OPENFOREXAI_LOG_LEVEL=INFO     # normal (agent cycles, connections)
OPENFOREXAI_LOG_LEVEL=WARNING  # quiet (only warnings and errors)
```

### Output Format

- **Development** (TTY detected): coloured, human-readable key=value output
- **Production** (no TTY / JSON mode): JSON lines, machine-parseable

```
# Development
2026-03-02 12:34:56 [info     ] Agent starting   agent_id=OAPR1_EURUSD_AA_ANLYS
2026-03-02 12:34:57 [debug    ] Fetching candles  timeframe=H1  count=200

# Production
{"timestamp": "2026-03-02T12:34:56Z", "level": "info", "event": "Agent starting", "agent_id": "OAPR1_EURUSD_AA_ANLYS"}
```

### Convention

Every module uses the module-level pattern:
```python
_log = get_logger(__name__)
```

**Never** use `logging.getLogger()` directly in this codebase.

---

## `retry.py` — Exponential Backoff

A decorator for async functions that retries on exceptions with exponential backoff.

### Usage

```python
from openforexai.utils.retry import retry

@retry(max_attempts=3, base_delay=1.0, max_delay=30.0)
async def call_api():
    ...
```

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `max_attempts` | `3` | Total attempts (including first try) |
| `base_delay` | `1.0` | Initial delay in seconds |
| `max_delay` | `30.0` | Maximum delay cap |
| `exceptions` | `Exception` | Exception types to catch |

Delay formula: `min(base_delay * 2^(attempt-1), max_delay)` + random jitter.

### Applied to LLM Adapters

The `llm_retry` decorator in `adapters/llm/base.py` wraps all `complete*` methods automatically to handle rate limits and transient API errors:

```python
# adapters/llm/base.py
def llm_retry(func):
    return retry(max_attempts=3, base_delay=2.0, max_delay=60.0)(func)
```

---

## `time_utils.py` — Time Helpers

### UTC Utilities

```python
from openforexai.utils.time_utils import utcnow, floor_to_m5

now = utcnow()                    # datetime with UTC timezone
m5_ts = floor_to_m5(timestamp)   # floor to nearest 5-minute boundary
```

`floor_to_m5()` is used by the resampler and gap detection to align M5 candle timestamps to the correct 5-minute boundary.

### Forex Session Detection

```python
from openforexai.utils.time_utils import detect_session

session = detect_session(utcnow())
# Returns: "ASIAN" | "EUROPEAN" | "US" | "OVERLAP_EU_US" | "CLOSED"
```

Session boundaries (UTC):
- **Asian**: 00:00 – 09:00
- **European**: 08:00 – 17:00
- **US**: 13:00 – 22:00
- **EU/US Overlap**: 13:00 – 17:00
- **Closed**: 22:00 – 00:00

Session context is available in the agent's `MarketSnapshot` and can be referenced in system prompts for session-aware trading decisions.

---

## `metrics.py` — Performance Metrics

Lightweight in-memory metrics for the Management API `/metrics` endpoint.

### Tracked Metrics

```python
# Counters (increment-only)
metrics.increment("messages_dispatched")
metrics.increment("tool_calls_executed")
metrics.increment("llm_requests")
metrics.increment("system_errors")

# Gauges (current value)
metrics.set_gauge("active_agents", 3)
metrics.set_gauge("queue_depth_aa", 0)

# Read
all_metrics = metrics.snapshot()
# → {"messages_dispatched": 1423, "tool_calls_executed": 89, ...}
```

These metrics are exposed at `GET /metrics` and can be scraped by monitoring tools.

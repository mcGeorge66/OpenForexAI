# openforexai/management — Management API

The control plane for the running system. A FastAPI application served by a non-blocking uvicorn task, exposing REST endpoints for monitoring, introspection, and agent interaction.

## Files

| File | Purpose |
|---|---|
| `api.py` | FastAPI application — all endpoint definitions |
| `server.py` | Uvicorn wrapper — runs as a background asyncio task |

---

## `api.py` — FastAPI Application

### Endpoints

#### System

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | System health: uptime, agents alive, queue depths |
| `GET` | `/metrics` | Key counters: messages dispatched, tool calls, errors |

#### Agents

| Method | Path | Description |
|---|---|---|
| `GET` | `/agents` | List all registered agents with queue depths |
| `GET` | `/agents/{agent_id}` | Single agent info |
| `POST` | `/agents/{agent_id}/ask` | Query any agent — blocks until agent responds |

#### Routing

| Method | Path | Description |
|---|---|---|
| `GET` | `/routing/rules` | Current routing rules as JSON |
| `POST` | `/routing/reload` | Hot-reload routing table from `config/RunTime/event_routing.json5` |

#### Events & Config

| Method | Path | Description |
|---|---|---|
| `POST` | `/events` | Inject an arbitrary event into the EventBus |
| `POST` | `/config/reload` | Trigger agents to re-read their config |

#### Observability

| Method | Path | Description |
|---|---|---|
| `GET` | `/monitoring/events` | Recent events from the ring buffer (used by `monitor.py`) |
| `GET` | `/indicators` | List registered technical indicators |
| `GET` | `/tools` | List registered tool plugins |

---

### Authentication

Static API key via `X-API-Key` header. Set `MANAGEMENT_API_KEY` environment variable to enable. When the variable is not set, the API is open (development mode).

```bash
# Protected request
curl -H "X-API-Key: mysecret" http://127.0.0.1:8765/agents
```

---

### `POST /agents/{agent_id}/ask` — Agent Query

Queries any running agent and returns its response. The agent runs a full LLM + tool cycle to answer.

**Request:**
```json
{
  "question": "What is the current EURUSD trend on H1?",
  "timeout": 120
}
```

**Response:**
```json
{
  "correlation_id": "3f2a1c8e-...",
  "agent_id": "OAPR1_EURUSD_AA_ANLYS",
  "response": "{\"bias\": \"BIAS_LONG\", \"reasoning\": \"...\"}"
}
```

**Implementation flow:**
```
POST /agents/{id}/ask
    │
    ├── Creates asyncio.Future keyed by correlation_id
    ├── Publishes AGENT_QUERY event (direct-targeted to agent)
    │
    ▼
Agent._run_message_loop()
    └── detects AGENT_QUERY → runs _run_cycle(trigger="agent_query")
        └── publishes AGENT_QUERY_RESPONSE
              │
              ▼
_on_agent_query_response() (handler subscribed to EventBus)
    └── resolves Future with response payload
              │
              ▼
POST handler receives result → returns HTTP 200

Timeout → HTTP 504 (if agent takes longer than timeout seconds)
```

**Timeouts:** `--timeout` defaults to 120s (range: 5–300s). HTTP client timeout is set to `timeout + 15s` to account for network overhead.

---

### `GET /monitoring/events` — Event Stream

Powers the `tools/monitor.py` console tool. Returns recent events from the `MonitoringBus` ring buffer.

**Query parameters:**
- `since` — ISO timestamp; return only events after this time
- `limit` — max events to return (default: 100, ring buffer holds: 1,000)

**Response:** JSON array of `MonitoringEvent` objects.

---

### Dependency Injection

The API module stays import-time clean (no circular imports). Dependencies are injected at startup by `ManagementServer.build_app()`:

```python
app = build_app(
    bus=event_bus,
    routing_table=routing_table,
    tool_registry=tool_registry,
    indicator_registry=indicator_registry,
    monitoring_bus=monitoring_bus,
)
```

---

## `server.py` — ManagementServer

A thin uvicorn wrapper that runs the FastAPI app as a **non-blocking asyncio background task** alongside all agents.

```python
server = ManagementServer(
    bus=event_bus,
    routing_table=routing_table,
    tool_registry=tool_registry,
    indicator_registry=indicator_registry,
    monitoring_bus=monitoring_bus,
    host="127.0.0.1",
    port=8765,
)
asyncio.create_task(server.serve())
```

### Key Configuration

| Parameter | Default | Description |
|---|---|---|
| `host` | `127.0.0.1` | Bind address (localhost only — not exposed externally) |
| `port` | `8765` | HTTP port |
| `log_level` | `"warning"` | Uvicorn log level |

The server uses `loop="none"` to integrate with the already-running asyncio event loop without spawning a new one.

### Graceful Shutdown

```python
await server.shutdown()
# Sets uvicorn's should_exit flag → server drains and exits cleanly
```

---

## Usage Examples

```bash
# Health check
curl http://127.0.0.1:8765/health

# List agents
curl http://127.0.0.1:8765/agents

# Query an agent
curl -X POST http://127.0.0.1:8765/agents/OAPR1_EURUSD_AA_ANLYS/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Current EURUSD bias?", "timeout": 60}'

# Hot-reload routing rules
curl -X POST http://127.0.0.1:8765/routing/reload

# Get recent monitoring events
curl "http://127.0.0.1:8765/monitoring/events?limit=50"
```

See also: [`tools/ask.py`](../../tools/README.md) for a CLI wrapper around the agent query endpoint.



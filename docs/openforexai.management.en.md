[Back to Documentation Index](README.en.md)

# openforexai/management — Management API

The Management API is the control plane of the running application. It is a
FastAPI application hosted by a background uvicorn task and is used by the web
console for runtime control, inspection, configuration editing, and testing.

## Files

| File | Purpose |
|---|---|
| `api.py` | Endpoint definitions and request/response models |
| `server.py` | Background uvicorn wrapper used by the runtime |

## Main API Areas

The current API is broader than a simple health interface. It now covers:

- runtime status
- update and restart control
- agent execute/query flows
- analysis browsing
- orderbook browsing
- monitoring stream access
- direct tool execution
- raw and structured config editing
- snapshot preview
- selective config package import/export

## System and Runtime Endpoints

Important current endpoints:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Basic health information |
| `GET` | `/version` | Local application version |
| `GET` | `/runtime/status` | Current runtime state |
| `GET` | `/metrics` | Key counters and health metrics |
| `GET` | `/console/initial` | Data for the Initial UI page |
| `GET` | `/system/update/status` | Updater state and output |
| `POST` | `/system/update/start` | Start update workflow |
| `POST` | `/system/runtime/pause` | Pause runtime processing |
| `POST` | `/system/runtime/resume` | Resume runtime processing |
| `POST` | `/system/restart-now` | Immediate restart path |

## Agent Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/agents` | List running agents |
| `GET` | `/agents/{agent_id}` | Single agent detail |
| `POST` | `/agents/{agent_id}/ask` | Standard agent query |
| `POST` | `/agents/{agent_id}/execute` | Execute an inspect/test run |
| `GET` | `/agents/{agent_id}/candles` | Candle data for Agent Chat charts |

### `/agents/{agent_id}/ask`

This endpoint is used for normal interactive agent questioning. The runtime
publishes an `agent_query` event and waits for the corresponding response.

### `/agents/{agent_id}/execute`

This endpoint is used by Agent Chat `Execute`.

It runs an isolated inspection-style cycle and returns structured data that the
UI can split into:

- chat-visible output
- snapshot details
- LLM request/response
- tool traces
- runtime metrics

This is the API surface that powers configuration testing without waiting only
for live trading events.

## Snapshot and Analysis Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/config/snapshots/preview` | Build a snapshot preview for a selected agent context |
| `GET` | `/analyses` | List persisted analyses |
| `GET` | `/analyses/{record_id}` | Fetch one persisted analysis record |

The snapshot preview endpoint is used by `Snapshot Config -> Execute`.

It builds the exact runtime snapshot for the current unsaved profile state and
returns both:

- the generated snapshot
- the final decision input that would be forwarded to the LLM

## Orderbook Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/orderbook` | List order book entries |
| `GET` | `/orderbook/{entry_id}` | Get one order book entry |
| `GET` | `/orderbook/{entry_id}/candles` | Candle context for one order book entry |

These endpoints power the `Action -> Orderbook` UI and support audit and
execution review.

## Monitoring, Tools, and Routing

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/monitoring/events` | Monitoring event stream buffer |
| `GET` | `/indicators` | Registered indicator information |
| `GET` | `/tools` | Registered tool list |
| `POST` | `/tools/execute` | Execute a tool directly |
| `GET` | `/routing/rules` | Current routing table |
| `POST` | `/routing/reload` | Reload routing config |
| `POST` | `/events` | Inject an event into the EventBus |
| `POST` | `/test/llm/check` | LLM connectivity and behavior checks |

## Configuration Endpoints

The current config surface supports both targeted editors and package-style
export/import.

### Raw and structured config

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/config/view` | Masked structured system view |
| `GET` | `/config/system` | Editable structured system config |
| `GET` | `/config/system/text` | Raw `system.json5` text |
| `PUT` | `/config/system` | Save structured system config |
| `GET` | `/config/files/{name}` | Structured runtime file view |
| `GET` | `/config/files/{name}/text` | Raw runtime file text |
| `PUT` | `/config/files/{name}` | Save runtime config file |
| `GET` | `/config/modules/{module_type}` | List configured modules |
| `GET` | `/config/modules/{module_type}/{name}` | Masked module config |
| `GET` | `/config/modules/{module_type}/{name}/raw` | Structured raw module config |
| `GET` | `/config/modules/{module_type}/{name}/raw_text` | Raw module text |
| `PUT` | `/config/modules/{module_type}/{name}/raw` | Save raw module config |
| `GET` | `/config/information/readme` | Read Information page content |
| `PUT` | `/config/information/readme` | Save Information page content |

### Package manager support

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/config/packages/export` | Export selected config areas |
| `POST` | `/config/packages/validate` | Validate import package |
| `POST` | `/config/packages/import` | Import selected config areas |

Current package operations support:

- agents
- snapshot profiles
- decision prompt profiles
- bridge tools
- event routing
- system config

## Authentication

The API can be protected with `X-API-Key` if `MANAGEMENT_API_KEY` is set.
Without that environment variable the API remains open for local development.

## Server Integration

`server.py` runs uvicorn as a non-blocking background task inside the main
runtime event loop. The management server therefore lives alongside:

- the EventBus
- brokers
- agents
- monitoring
- the config service

The API is not a separate standalone control process.

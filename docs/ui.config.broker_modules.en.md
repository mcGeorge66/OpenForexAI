[Back to Config](ui.config.en.md)

# Broker Modules

Broker Modules is a direct editor for the configuration files of individual broker adapter modules. Each broker adapter has its own configuration file that can be selected and edited here. This page is intended for operators who need to adjust connection parameters, symbol mappings, polling intervals, synchronization settings, or adapter-specific options for their broker connections.

---

## Table of Contents

1. [Broker Architecture Overview](#broker-architecture-overview)
2. [Interface](#interface)
3. [Save Behavior](#save-behavior)
4. [How Broker Modules Are Registered](#how-broker-modules-are-registered)
5. [Common Configuration Fields](#common-configuration-fields)
6. [MT5 Adapter Configuration](#mt5-adapter-configuration)
7. [OANDA Adapter Configuration](#oanda-adapter-configuration)
8. [The short_name Field](#the-short_name-field)
9. [Candle Polling and Synchronization](#candle-polling-and-synchronization)
10. [broker_candle_utc_offset_hours and the Broker Module](#broker_candle_utc_offset_hours-and-the-broker-module)
11. [Symbol Maps](#symbol-maps)
12. [Multiple Broker Modules](#multiple-broker-modules)
13. [Typical Workflow](#typical-workflow)
14. [Troubleshooting Broker Connection Issues](#troubleshooting-broker-connection-issues)

---

## Broker Architecture Overview

Broker adapters are the boundary between OpenForexAI and the outside world. Each adapter handles:

- **Candle synchronization**: Polling the broker for new M5 candles and storing them in the database
- **Account queries**: Providing account balance, equity, margin, and open positions on request
- **Order execution**: Placing, modifying, and closing trades
- **Real-time updates**: Publishing candle updates and position changes to the Event Bus

### Event Bus Integration

Broker adapters register on the Event Bus as `{BROKER}-ALL___-BK-CONN`. For broker `OXS_T`, the bus member ID is `OXS_T-ALL___-BK-CONN`. Routing rules send order requests, account status requests, and position requests to this ID.

The adapter receives:
- `order_request` → execute the order
- `account_status_request` → query and return current account state
- `positions_request` → return list of open positions
- `position_close_request` → close the specified position
- `order_modify_request` → modify SL/TP on an open position

The adapter publishes:
- `m5_candle_saved` → after each new candle is stored
- `account_status_response` → in reply to account_status_request
- `positions_response` → in reply to positions_request
- `order_result` → after order placement attempt
- `position_opened` / `position_closed` → proactive position state changes

---

## Interface

### Header Bar

| Element | Function |
|---------|----------|
| **Module selector** | Dropdown listing all broker modules from `modules.broker` in `system.json5` |
| **File path** | Full path to the selected module's configuration file |
| **Refresh** | Reload the current file version from disk (active only when a module is selected) |
| **Save** | Validate and write the file (active only when a module is selected) |
| **Position** | Current cursor position as line:column |

### Module Selector

The dropdown is populated from the `modules.broker` array in `system.json5`. Each entry is a file path; the dropdown shows the filename portion (e.g. `oxs_mt5.json5`). After selecting, the editor loads the file content.

### Editor Textarea

Free-text JSON5 editing with syntax highlighting (keys: cyan, strings: green, booleans: amber, null: gray, numbers: purple).

### Status Messages

- **"Saved."** — File successfully written
- **Error message** — Parse error; file not written

---

## Save Behavior

1. Content parsed as JSON5
2. Top-level result must be a JSON object
3. On error: error message shown, file not written
4. On success: file written to disk

The broker adapter picks up new configuration at the next system start or adapter reload. Connection parameter changes (endpoint, credentials) require a full restart. Polling interval changes take effect after reload.

---

## How Broker Modules Are Registered

Path chain for a broker module:

1. `config/system.json5` has `modules.broker: ["config/broker/oxs_mt5.json5"]`
2. On startup, the system reads this path and loads `oxs_mt5.json5`
3. The adapter is instantiated and registers on the bus as `{short_name}-ALL___-BK-CONN`
4. The `short_name` field in the config determines the broker segment of the bus ID
5. Routing rules and Agent-IDs that reference this broker use the `short_name` value

Example: `short_name: "OXS_T"` → bus ID `OXS_T-ALL___-BK-CONN`, and agents for this broker have IDs like `OXS_T-EURUSD-AA-ANLYS`.

---

## Common Configuration Fields

Fields shared across all broker adapter types:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `adapter` | string | yes | Adapter implementation: `mt5`, `oanda`, or custom |
| `short_name` | string | yes | Broker identifier used in all Agent-IDs and bus routing. See dedicated section. |
| `enabled` | boolean | no | Whether to start this adapter on system startup. Default: `true`. |
| `sync_interval_seconds` | integer | no | How often to poll for new candles. Default: 60. |
| `pairs` | array | yes | List of forex pairs this adapter monitors. |
| `timeframes` | array | no | Timeframes to sync. Default: `["M5", "M15", "H1"]`. |
| `max_candle_sync_count` | integer | no | Maximum candles to fetch in a single sync request. Default: 500. |
| `candle_gap_fill_lookback_bars` | integer | no | Lookback bars to check for gaps on startup. Default: 200. |
| `connection_timeout_seconds` | integer | no | Connection attempt timeout. Default: 30. |
| `request_timeout_seconds` | integer | no | Per-request timeout. Default: 60. |

---

## MT5 Adapter Configuration

The MT5 adapter connects to a MetaTrader 5 terminal running on the same machine (or via a bridge on a remote machine). MT5 must be installed, logged into the broker account, and the MT5 Python bridge must be enabled.

```json5
{
  adapter: "mt5",
  short_name: "OXS_T",
  enabled: true,
  
  // MT5 connection
  mt5_path: "C:/Program Files/MetaTrader 5/terminal64.exe",
  login: 12345678,
  password_env: "MT5_OXS_T_PASSWORD",
  server: "OXSTrading-Server",
  
  // Pairs and timeframes
  pairs: ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"],
  timeframes: ["M5", "M15", "H1"],
  
  // Sync settings
  sync_interval_seconds: 60,
  max_candle_sync_count: 500,
  candle_gap_fill_lookback_bars: 200,
  
  // Order defaults
  default_deviation_points: 10,
  default_magic_number: 20241001,
  
  // Symbol map (if broker uses non-standard symbols)
  symbol_map: {
    "EURUSD": "EURUSDm",
    "GBPUSD": "GBPUSDm",
  }
}
```

### MT5-Specific Fields

| Field | Description |
|-------|-------------|
| `mt5_path` | Path to the MT5 terminal executable. Only needed if MT5 is not in the default installation location. |
| `login` | MT5 account number. |
| `password_env` | Name of the environment variable containing the MT5 account password. |
| `password` | Plaintext password (not recommended). |
| `server` | MT5 broker server name exactly as shown in MT5 (case-sensitive). |
| `default_deviation_points` | Maximum price deviation in points allowed for market order execution. |
| `default_magic_number` | Magic number attached to all orders placed by this system. Allows filtering system orders from manual orders in MT5. |
| `symbol_map` | Mapping from standard pair names to broker-specific symbols. See Symbol Maps section. |

### MT5 Connection Requirements

The MT5 adapter requires:
1. MetaTrader 5 terminal installed on the machine running OpenForexAI
2. Terminal logged in with an active account
3. Auto-trading enabled in the terminal
4. MT5 Python package installed in the OpenForexAI Python environment (`pip install MetaTrader5`)
5. The terminal must be running when OpenForexAI starts

### MT5 Terminal Time (Broker Server Time)

MT5 candle timestamps are in broker server local time. The `broker_candle_utc_offset_hours` setting in `system.json5` must match the broker's server UTC offset for session filtering to work correctly. See the [System Config](ui.config.system_config.en.md) documentation for a full explanation.

---

## OANDA Adapter Configuration

The OANDA adapter connects to OANDA's REST v20 API. No local trading terminal is required.

```json5
{
  adapter: "oanda",
  short_name: "OANDA",
  enabled: true,
  
  // OANDA API connection
  account_id: "001-001-12345678-001",
  api_key_env: "OANDA_API_KEY",
  environment: "practice",   // or "live"
  
  // Pairs and timeframes
  pairs: ["EUR_USD", "GBP_USD", "USD_JPY"],
  timeframes: ["M5", "M15", "H1"],
  
  // Sync settings
  sync_interval_seconds: 60,
  max_candle_sync_count: 500,
  
  // Symbol map (OANDA uses underscore notation)
  symbol_map: {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
  }
}
```

### OANDA-Specific Fields

| Field | Description |
|-------|-------------|
| `account_id` | OANDA account identifier. Found in OANDA Hub under your account details. |
| `api_key_env` | Environment variable name for the OANDA API key (personal access token). |
| `api_key` | Plaintext API key (not recommended). |
| `environment` | `"practice"` for demo/paper trading, `"live"` for real money. |

### OANDA Time Zone Note

OANDA API returns candle timestamps in UTC. When using the OANDA adapter, set `broker_candle_utc_offset_hours: 0` in `system.json5`. The session filter then compares UTC candle times to UTC session boundaries with no offset.

---

## The short_name Field

`short_name` is the most important field in a broker module configuration. It determines:

1. **The broker's Bus Member ID**: `{short_name}-ALL___-BK-CONN`
2. **All Agent-IDs for this broker**: `{short_name}-{PAIR}-AA-ANLYS`, `{short_name}-ALL___-BA-ANLYS`, etc.
3. **Event routing templates**: rules using `{sender.broker}` resolve to this value
4. **Log entries**: all logs for this broker show the short_name as a prefix

### Choosing a short_name

Rules:
- All uppercase
- No spaces (use underscores if needed)
- 3–8 characters (longer is harder to read in logs and IDs)
- Must be unique across all configured brokers
- Stable — changing it invalidates all existing Agent-IDs and routing rules

Examples:
- `OXS_T` — OXS Trading broker
- `OANDA` — OANDA
- `IC_MKT` — IC Markets
- `FP_MKT` — FP Markets

### What Happens If You Change short_name

If you change `short_name` after the system has been running:
- The broker adapter registers with a new bus ID
- All existing routing rules that reference the old name stop working
- All Agent-IDs change — the database still has records under old IDs
- All agents (AA, BA, EC) need their `id` fields updated to use the new broker name

**Recommendation**: Choose `short_name` carefully before first use and never change it.

---

## Candle Polling and Synchronization

### How Candle Sync Works

1. The adapter runs a polling loop every `sync_interval_seconds`
2. For each pair and timeframe in `pairs` × `timeframes`, it queries the broker for recent candles
3. New candles (not yet in the database) are stored
4. For each stored M5 candle, the adapter publishes `m5_candle_saved` to the Event Bus
5. The AgentDispatcher (AD) listens for `m5_candle_saved` and fires `m5_agent_trigger` when appropriate

### sync_interval_seconds

Default: 60 seconds.

The polling interval should be set to approximately the M5 candle duration (300 seconds) or shorter. A 60-second interval ensures new candles are fetched shortly after they close. Do not set below 10 seconds — excessive polling can trigger broker API rate limits.

### Gap Detection and Fill

On startup and periodically during operation, the adapter checks for gaps in stored candle history:
- `candle_gap_fill_lookback_bars`: how many bars to look back for gaps (default: 200)
- If a gap is found, the adapter fetches the missing candles and publishes `candle_gap_detected` to the bus
- Gap fill runs once on startup and again whenever the system resumes after a connectivity interruption

### max_candle_sync_count

Maximum number of candles to fetch in a single API request. Default: 500.

For initial setup or after a long gap, the system may need to fetch hundreds of historical candles. The API request is split into batches of `max_candle_sync_count` if more are needed.

---

## broker_candle_utc_offset_hours and the Broker Module

The broker module configuration file does not itself contain the UTC offset setting. That setting lives in `config/system.json5` under `system.broker_candle_utc_offset_hours`.

However, the broker module determines which offset value is correct:
- MT5 brokers typically serve candles in broker local time (UTC+2 or UTC+3 depending on DST)
- OANDA serves candles in UTC

When switching from an MT5 broker to OANDA, or adding an OANDA adapter alongside an MT5 adapter:
- Update `broker_candle_utc_offset_hours` to match the active data source
- If running MT5 and OANDA simultaneously, note that this is a global setting — consult the architecture documentation for multi-broker timezone handling

For a complete explanation of this setting, see [System Config](ui.config.system_config.en.md#broker_candle_utc_offset_hours--critical-setting).

---

## Symbol Maps

Different brokers use different symbol names. OpenForexAI uses standard 6-character names internally (EURUSD, GBPUSD, etc.). When a broker uses different symbols, the `symbol_map` field provides the translation.

### When You Need a Symbol Map

- **MT5 with suffix**: Many MT5 brokers append suffixes to symbols (e.g. `EURUSDm`, `EURUSD.a`, `EURUSD_ecn`)
- **OANDA**: Uses underscore-separated notation (`EUR_USD`)
- **Index symbols**: Non-standard symbol names for indices or metals

### Symbol Map Format

```json5
symbol_map: {
  // Internal name → broker symbol
  "EURUSD": "EURUSDm",
  "GBPUSD": "GBPUSDm",
  "USDJPY": "USDJPYm",
  "XAUUSD": "GOLD",
}
```

The left side is the internal name used in OpenForexAI Agent-IDs and configurations. The right side is the exact symbol name as it appears in the broker's MT5 terminal or API.

### Pairs vs Symbol Map

The `pairs` array uses internal names. The `symbol_map` is only consulted when making API calls to the broker. If a pair in `pairs` has no entry in `symbol_map`, the internal name is used as-is for API calls.

---

## Multiple Broker Modules

OpenForexAI supports multiple broker adapters running simultaneously:

```json5
// In system.json5:
modules: {
  broker: [
    "config/broker/oxs_mt5.json5",
    "config/broker/oanda.json5"
  ]
}
```

Each adapter registers independently on the bus with its own `short_name`. Agents are configured per-broker: EURUSD on OXS_T uses `OXS_T-EURUSD-AA-ANLYS`, while EURUSD on OANDA uses `OANDA-EURUSD-AA-ANLYS`.

Routing rules using templates automatically route to the correct broker adapter based on the sender's broker segment.

### Use Cases for Multiple Brokers

- **Live + demo**: Run the same strategy live on one broker and on a demo account simultaneously
- **Comparison**: Monitor identical pairs on two brokers to detect spread or fill differences
- **Redundancy**: If one connection fails, the other broker's data keeps the system partially operational
- **Different pairs**: Each broker handles the pairs it supports best

---

## Typical Workflow

### Changing Connection Credentials

1. Select the module from the dropdown
2. Click **Refresh**
3. Update `password_env` or `api_key_env` (and set the environment variable to the new value)
4. Click **Save**
5. Restart the system
6. Verify connection in System Monitor

### Adding a New Trading Pair

1. Select the module
2. Add the pair name to the `pairs` array (e.g. `"AUDNZD"`)
3. If the broker uses non-standard symbols, add an entry to `symbol_map`
4. Click **Save**
5. Restart the system (or reload the adapter)
6. Verify candle data starts appearing in System Monitor within 1–2 sync cycles
7. Configure an AA agent and EC entity for this pair in Agent Config and Entity Config

### Adding a New Broker Adapter

1. Create a new config file (e.g. `config/broker/new_broker.json5`)
2. Set the appropriate `adapter`, `short_name`, `pairs`, and credentials
3. Add the path to `modules.broker` in `system.json5`
4. Restart the system
5. Verify the adapter registers in System Monitor
6. Add agents for the new broker's pairs

---

## Troubleshooting Broker Connection Issues

### Symptom: Adapter fails to connect on startup

For MT5:
- Is MT5 terminal running and logged in?
- Is the account password correct?
- Is the `server` name exactly as shown in MT5 (case-sensitive)?
- Is the MT5 Python package installed in the correct Python environment?
- Is auto-trading enabled in the MT5 terminal?

For OANDA:
- Is the API key valid and not expired?
- Is the `account_id` correct (check OANDA Hub)?
- Is `environment` set correctly (`practice` vs `live`)?

### Symptom: Candles not being fetched

- Check that `pairs` includes the desired pairs
- Check that `timeframes` includes the required timeframes
- For MT5: verify the symbol names exist in MT5 Market Watch (add them if missing)
- For symbol mismatches: check `symbol_map` entries
- Check `sync_interval_seconds` — if very large, the first sync may not have run yet

### Symptom: Session filter fires at wrong times

- `broker_candle_utc_offset_hours` in `system.json5` does not match broker server timezone
- For MT5: check broker server time in the MT5 terminal (shown in the status bar)
- For OANDA: should be `0` (OANDA uses UTC)

### Symptom: Orders not being executed

- Check Event Routing: is there a rule routing `order_request` to this broker's BK-CONN?
- Check the broker adapter is registered (visible in System Monitor)
- Check the `default_magic_number` does not conflict with another application
- For MT5: is auto-trading enabled in the terminal? Check the auto-trading button in the toolbar.

### Log Messages

| Log Message | Meaning |
|-------------|---------|
| `[BK] Connected to broker X` | Adapter connected successfully |
| `[BK] Connection failed: <error>` | Connection attempt failed |
| `[BK] Candle sync complete: N new candles` | Sync run completed |
| `[BK] Gap detected at <time> for <pair>/<tf>` | Gap found and being filled |
| `[BK] Order placed: ticket=NNNN` | Order successful |
| `[BK] Order failed: <error>` | Order placement error |
| `[BK] Reconnecting (attempt N)` | Connection lost, retrying |

---

*This document covers Broker Modules as implemented in OpenForexAI v0.7+. For the timezone offset setting, see [System Config](ui.config.system_config.en.md). For agent configuration tied to a broker, see [Agent Config](ui.config.agent_config.en.md).*

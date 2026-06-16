[Back to Test](ui.test.en.md)

# Tool Executor

`Tool Executor` calls a single tool directly and shows the result. No agent cycle, no LLM, no routing — just a direct tool call with controlled inputs. Ideal for testing tool parameters and debugging unexpected tool behavior.

Use cases:
- Check whether a tool is reachable and returns expected data
- Test parameters before embedding them in a snapshot profile
- Debug tool output that appears unexpectedly in agent runs

---

## Layout

Single column, scrollable (on large screens: form on the left, result on the right).

---

## Context Section (Top)

### Tool

Dropdown. **Required** — determines which tool is executed. Selecting a tool loads its schema and dynamically builds the argument form. A new selection resets the form and result.

### Agent

Dropdown. Optional. Selecting an agent automatically pre-fills Broker, LLM, and Pair from the agent configuration.

### Broker

Dropdown. Optional. Sets the broker context. Shows `short_name (module_name)` for identification. Required by tools that access broker data (e.g. `place_order`, `get_account_summary`).

### LLM

Dropdown. Optional. Sets the LLM context for tools that need one.

### Pair

Datalist input. Optional. Currency pair for context, e.g. `EURUSD`. Automatically uppercased. Suggests known pairs from agent configs.

---

## Argument Form

Built dynamically from the tool schema. Each tool has its own fields.

| Aspect | Behavior |
|---|---|
| **Field type** | Text, number, or dropdown — based on schema type (`string`, `number`, `integer`, `boolean`, enum) |
| **Required field** | Marked with `*`; must be filled |
| **Description** | Shown below the field if present in schema |
| **Empty fields** | Not submitted (no null values sent) |

### Input Schema (collapsible)

Shows the full JSON schema of the tool for reference.

### Quick Presets (order tools only)

Only appears for `place_order` and `auto_place_order`. Four buttons:

| Preset | Pre-fills |
|---|---|
| **Market** | Immediate market order |
| **Limit** | Limit order with limit price |
| **Stop** | Stop order with stop price |
| **Stop-Limit** | Stop-limit order with both prices |

### Validation

Errors are shown as an amber list above the Execute button. Common rules:

- All required fields must be filled
- For order tools: `units` (positive integer), `lots`, or `risk_pct` must be present
- For `LIMIT`: `limit_price` required
- For `STOP`: `stop_price` required
- For `STOP_LIMIT`: both prices required
- For `TRAILING_STOP`: `trailing_stop_distance` required

When all checks pass for an order tool, a green success message is shown.

### Execute

Executes the tool with the entered arguments. Disabled when: no tool selected, validation errors present, execution in progress.

---

## Result Panel

Shows the tool result after execution. Syntax-highlighted JSON:

| Color | Meaning |
|---|---|
| Light blue | JSON keys |
| Green | Strings |
| Amber | Boolean values |
| Purple | Numbers |
| Gray | `null` |

On error, the header appears in red with the error message.

---

## Tool Description

Shows the description of the selected tool from its schema. For tools that require approval, a warning badge is shown: "⚠ This tool requires approval".

---

## Typical Workflow

1. Select **Tool**
2. Optional: select **Agent** (pre-fills context)
3. Set **Broker**, **LLM**, **Pair** manually if needed
4. Fill in arguments (check required fields)
5. Review validation messages
6. Click **Execute**
7. Inspect result JSON

---

## Purpose and Use Cases in Depth

The Tool Executor is the direct-access interface for every registered tool in the system. It bypasses the LLM entirely — you specify the parameters, click Execute, and the tool runs immediately against the live system. The result appears as formatted JSON.

**When to use Tool Executor vs LLM Checker:**

| Scenario | Use |
|---|---|
| You want to see raw tool output for exact parameters | Tool Executor |
| You want to test whether the LLM calls a tool correctly | LLM Checker |
| You want to explore what parameters a tool accepts | Tool Executor (read the auto-generated form) |
| You want to verify data quality (are these candles correct?) | Tool Executor |
| You want to test system prompt behavior | LLM Checker |
| You want to place a test order directly | Tool Executor |

The Tool Executor is especially valuable for:

- **Snapshot profile debugging:** Before adding a tool call to a snapshot profile, verify with Tool Executor that the exact parameters return the expected data format
- **Indicator validation:** Confirm that `calculate_indicator` with a specific indicator/timeframe/period combination returns sensible values before relying on it in an agent
- **Order book inspection:** Browse the actual order history with full filtering control, including the `with_aa_analysis` flag to see the full analyst data
- **Connectivity checks:** Confirm that the broker is reachable and returning data before starting agent cycles

---

## Context Section — Detailed Reference

### Tool Dropdown

The primary selector. Lists every registered tool in the system. Selecting a tool:
1. Loads the tool's JSON schema from the backend
2. Dynamically generates the argument form with appropriate field types
3. Resets any previous result
4. Shows the tool's description in the Tool Description section

The tool list includes all tools from all modules: market data tools, indicator tools, account tools, order tools, and system tools.

### Agent Dropdown

Optional. Selecting an agent pre-fills:
- **Broker** — from the agent's broker field
- **LLM** — from the agent's llm field (for tools that need an LLM context)
- **Pair** — from the agent's pair field

This is a convenience shortcut. You do not need to select an agent — you can fill in Broker, LLM, and Pair manually.

### Broker Dropdown

Shows all broker modules as `short_name (module_name)`. Optional but required for broker-dependent tools like `get_order_book`, `place_order`, `get_account_status`, `get_open_positions`, `close_position`, `modify_order`.

When a broker is selected, it is passed as context to the tool execution. The tool registry resolves the correct broker adapter to use.

### LLM Dropdown

Optional. Only needed for tools that invoke an LLM as part of their operation. Most market data and trading tools do not need this. It is available for completeness.

### Pair Input

Datalist input. Accepts any currency pair string (e.g. `EURUSD`, `USDJPY`). Automatically uppercased. Provides autocomplete suggestions from known agent configurations. The pair is passed to tools that require it.

---

## Argument Form — Detailed Reference

The argument form is dynamically generated from the tool's JSON schema. Every field type, placeholder, and validation rule comes directly from the schema — there is no manual form configuration.

### Field Types

**Text inputs** (`string` type in schema):
- For free-form string parameters like `pair`, `price_source`, `comment`
- No restrictions — any text can be entered

**Number inputs** (`number` or `integer` type in schema):
- For numeric parameters like `count`, `period`, `lots`, `risk_pct`
- Only valid numbers are accepted
- Step=1 for integers, step=any for numbers

**SELECT DROPDOWNS** (`enum` type in schema):
- Replaces text inputs for fields with a fixed set of valid values
- Shows all valid options as a dropdown list
- Examples:
  - `timeframe`: M1, M5, M15, M30, H1, H4, D1, W1, MN
  - `indicator`: RSI, ATR, SMA, EMA, BB, VWAP, DXY, SLOPE_E, SLOPE_S, MACD, CCI, STOCH, ADX
  - `sort_by`: nearest, prominent
  - `status_filter`: open, closed, all, rejected, cancelled, pending, partially_filled
  - `decision`: BUY, SELL, NEUTRAL
  - `order_type`: MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP

**BOOLEAN DROPDOWNS** (`boolean` type in schema):
- Shows a SELECT with two options: `true` and `false`
- NOT a text input — prevents typos and eliminates ambiguity
- Example: `with_aa_analysis`, `include_metadata`

### Required Fields

Marked with `*` after the field label. Must be filled before Execute is available. Required fields are defined in the tool's JSON schema `required` array.

### Field Descriptions

If the tool schema includes a `description` for a property, it is displayed as helper text below the input field. This tells you what the parameter does without having to look up the documentation.

### Empty Fields

Fields that are left empty are NOT sent to the tool. The tool receives only the parameters that have been filled in. This means:
- Optional parameters are truly optional — leave them empty for default behavior
- Required parameters must be filled or the Execute button stays disabled

### Input Schema Section

A collapsible section that shows the complete raw JSON schema for the tool. Use this to:
- Understand the full list of accepted parameters
- See exact enum values for dropdowns
- Read detailed descriptions for each parameter
- Identify which parameters are required vs optional

Click the section header to expand/collapse.

### Quick Presets (Order Tools Only)

Only appears for `place_order` and `auto_place_order`. Four preset buttons quickly fill common parameter combinations:

| Preset | What it fills |
|---|---|
| **Market** | `order_type=MARKET` — immediate execution at current price |
| **Limit** | `order_type=LIMIT`, unlocks and marks `limit_price` as required |
| **Stop** | `order_type=STOP`, unlocks and marks `stop_price` as required |
| **Stop-Limit** | `order_type=STOP_LIMIT`, marks both `limit_price` and `stop_price` as required |

Using a preset fills only the order_type-related fields. You still need to fill in pair, units/lots/risk_pct, direction, and price levels.

### Validation Panel

An amber-colored panel that appears above the Execute button when there are validation issues. Lists all problems:

- Required fields missing (listed by name)
- For order tools: one of `units`, `lots`, or `risk_pct` must be present
- For `LIMIT` orders: `limit_price` required
- For `STOP` orders: `stop_price` required
- For `STOP_LIMIT` orders: both price fields required
- For `TRAILING_STOP` orders: `trailing_stop_distance` required

A green success message replaces the amber panel when all validations pass for order tools.

### Execute Button

Disabled while:
- No tool is selected
- Required fields are empty
- Validation errors exist
- A previous execution is still running

When clicked, sends the tool call to the backend with the filled arguments. The button shows a spinner during execution. Results typically appear within 1–5 seconds for market data tools; order execution tools may take longer.

---

## Result Panel — Detailed Reference

The result panel shows the tool's return value as syntax-highlighted JSON.

### Color Coding

| Color | JSON Element |
|---|---|
| Light blue | Object keys / property names |
| Green | String values |
| Amber/yellow | Boolean values (`true`, `false`) |
| Purple | Number values |
| Gray | `null` values |

### Success Response

The panel header shows a green "Success" badge with execution time (e.g. "147 ms"). The JSON body displays the full return value of the tool.

### Error Response

The panel header shows a red "Error" badge with the error message. The body shows the error details. Common errors:
- "Broker not connected" — broker adapter is not running or not reachable
- "Pair not found" — the specified pair is not available on the broker
- "Insufficient margin" — order tool called with parameters that exceed available margin
- "Tool not found" — tool name is invalid or not registered

### Copy Button

Top-right corner of the result panel. Copies the full JSON output to clipboard. Useful for:
- Pasting the result into the LLM Checker to test how an agent would interpret this data
- Reporting a data issue with the actual output included
- Saving expected output for comparison testing

---

## Complete Tool Reference with Parameters

### get_candles

Retrieves OHLCV candlestick data for a currency pair and timeframe.

| Parameter | Type | Required | Description |
|---|---|---|---|
| pair | string | Yes | Currency pair, e.g. EURUSD |
| timeframe | enum dropdown | Yes | M1, M5, M15, M30, H1, H4, D1, W1, MN |
| count | integer | Yes | Number of candles to retrieve (1–500) |

**Example result:** Array of candle objects: `[{"time": "2026-06-03T10:00:00", "open": 1.0921, "high": 1.0934, "low": 1.0918, "close": 1.0929, "volume": 1842}, ...]`

**Testing tip:** Start with a small count (5–10) to verify the data is returning correctly before using larger counts in snapshot profiles.

---

### calculate_indicator

Calculates a technical indicator for a currency pair and timeframe.

| Parameter | Type | Required | Description |
|---|---|---|---|
| indicator | enum dropdown | Yes | RSI, ATR, SMA, EMA, BB, VWAP, DXY, SLOPE_E, SLOPE_S, MACD, CCI, STOCH, ADX |
| period | integer | Yes | Indicator period (e.g. 14 for RSI, 20 for SMA) |
| timeframe | enum dropdown | Yes | M1, M5, M15, M30, H1, H4, D1, W1, MN |
| history | integer | No | Number of historical values to return (default: 1) |
| smooth_period | integer | No | Smoothing period for indicators that support it (e.g. SLOPE_E, SLOPE_S) |
| pair | string | No | Currency pair (defaults to context pair) |

**Indicator notes:**
- `SLOPE_E` — exponential slope of price, uses smooth_period for EMA calculation
- `SLOPE_S` — simple slope of price, uses smooth_period for SMA calculation
- `BB` — Bollinger Bands, returns upper/middle/lower values
- `VWAP` — Volume Weighted Average Price
- `DXY` — US Dollar Index (if available from the data provider)

**Example result for RSI:** `{"value": 58.3, "previous": 56.1, "timestamp": "2026-06-03T10:00:00"}`

**Example result for BB:** `{"upper": 1.0945, "middle": 1.0921, "lower": 1.0897, "timestamp": "2026-06-03T10:00:00"}`

---

### get_swing_levels

Identifies swing highs and lows from price history.

| Parameter | Type | Required | Description |
|---|---|---|---|
| timeframe | enum dropdown | Yes | M15, H1, H4, D1 (lower TFs less useful for swings) |
| max_levels | integer | No | Maximum levels to return (default: 10) |
| lookback | integer | No | Number of candles to analyze for swings |
| atr_period | integer | No | ATR period for gap filtering (default: 14) |
| min_gap_atr | number | No | Minimum gap between levels as ATR multiple (default: 0.5) |
| sort_by | enum dropdown | No | nearest (by price proximity), prominent (by significance) |
| price_source | string | No | Which price to use: close, high_low (default) |

**Example result:** `[{"level": 1.0880, "type": "support", "strength": 3, "distance_atr": 1.2, "last_touch": "2026-05-28"}, ...]`

**Testing tips:**
- Use `sort_by=nearest` to verify levels close to the current price
- Use `sort_by=prominent` to see the most historically significant levels
- Increase `lookback` to find older, higher-timeframe swing levels
- Decrease `min_gap_atr` to see more granular levels, increase to see only major ones

---

### get_order_book

Retrieves the order book (trade history) for the selected broker.

| Parameter | Type | Required | Description |
|---|---|---|---|
| broker | string | No | Broker module name (defaults to context broker) |
| pair | string | No | Filter by pair (leave empty for all pairs) |
| status_filter | enum dropdown | No | open, closed, all, rejected, cancelled, pending, partially_filled |
| limit | integer | No | Maximum number of orders to return |
| with_aa_analysis | boolean dropdown | No | true = include full analyst data (market_context_snapshot); false = clean output |

**The `with_aa_analysis` parameter** is important for understanding what was in the system at the time of an order:
- `false` (default): returns clean order data without the large snapshot JSON embedded in each order
- `true`: returns the full analyst data including the complete `market_context_snapshot` that was active when the order was placed — useful for reviewing what the agent "saw" when it made a trading decision

**`status_filter` values explained:**
- `open`: positions currently open (in profit/loss)
- `closed`: positions that have been closed
- `pending`: orders placed but not yet filled (e.g. limit orders waiting)
- `partially_filled`: orders that have been partially executed
- `rejected`: orders that were refused by the broker
- `cancelled`: orders that were cancelled before execution
- `all`: every order regardless of status

**Example result:** `[{"order_id": "12345", "pair": "EURUSD", "direction": "BUY", "units": 1000, "open_price": 1.0921, "close_price": null, "status": "open", "open_time": "2026-06-03T09:15:00"}, ...]`

---

### get_account_status

Returns current account balance, equity, margin, and free margin.

No required parameters (uses context broker).

| Parameter | Type | Required | Description |
|---|---|---|---|
| broker | string | No | Broker module name |

**Example result:** `{"balance": 10500.00, "equity": 10487.50, "margin": 25.00, "margin_free": 10462.50, "margin_level_pct": 41950.0, "currency": "USD"}`

---

### get_open_positions

Returns all currently open positions.

| Parameter | Type | Required | Description |
|---|---|---|---|
| broker | string | No | Broker module name |
| pair | string | No | Filter by pair |

**Example result:** `[{"position_id": "P123", "pair": "EURUSD", "direction": "BUY", "units": 1000, "open_price": 1.0921, "current_price": 1.0929, "profit_loss": 8.00, "open_time": "2026-06-03T09:15:00"}]`

---

### get_session_status

Returns the current trading session information including which sessions are active.

No required parameters.

**Example result:** `{"current_time_utc": "2026-06-03T10:30:00", "active_sessions": ["london"], "next_session": "new_york", "next_session_open_utc": "2026-06-03T12:00:00"}`

---

### get_last_decision

Returns the most recent trading decision made by an agent.

| Parameter | Type | Required | Description |
|---|---|---|---|
| agent_id | string | No | Filter by specific agent ID |
| pair | string | No | Filter by pair |

**Example result:** `{"agent_id": "OXS_T-EURUSD-AA-ANLYS", "decision": "BUY", "confidence": 0.82, "timestamp": "2026-06-03T10:00:00", "summary": "Strong bullish momentum..."}`

---

### place_order

Places a new trade order directly.

| Parameter | Type | Required | Description |
|---|---|---|---|
| pair | string | Yes | Currency pair |
| direction | enum dropdown | Yes | BUY, SELL |
| order_type | enum dropdown | Yes | MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP |
| units | integer | No* | Units (one of: units, lots, or risk_pct required) |
| lots | number | No* | Position size in lots |
| risk_pct | number | No* | Risk as percentage of account balance |
| limit_price | number | No | Required for LIMIT and STOP_LIMIT orders |
| stop_price | number | No | Required for STOP and STOP_LIMIT orders |
| stop_loss | number | No | Stop loss price |
| take_profit | number | No | Take profit price |
| trailing_stop_distance | number | No | Required for TRAILING_STOP orders |
| comment | string | No | Order comment/label |
| broker | string | No | Broker module name |

**Warning:** This tool places real orders on the selected broker. Use only on demo accounts during testing unless executing an intentional live test.

---

### auto_place_order

Places an order with automatic parameter resolution from the most recent agent decision. Fewer parameters needed than `place_order`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| pair | string | Yes | Currency pair |
| broker | string | No | Broker module name |
| override_direction | enum dropdown | No | Override the direction from the last decision |
| override_risk_pct | number | No | Override the risk percentage |

---

### close_position

Closes an open position.

| Parameter | Type | Required | Description |
|---|---|---|---|
| position_id | string | Yes | The position ID to close |
| broker | string | No | Broker module name |
| units | integer | No | Partial close — units to close (omit for full close) |

---

### modify_order

Modifies an existing pending or open order.

| Parameter | Type | Required | Description |
|---|---|---|---|
| order_id | string | Yes | The order ID to modify |
| stop_loss | number | No | New stop loss price |
| take_profit | number | No | New take profit price |
| limit_price | number | No | New limit price (for limit orders) |
| broker | string | No | Broker module name |

---

### raise_alarm

Triggers an alarm event on the event bus.

| Parameter | Type | Required | Description |
|---|---|---|---|
| alarm_type | string | Yes | Type/category of the alarm |
| message | string | Yes | Alarm message text |
| severity | enum dropdown | No | info, warning, critical |
| pair | string | No | Associated pair if relevant |

---

### trigger_sync

Triggers a synchronization event to force data refresh.

| Parameter | Type | Required | Description |
|---|---|---|---|
| sync_type | string | No | What to synchronize (e.g. "positions", "orders", "account") |
| broker | string | No | Broker to sync |

---

## Practical Examples

### Example 1: Verify H1 RSI Before Adding to Snapshot Profile

You want to add H1 RSI (period 14) for EURUSD to your snapshot profile. Before doing so, verify it returns correct values.

1. Select `calculate_indicator`
2. Set Pair = EURUSD (or select a EURUSD agent)
3. Fill form:
   - indicator = RSI (dropdown)
   - period = 14
   - timeframe = H1 (dropdown)
   - history = 3 (see 3 consecutive values to assess reasonableness)
4. Click Execute
5. Verify: are the returned RSI values in a reasonable range (0–100)? Do they roughly match what you see on your chart?

If the values look correct, you can confidently add this call to the snapshot profile.

### Example 2: Check Why Swing Levels Look Wrong on the Chart

An agent references H4 EURUSD swing levels at 1.0850 but you don't see that level on your chart.

1. Select `get_swing_levels`
2. Set Pair = EURUSD
3. Fill form:
   - timeframe = H4 (dropdown)
   - max_levels = 10
   - sort_by = prominent (dropdown)
   - lookback = 200 (look further back in history)
4. Click Execute
5. Review the returned levels — is 1.0850 present? What does its `strength` and `last_touch` show?
6. If the level appears but seems wrong, try adjusting `min_gap_atr` or `lookback`

### Example 3: Inspect Order History with Full Analyst Data

You want to review what market context the analyst provided for a specific trade that went wrong.

1. Select `get_order_book`
2. Select the relevant broker
3. Fill form:
   - pair = EURUSD
   - status_filter = closed (dropdown)
   - limit = 10
   - with_aa_analysis = true (boolean dropdown)
4. Click Execute
5. In the result JSON, find the order of interest
6. Expand the `market_context_snapshot` field — this shows the full analyst snapshot that was present when the order was placed

Note: `with_aa_analysis=true` returns significantly larger JSON objects. Use `false` for a clean overview and `true` only when you need the analytical detail.

### Example 4: Check Account Status Before Manual Test Trade

Before placing a test order with Tool Executor, verify account state.

1. Select `get_account_status`
2. Select broker
3. Click Execute (no other parameters needed)
4. Verify: balance, margin_free — is there enough margin for the planned test order?

### Example 5: Test a Direct MARKET Order on Demo Broker

You want to verify the order placement pipeline works end-to-end on a demo broker.

1. Confirm the selected broker is your demo account
2. Select `place_order`
3. Click the "Market" preset to auto-fill order_type=MARKET
4. Fill remaining fields:
   - pair = EURUSD
   - direction = BUY (dropdown)
   - risk_pct = 0.5 (0.5% of balance)
   - stop_loss = 1.0880 (a reasonable level below current price)
   - take_profit = 1.0980
   - comment = "ToolExecutor test"
5. Verify: validation panel shows green
6. Click Execute
7. Inspect result: `order_id`, `status`, `fill_price`
8. Immediately run `get_open_positions` to confirm the position is visible

### Example 6: Close All Open Positions Manually

You want to close a specific open position found in the order book.

1. First run `get_open_positions` to get the position_id
2. Note the position_id (e.g. "P12345")
3. Select `close_position`
4. Fill form:
   - position_id = P12345
   - (leave units empty for full close)
5. Click Execute
6. Verify result shows status = "closed"
7. Run `get_open_positions` again to confirm it is no longer listed

---

## Tips and Best Practices

- **Always verify market data tools before relying on them in snapshot profiles** — data format can change with broker adapter updates; Tool Executor gives instant confirmation
- **Use `status_filter` on `get_order_book`** — "all" returns many records; filter to "open" or "closed" for targeted inspection
- **Compare indicator values with your charting platform** — if values differ significantly, check the `timeframe` and `period` settings match exactly
- **For swing level testing, try multiple `sort_by` and `lookback` combinations** — the "correct" parameters depend on your trading strategy's timeframe and style
- **The boolean dropdown for `with_aa_analysis` is not a text field** — you must select from the dropdown, you cannot type "true" or "false"
- **Copy results frequently** — the result panel shows only the most recent execution; if you run multiple tests in sequence, copy each result before moving on
- **Check latency** — the execution time shown in the result header tells you how long the tool takes to run; slow tools (>500ms) may need optimization in snapshot profiles that call them multiple times
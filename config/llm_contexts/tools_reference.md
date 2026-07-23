# Tools Reference

All tools available in EC scripts (`await tools.call("tool_name", ...)`) and to LLM agents.

`broker` and `pair` parameters are always injected from context — omit unless you need to override.

---

## ⚠️ Data types — read this before processing any return value

Every value below reflects the **actual JSON that reaches your code**, verified against the source.

- **Prices, money, P&L, spreads, ATR-in-price arrive as STRINGS, not numbers.**
  Internally they are Python `Decimal`, serialized via `model_dump(mode="json")` → JSON strings
  like `"1.08521"`. This applies to every broker-backed tool: `get_candles` (OHLC + spread),
  `get_account_status` (balance/equity/margin/margin_free), `get_open_positions`,
  `get_order_book`, `place_order`/`auto_place_order` (`fill_price`), `close_position` (`pnl`).
  **Always cast before arithmetic:** `float(c["close"])` or `Decimal(c["close"])`.
- **Integers stay integers:** `units`, `leverage`, `tick_volume`.
- **Plain floats (numbers, not strings):** `signal_confidence`, `margin_level`,
  indicator `value`s from `calculate_indicator`, everything from `get_swing_levels`,
  and the SL/TP echoed back by `modify_order`.
- **Enums arrive as their string value:** direction `"BUY"`/`"SELL"`, order status
  `"PENDING"|"OPEN"|"PARTIALLY_FILLED"|"CLOSED"|"REJECTED"|"CANCELLED"`,
  order type `"MARKET"|"LIMIT"|"STOP"|"STOP_LIMIT"|"TRAILING_STOP"`.
- **Datetimes are ISO 8601 strings** (e.g. `"2024-01-15T10:00:00+00:00"`). They reflect how the
  value was stored — a UTC offset like `+00:00` may be present; do not assume a trailing `"Z"`.
- **Optional fields are `null`** when unset. Fields marked "always null in current impl" below are
  present in the dict but never populated by the current broker adapters — do not rely on them.

---

## Market Data

### get_candles
Retrieve OHLCV candle history for the current pair (reads DB only — no broker backfill).

**Parameters:** `timeframe`* (M5|M15|M30|H1|H4|D1), `count` (1–500, **default 50**)

**Returns:** list of candle dicts, oldest first / newest last. **OHLC and `spread` are STRINGS:**
```python
[{"timestamp":   "2024-01-15T10:00:00+00:00",  # ISO 8601 (offset as stored, not always "Z")
  "open":        "1.08521",   # STRING
  "high":        "1.08612",   # STRING
  "low":         "1.08490",   # STRING
  "close":       "1.08580",   # STRING
  "tick_volume": 342,          # int
  "spread":      "0.00012",   # STRING
  "timeframe":   "M5"}, ...]
```
Returns `[]` if the DB holds no candles for the pair/timeframe.

---

### calculate_indicator
Compute a technical indicator.

**Parameters:** `indicator`* (RSI|ATR|SMA|EMA|BB|VWAP|DXY|SLOPE_E|SLOPE_S), `period`* (int, min 0 — 0 only valid for VWAP daily reset; all others need ≥1), `timeframe`* (M5|M15|M30|H1|H4|D1), `history` (1–500, default 1), `smooth_period` (EMA smoothing on scalar output only, default 1 = off; ignored for BB/DXY dict values), `warmup_candles` (0–2000, optional)

**`warmup_candles`:** RSI/ATR (Wilder's smoothing) and EMA (incl. smoothed SLOPE_E/SLOPE_S) are
recursive — the returned value depends on how many candles preceded it, not just on `period`.
Leave `warmup_candles` empty to auto-size it from `period` (targets ~0.1% residual error: roughly
`period × 10`, minimum 50). Set it explicitly to override — e.g. to reproduce a specific chart's
lookback, or to intentionally accept a "cold" value with fewer DB reads. A small explicit `history`
alone does **not** shrink the candle window used to compute it — `warmup_candles` is the only way
to control that. Not applicable to SMA/BB/VWAP (fixed rolling window, no recursion, unaffected).

**Outer return structure** (same for all indicators). `values` is **always a list**, even when `history=1`:
```python
{"indicator": "RSI", "period": 14, "timeframe": "H1", "history": 3,
 "values": [
   {"timestamp": "2024-01-15T08:00:00Z", "value": <value>},  # oldest
   {"timestamp": "2024-01-15T09:00:00Z", "value": <value>},
   {"timestamp": "2024-01-15T10:00:00Z", "value": <value>},  # newest
 ]}
# On error / not enough data: {"values": None, "reason": "Not enough candle data"}
```
Indicator `value`s are **plain floats or dicts of floats** (NOT strings). `timestamp` is an ISO
string for all indicators **except DXY, whose timestamps are always `null`**.

**`value` per indicator:**

| Indicator | value type | value description |
|---|---|---|
| RSI | float (0–100) | >70 overbought, <30 oversold |
| ATR | float | Average true range in price units; use for SL sizing |
| SMA | float | Simple moving average of closes |
| EMA | float | Exponential moving average of closes |
| BB | dict | `{"upper": f, "middle": f, "lower": f}` — SMA ± 2σ, each rounded to 6 dp |
| VWAP | float | Volume-weighted avg price. `period=0` = daily reset from 00:00 **broker-local** wall-clock time; `period>0` = rolling over the last N candles |
| DXY | dict | `{"dxy_close": f, "dxy_direction": "rising"\|"falling", "correlation": f}` — synthetic 5-component USD index (EURUSD/USDJPY/GBPUSD/USDCAD/USDCHF); `correlation` is Pearson corr of pair close vs DXY over the window (0.0 if <2 points) |
| SLOPE_E | float (pips) | EMA slope candle-over-candle in pips. Positive = rising, negative = falling, near zero = flat |
| SLOPE_S | float (pips) | SMA slope candle-over-candle in pips. Same concept as SLOPE_E |

Pip auto-detection (SLOPE_E/SLOPE_S): last close > 20 (JPY pairs) → 0.01 pip divisor, otherwise 0.0001.

---

### get_swing_levels
Detect swing high/low support and resistance levels (scipy peak detection + ATR clustering).

**Parameters:** `timeframe`* (M5|M15|M30|H1|H4|D1), `lookback` (10–500, default 100), `prominence` (min swing height, default 0.0), `atr_period` (1–200, default 14), `min_gap_atr` (cluster-merge threshold as ATR multiple, default 0.3; 0 disables clustering), `max_levels` (1–20, default 5), `current_price` (float; default = last M5 close, else last candle of timeframe), `price_source` (HL|OC, default HL), `sort_by` (nearest|prominent, default nearest)

**Returns** (all numeric fields are plain floats, not strings):
```python
{"timeframe": "H1",
 "lookback": 100,
 "candles_available": 100,
 "current_price": 1.08580,
 "current_price_source": "M5",     # "argument" | "M5" | "<timeframe>"
 "atr": 0.00085,                    # or null
 "min_gap": 0.000255,               # ATR*min_gap_atr, or 0.0
 "highs":      [{"price": 1.09100, "timestamp": "...", "distance": 0.00520, "prominence": 0.0012, "type": "high"}],
 "lows":       [{"price": 1.08200, "timestamp": "...", "distance": 0.00380, "prominence": 0.0009, "type": "low"}],
 "confluence": [{"price": 1.08750, "timestamp": "...", "distance": 0.00170, "type": "confluence"}],  # NO "prominence" key
 "nearest_resistance": {"price": 1.08750, "distance": 0.00170, "type": "confluence"},  # a high/low/confluence dict, or null
 "nearest_support":    {"price": 1.08200, "distance": 0.00380, "type": "low"}}          # or null
```
`highs`/`lows` entries carry `prominence`; `confluence` entries do NOT.
`nearest_resistance`/`nearest_support` mirror whichever level dict was nearest (so their key set varies).

**Insufficient data** (fewer than 3 candles) — note there is **no `confluence` key** in this variant:
```python
{"timeframe": "H1", "lookback": 100, "candles_available": 0,
 "current_price": null, "current_price_source": null, "atr": null, "min_gap": null,
 "highs": [], "lows": [], "nearest_resistance": null, "nearest_support": null}
```

---

### get_session_status
Forex session state, liquidity, and trade recommendation. No required parameters.

**Parameters:** `timestamp` (optional ISO 8601 UTC; default = now), `pair` (optional; default = context pair)

**Returns:**
```python
{"timestamp": "2024-01-15T10:30:00Z",
 "sessions": {
   "sydney":   {"name": "sydney",   "status": "closed", "local_time": "2024-01-15T21:30:00+11:00",
                "minutes_since_open": null, "minutes_until_close": null, "is_holiday": false},
   "tokyo":    {"name": "tokyo",    "status": "...", ...},
   "london":   {"name": "london",   "status": "active", "local_time": "...",
                "minutes_since_open": 150, "minutes_until_close": 270, "is_holiday": false},
   "new_york": {"name": "new_york", "status": "opening_hour", ...}},
 "active_sessions":    ["london", "new_york"],
 "session_count":      2,
 "overlap":            "london_newyork",  # none|sydney_tokyo|tokyo_london|london_newyork|other
 "liquidity_estimate": "very_high",       # very_low|low|medium|high|very_high
 "recommended_action": "trade",           # trade|caution|avoid
 # pair_context only present when a pair (arg or context) resolves to known currencies:
 "pair_context": {
   "pair":              "EURUSD",
   "primary_sessions":  ["london", "new_york"],
   "active_primary":    ["london", "new_york"],
   "current_relevance": "optimal",        # optimal|partial|off_hours
   "pair_liquidity":    "very_high"}}      # very_low|low|medium|high|very_high
```
Per-session `status` values: `closed_weekend | closed_holiday | closed | opening_hour | active | closing_hour`.
`minutes_since_open` / `minutes_until_close` are `null` unless the session is in-session.

---

### get_news
Retrieve economic calendar events for the current pair from the MQL5 calendar.

**Parameters:** `hoursBack` (default 1), `hoursFor` (default 4), `pair` (default: context pair)

**Returns:** a **Markdown string** — either the rendered events document, or a
`"No economic calendar events found for … "` message. (Not a dict.)

---

### chartshot
Render a candlestick chart as PNG. Returns a file path and image marker for LLM context injection.

**Parameters:** `timeframe`* (M5|M15|M30|H1|H4|D1), `candles` (10–500, default 200), `pair` (override), `config` (named config from system.json5, default "default"), `filename` (auto-generated if omitted)

**Returns:**
```python
{"pair": "EURUSD", "timeframe": "M15",
 "candles": 200,                        # actual rendered count (len of the DataFrame)
 "config": "default",
 "candle_from": "2024-01-15T08:00:00",  # naive ISO (no offset/Z), from the chart's first candle
 "candle_to":   "2024-01-15T10:00:00",  # naive ISO, last candle
 "file_path":   "C:/OpenForexAI-B/data/chartshots/EURUSD_M15_200_20240115_103000.png",  # absolute
 "image_marker": "imagetmp[data/chartshots/EURUSD_M15_200_20240115_103000.png]",
 # marker is "image[<rel>]" when the config's output_mode is "keep",
 # "imagetmp[<rel>]" when output_mode is "temp" (the default). Path is repo-relative, POSIX.
 "description": ""}                      # from the named config, or "" if none
```

---

## Account

### get_account_status
Retrieve live account balance, equity, margin and trading permission.

**Parameters:** none required

**Returns** (monetary values are **STRINGS**; `leverage` int; `margin_level` float|null; `trade_allowed` bool):
```python
{"broker_name": "OANDA_DEMO",
 "balance":      "10000.00",   # STRING
 "equity":       "10380.00",   # STRING
 "margin":       "215.00",     # STRING
 "margin_free":  "10165.00",   # STRING
 "margin_level": 4828.0,        # float, or null when no open trades
 "leverage":     50,            # int
 "currency":     "USD",
 "trade_allowed": true,
 "recorded_at":  "2024-01-15T10:30:00+00:00"}
```
Any field may be `null` if the broker adapter omitted it.

---

### get_open_positions
Retrieve all open positions, grouped by pair. Each position is a serialized `Position` model.

**Parameters:** `pair` (optional filter)

**Returns** (prices + `unrealized_pnl` are **STRINGS**; `units` int; `direction` "BUY"/"SELL"):
```python
{"success": true,
 "broker_name": "oanda",
 "pair_filter": "EURUSD",        # the filter arg, or null
 "used_context_pair": "EURUSD",
 "total_count": 1,
 "pairs": {
   "EURUSD": {"count": 1, "orders": [
     {"broker_position_id": "12345",
      "broker_name": "oanda",
      "pair": "EURUSD",
      "direction": "BUY",          # "BUY" | "SELL"
      "units": 10000,              # int
      "open_price":     "1.08200", # STRING (NOT "entry_price")
      "current_price":  "1.08580", # STRING
      "stop_loss":      "1.07900", # STRING | null
      "take_profit":    "1.09000", # STRING | null
      "unrealized_pnl": "38.00",   # STRING
      "opened_at":      "2024-01-15T08:30:00+00:00",
      "sync_key":       "abc123"}]}}}  # str | null
```
A pair with no positions yields `{"count": 0, "orders": []}` (only for the filtered pair).

---

### get_order_book
Retrieve internal order book entries (serialized `OrderBookEntry` models).

**Parameters:** `status_filter` (open|pending|partially_filled|closed|rejected|cancelled|all, default **open**), `limit` (1–100, default 20), `with_aa_analysis` (bool, default true)

**Field visibility (important):**
- `status_filter="open"` (default) uses a **slim** repo read that ALWAYS omits
  `market_context_snapshot`, `entry_reasoning`, and `close_reasoning` — regardless of `with_aa_analysis`.
- Any other `status_filter` returns the full entry; then `with_aa_analysis=false` additionally
  drops `market_context_snapshot`.

**Returns:** a **list** of entry dicts (NOT wrapped in an outer object). Prices are **STRINGS**:
```python
[{"id": "550e8400-e29b-41d4-a716-446655440000",  # UUID string
  "broker_name": "oanda", "broker_order_id": "12345", "sync_key": "abc",  # broker_order_id/sync_key: str|null
  "pair": "EURUSD",
  "direction": "BUY",           # "BUY" | "SELL"
  "order_type": "MARKET",       # MARKET|LIMIT|STOP|STOP_LIMIT|TRAILING_STOP
  "units": 10000,               # int
  "requested_price": "1.08200", # STRING
  "fill_price":      "1.08215", # STRING | null
  "stop_loss":       "1.07900", # STRING | null
  "take_profit":     "1.09000", # STRING | null
  "trailing_stop_distance": null,  # STRING | null
  "limit_price": null, "stop_price": null,  # STRING | null
  "status": "OPEN",             # PENDING|OPEN|PARTIALLY_FILLED|CLOSED|REJECTED|CANCELLED
  "agent_id": "TA001",
  "prompt_version": 3,          # int | null
  "entry_reasoning": "...",     # str  (omitted for status_filter="open")
  "signal_confidence": 0.75,    # float
  "market_context_snapshot": {...},  # dict (omitted for "open" OR when with_aa_analysis=false)
  "requested_at": "2024-01-15T08:30:00+00:00",
  "opened_at":    "2024-01-15T08:30:01+00:00",  # ISO | null
  "close_requested_at": null, "closed_at": null, "last_broker_sync": "...",  # ISO | null
  "close_reason": null,         # SL_HIT|TP_HIT|TRAILING_STOP|AGENT_CLOSED|BROKER_CLOSED|SYNC_DETECTED|REJECTED | null
  "close_price": null,          # STRING | null
  "close_reasoning": null,      # str | null  (omitted for status_filter="open")
  "pnl_pips": null,             # STRING | null
  "pnl_account_currency": null, # STRING | null
  "sync_confirmed": true,       # bool
  "confirmed_by_broker": true}, ...]  # bool
```

---

## Trading

### place_order
Submit a trade order.

**Parameters:** `direction`* (buy|sell), `order_type`* (MARKET|LIMIT|STOP|STOP_LIMIT|TRAILING_STOP), `units` (int) OR `lots` (number, ×100000) OR `risk_pct` (0.1–5.0), `stop_loss`, `take_profit`, `entry_price`, `limit_price`, `stop_price`, `trailing_stop_distance` (pips), `reasoning`, `confidence` (0.0–1.0)

**Returns** (`_handle_order_request` uses `model_dump(mode="json")`, so this is fully populated):
```python
{"success": true,               # false only when status == "REJECTED"
 "order_id": "broker-id-123",   # broker_order_id (falls back to it); may be "" if broker omitted
 "status": "OPEN",              # OPEN | PENDING | CLOSED | REJECTED  (TradeStatus enum)
 "fill_price": "1.08215",       # STRING | null (null until filled)
 "broker_name": "oanda",
 "broker_message": null,        # ALWAYS null — TradeResult has no such field
 "sync_key": "abc123",          # from the order, str | null
 "order_book_entry_id": "550e8400-..."}  # internal order book UUID string
```

---

### auto_place_order
Place an order using centrally defined defaults. Only `direction` required; all other fields optional overrides. ATR-based SL/TP auto-computed if not provided.

**Parameters:** `direction`* (buy|sell), `order_type`, `units`, `lots`, `risk_pct`, `stop_loss`, `take_profit`, `entry_price`, `atr_period` (1–500, default 14), `atr_timeframe` (default M5), `sl_atr_factor` (0.1–10, default 1.5), `tp_atr_factor` (0.1–20, default 3.0), `reasoning`, `confidence`

**Returns:** same shape as `place_order`.

---

### modify_order
Adjust SL and/or TP of an open position. At least one of `stop_loss`/`take_profit` required.

**Parameters:** `position_id`* (string), `stop_loss` (float), `take_profit` (float), `reasoning`

**Returns:**
```python
{"success": true,               # true unless status == "REJECTED"
 "position_id": "12345",
 "status": "UNKNOWN",           # NOTE: current OANDA/MT5 adapters return no status here → almost always "UNKNOWN"
 "broker_name": "oanda",
 "stop_loss": 1.08100,          # float | null — the value you PASSED IN, echoed back (not broker-confirmed)
 "take_profit": 1.09200,        # float | null — echoed input
 "order_book_entry_id": "550e8400-..."}  # str | null (null if no matching local entry)
```
Because the broker adapter stringifies its `TradeResult` instead of returning a dict, `status` is not
propagated — treat `success` (no error raised) as the signal, and re-read via `get_open_positions`/`get_order_book` to confirm.

---

### close_position
Close an open position, fully or partially.

**Parameters:** `position_id` (string; "0" = emergency close ALL) OR `pair` (close all for that pair), `units`, `lots` (partial close), `reasoning`

**Returns (single close)** — same adapter limitation as `modify_order`:
```python
{"success": true,               # true unless status == "REJECTED"
 "position_id": "12345",
 "status": "UNKNOWN",           # current adapters don't propagate status → "UNKNOWN"
 "order_id": null,              # ALWAYS null in current impl (TradeResult has no order_id key)
 "close_price": null,           # ALWAYS null in current impl (no close_price key)
 "pnl": null,                   # ALWAYS null in current impl (str expected, key absent)
 "closed_units": 10000,         # the units requested to close (int) | null
 "remaining_units": null,       # ALWAYS null in current impl
 "broker_name": "oanda",
 "order_book_entry_id": "550e8400-..."}  # str | null
```
Reliable fields today: `success`, `position_id`, `closed_units`, `broker_name`, `order_book_entry_id`.
Confirm the actual outcome (fill/P&L) via `get_order_book`/`get_open_positions` afterwards.

**Returns (batch — `position_id="0"` or pair-close):**
```python
{"success": true, "status": "BATCH_ALL",  # or "BATCH" for pair-close
 "closed_count": 2, "results": [{...single-close dict...}, {...}],
 "pair": "EURUSD"}                          # present only for the "BATCH" (pair-close) variant
```

---

## System

### raise_alarm
Emit a structured alarm to the monitoring system.

**Parameters:** `severity`* (info|warning|error|critical), `title`* (max 100 chars), `message`*, `context` (optional key-value dict)

**Returns:** `{"alarm_raised": true, "severity": "warning", "title": "..."}`
(severity falls back to `"warning"` if an invalid value is passed; title is truncated to 100 chars.)

---

### trigger_sync
Manually trigger an order book sync with the broker to detect externally closed positions.

**Parameters:** none required (`pair`/`broker` from context)

**Returns:**
```python
{"sync_triggered": true, "pair": "EURUSD", "broker": "oanda",
 "discrepancies_found": 1,
 "discrepancies": [
   {"entry_id": "550e8400-...",      # order book entry UUID string
    "pair": "EURUSD",
    "direction": "BUY",              # "BUY" | "SELL"
    "close_reason": "SYNC_DETECTED"} # "SYNC_DETECTED" | "REJECTED"
 ]}
```
`discrepancies` is `[]` when the order book already matches the broker.

---

### get_last_decision
Retrieve the most recent analysis decision record for an agent.

**Parameters:** `agentid` (default: current agent)

**Returns:**
```python
{"agent_id": "...", "found": true,
 "decision": {
   "decided_at": "2024-01-15T10:00:00",
   "analysis_text": "...",    # human-readable summary (or null)
   "analysis": {...},         # structured analysis block (agent-schema-dependent, may be null)
   "decision": {...},         # structured decision block (agent-schema-dependent, may be null)
   "confidence": 0.8,         # float | null
   "order_start_signal": true,# bool | null
   "entry_quality": "good",   # agent-defined | null
   "output": {...},           # full raw LLM output dict
   "input_context": {...},
   "market_snapshot": {...},
   "bus_payload": {...},
   "latency_ms": 1234}}       # int | null
# found=false → {"agent_id": "...", "found": false, "decision": null}
```

---

### manage_sub_prompt
Read, replace, append, or delete a runtime sub-prompt extension for a target agent.

**Parameters:** `agent`* (target agent id), `command`* (read|replace|append|delete), `prompt` (required for replace/append)

**Returns (read):** `{"agent": "...", "command": "read", "prompt": "..."|null, "exists": true}`
**Returns (delete):** `{"agent": "...", "command": "delete", "deleted": true}`
**Returns (replace/append):** `{"agent": "...", "command": "replace", "prompt": "...", "length": 42}`
**On error:** `{"error": "..."}`

---

### assessment_memory
Get or set a persisted compact message for a target agent (cross-agent communication).

**Parameters:** `agentid`* (target agent id), `mode`* (get|set), `message` (required for set)

**Returns (get):** `{"agentid": "...", "mode": "get", "message": "..."|null, "exists": true}`
**Returns (set):** `{"agentid": "...", "mode": "set", "message": "...", "length": 42}`
**On error:** `{"error": "..."}`

---

## Bridge Tools (config-driven)

Bridge tools are defined in `config/RunTime/agent_tools.json5` and let one agent query another.
Each takes a `question` parameter (and `agent` too, if no fixed target is configured).

**Returns (success):**
```python
{"response": "...", "from_agent": "GLOBL-ALL___-GA-TA001"}
```
**Returns (failure — no bus / no target / target not running / timeout):**
```python
{"error": "Target agent '...' is not currently running. ..."}
```
Always check for an `"error"` key before reading `"response"`. Bridge tool names and targets are
project-specific — see `config/RunTime/agent_tools.json5`.

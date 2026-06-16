[Back to Documentation Index](README.md)

# tools/market — Market Data Tools

Tools for retrieving price data and computing technical indicators. These are the primary tools used by Analysis Agents (AA) to perform market analysis.

## Tools

### `get_candles` — GetCandlesTool

Retrieves historical OHLCV candle data for any supported timeframe.

**Input:**
```json
{
  "timeframe": "H1",
  "count": 100,
  "pair": "EURUSD"
}
```

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `timeframe` | string | ✓ | — | `M5`, `M15`, `M30`, `H1`, `H4`, `D1` |
| `count` | integer | — | 50 | Number of candles (1–500) |
| `pair` | string | — | agent default | Currency pair |

**Returns:**
```json
[
  {
    "timestamp": "2026-03-02T11:00:00Z",
    "timeframe": "H1",
    "open": 1.08210,
    "high": 1.08390,
    "low": 1.08150,
    "close": 1.08340,
    "volume": 12450.0,
    "spread": 0.8
  }
]
```

Candles are returned in ascending time order (oldest first). The last element is the most recent completed bar.

**Data source:** M5 candles come from the database directly. All higher timeframes (M15, M30, H1, H4, D1) are resampled on-demand from M5 data — no additional broker API calls are made.

**Approval mode:** `direct`

---

### `calculate_indicator` — CalculateIndicatorTool

Computes a technical indicator on the specified pair and timeframe.

**Input:**
```json
{
  "indicator": "RSI",
  "period": 14,
  "timeframe": "H1",
  "pair": "EURUSD"
}
```

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `indicator` | string | ✓ | — | Indicator name (see list below) |
| `period` | integer | — | indicator default | Calculation period |
| `timeframe` | string | — | `H1` | Timeframe for data |
| `pair` | string | — | agent default | Currency pair |
| `std_dev` | float | — | 2.0 | For BB (Bollinger Bands) |

**Supported Indicators:**

| Name | Returns |
|---|---|
| `EMA` | `{"value": 1.08234}` |
| `SMA` | `{"value": 1.08190}` |
| `RSI` | `{"value": 58.3}` |
| `ATR` | `{"value": 0.00420}` |
| `BB` | `{"upper": 1.0851, "middle": 1.0824, "lower": 1.0797}` |
| `VWAP` | `{"value": 1.08301}` |
| `DXY` | `{"value": 103.41, "correlation": 0.87, "trend": "bullish"}` |

**Returns example (RSI):**
```json
{
  "indicator": "RSI",
  "period": 14,
  "timeframe": "H1",
  "pair": "EURUSD",
  "value": 58.3
}
```

**DXY notes:** The `DXY` indicator computes a synthetic Dollar Index from five component pairs (EURUSD, USDJPY, GBPUSD, USDCAD, USDCHF) using the ICE weighting formula. The broker adapter tracks all five pairs permanently; the indicator reads their stored candles and derives a DXY series. `correlation` is the Pearson correlation between the trading pair and DXY over the same window.

**Internals:** The tool calls `IndicatorToolset.calculate()` which fetches candles from `DataContainer` and dispatches to `data/indicators.py`. Standard indicators (EMA, SMA, RSI, ATR, BB) use **pandas-ta**. Swing high/low detection uses **scipy.signal.find_peaks**. VWAP uses a NumPy implementation (pandas-ta VWAP requires a DatetimeIndex). DXY follows a separate code path that aggregates component pair candles before calculation.

**Approval mode:** `direct`

---

### `get_session_status` — ForexSessionStatusTool

Returns the current state of all four major Forex sessions (Sydney, Tokyo, London, New York) for a given UTC timestamp.

**Input:**
```json
{
  "timestamp_utc": "2026-05-14T13:00:00Z",
  "pair": "EURUSD"
}
```

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `timestamp_utc` | string | — | current time | UTC timestamp in ISO 8601 format |
| `pair` | string | — | agent default | Currency pair for pair-specific context |

**Returns:**
```json
{
  "timestamp_utc": "2026-05-14T13:00:00Z",
  "sessions": {
    "sydney":   {"status": "closed", "is_holiday": false, "minutes_since_open": null, "minutes_until_close": null},
    "tokyo":    {"status": "closed", "is_holiday": false, "minutes_since_open": null, "minutes_until_close": null},
    "london":   {"status": "active", "is_holiday": false, "minutes_since_open": 300, "minutes_until_close": 240},
    "new_york": {"status": "opening_hour", "is_holiday": false, "minutes_since_open": 0, "minutes_until_close": 540}
  },
  "active_sessions": ["london", "new_york"],
  "session_count": 2,
  "overlap": "london_newyork",
  "liquidity_estimate": "very_high",
  "recommended_action": "trade",
  "pair_context": {
    "pair": "EURUSD",
    "primary_sessions": ["london", "new_york"],
    "active_primary": ["london", "new_york"],
    "current_relevance": "optimal",
    "pair_liquidity": "very_high"
  }
}
```

**Session status values:**

| Status | Meaning |
|---|---|
| `active` | Session is open, not in first or last hour |
| `opening_hour` | Session opened less than 60 minutes ago |
| `closing_hour` | Session closes within 60 minutes |
| `closed` | Outside trading hours |
| `closed_holiday` | Bank holiday for that session's country |
| `closed_weekend` | Saturday or Sunday in local session time |

**`overlap` values:** `london_newyork`, `tokyo_london`, `sydney_tokyo`, `none`, `other`

**`liquidity_estimate` values:** `very_high`, `high`, `medium`, `low`, `very_low`

**`recommended_action` values:**

| Value | Condition |
|---|---|
| `trade` | Liquidity `high` or `very_high`, no holiday or transitional issues |
| `caution` | Liquidity `medium`, or any session in `opening_hour`/`closing_hour` |
| `avoid` | Liquidity `very_low`, or a major session (London/NY) has `closed_holiday` |

**`pair_context`** is only included when a `pair` argument is provided. `current_relevance` is `optimal` when all primary sessions for the pair are active, `partial` when some are, and `off_hours` when none are.

**Internals:** Uses Python stdlib `zoneinfo` for DST-accurate local time conversion. Uses the `holidays` library for bank holiday detection per country (AU/JP/GB/US). Weekend detection is per-session local weekday, so Sydney Monday and London/NY Sunday are handled independently.

**Snapshot integration:** Typically added as a `market_session_context` tool block with a transform script that strips the verbose `local_time` field from each session:

```json5
{
  "id": "session_status",
  "tool_name": "get_session_status",
  "role": "market_session_context",
  "output_key": "session_status",
  "enabled": true,
  "arguments": {},
  "transform_script": "result = {k: v for k, v in tool_output.items() if k != 'sessions'} | {'sessions': {name: {f: s[f] for f in ['status', 'is_holiday', 'minutes_since_open', 'minutes_until_close']} for name, s in tool_output.get('sessions', {}).items()}}"
}
```

**Approval mode:** `direct`

---

## Typical Analysis Agent Cycle

An AA agent with these tools follows this pattern in its LLM tool-use loop:

```
Turn 1: get_candles(timeframe="M5", count=100)
Turn 2: get_candles(timeframe="H1", count=50)
Turn 3: calculate_indicator(indicator="EMA", period=50, timeframe="H1")
Turn 4: calculate_indicator(indicator="EMA", period=200, timeframe="H1")
Turn 5: calculate_indicator(indicator="RSI", period=14, timeframe="H1")
Turn 6: calculate_indicator(indicator="ATR", period=14, timeframe="H1")
Final:  Output JSON with bias (BIAS_LONG / BIAS_SHORT / NEUTRAL) and reasoning
```

The system prompt instructs the agent to follow this exact analysis process.

---

## Performance Notes

- `get_candles` with `timeframe="M5"` is a direct DB query — typically < 5ms
- `get_candles` with `timeframe="H1"` fetches ~720 M5 bars from DB and resamples in RAM — typically 10–30ms for 50 H1 bars
- `calculate_indicator` includes the candle fetch; total time is dominated by the DB query
- Results are **not cached between tool calls** — each call reads fresh data from DB


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
| `fast_period` | integer | — | — | For MACD fast EMA |
| `slow_period` | integer | — | — | For MACD slow EMA |
| `signal_period` | integer | — | — | For MACD signal |
| `std_dev` | float | — | 2.0 | For Bollinger Bands |

**Supported Indicators:**

| Name | Returns |
|---|---|
| `EMA` | `{"value": 1.08234}` |
| `SMA` | `{"value": 1.08190}` |
| `RSI` | `{"value": 58.3}` |
| `ATR` | `{"value": 0.00420}` |
| `MACD` | `{"macd": 0.00021, "signal": 0.00018, "histogram": 0.00003}` |
| `BOLLINGER_BANDS` | `{"upper": 1.0851, "middle": 1.0824, "lower": 1.0797}` |
| `STOCHASTIC` | `{"k": 67.4, "d": 61.2}` |
| `VWAP` | `{"value": 1.08301}` |

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

**Internals:** The tool calls `IndicatorToolset.calculate()` which fetches candles from `DataContainer` and then dispatches to the appropriate function in `data/indicators.py`. All calculations are pure NumPy functions with no I/O.

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

Script Context: Entity Composer (EC) Script
===========================================

This document describes the execution context of an **EC (EventComposer)
Script** in OpenForexAI.

Function signature
------------------

The script must define exactly one async entry point:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
async def main(input, config, tools):
    ...
    return result_dict  # or None to skip output emission
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Return a `dict` to emit an output event downstream.  
Return `None` (or omit the return) to silently skip — no event is emitted.

Parameters
----------

### `input` — dict

The event payload that triggered this EC run. Shape depends on the event source.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
event_type = input.get("event_type")
payload    = input.get("payload") or {}
agent_id   = input.get("agent_id")
timestamp  = input.get("timestamp_utc")
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### `config` — dict

The EC instance configuration — the JSON you entered in the **Config** tab. Use
this for per-instance settings without changing the script itself.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
threshold = float(config.get("threshold", 0.5))
pair      = str(config.get("pair", "EURUSD"))
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### `tools` — tool caller

Provides access to registered broker/indicator tools. Call with `await`.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
result = await tools.call("get_candles", {
    "timeframe": "M5",
    "count": 20,
    "pair": config.get("pair", "EURUSD"),
})

candles = result.get("candles") or []
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Available tools can vary by instance — check registered tools in the Tools
panel.

 

Common tool calls
-----------------

### Get candles

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
resp    = await tools.call("get_candles", "timeframe": "M5", "count": 20)
candles = resp.get("candles") or []
last    = candles[-1] if candles else {}
close   = float(last.get("close", 0))
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### Calculate indicator

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
resp = await tools.call("calculate_indicator", 
    "indicator": "RSI",
    "period":    14,
    "timeframe": "H1", )
rsi_val = resp.get("value")
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### Get swing levels

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
resp       = await tools.call("get_swing_levels", "timeframe": "H1")
resistance = (resp.get("nearest_resistance") or {}).get("price")
support    = (resp.get("nearest_support")    or {}).get("price")
atr        = resp.get("atr")
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 

Return value
------------

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
return {
    "signal":    "long",           # or "short", "none"
    "reason":    "RSI < 30",
    "price":     close,
    "timestamp": input.get("timestamp_utc"),
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Return `None` to suppress the output event:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
if not signal:
    return None
return {"signal": signal, "price": close}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 

Error handling
--------------

Wrap tool calls defensively — tools can fail if the broker is disconnected:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
try:
    resp = await tools.call("get_candles", {"timeframe": "M5", "count": 10})
    candles = resp.get("candles") or []
except Exception as e:
    return {"error": str(e)}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 

Full example
------------

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
async def main(input, config, tools):
    pair      = config.get("pair", "EURUSD")
    threshold = float(config.get("rsi_threshold", 30.0))

    resp    = await tools.call("get_candles", "timeframe": "M5", "count": 5, "pair": pair )
    rsi_r   = await tools.call("calculate_indicator", "indicator": "RSI", "period": 14, "timeframe": "H1" )

    candles = resp.get("candles") or []
    last    = candles[-1] if candles else {}
    close   = float(last.get("close", 0))
    rsi     = rsi_r.get("value")

    if rsi is None or rsi > threshold:
        return None

    return {
        "signal": "long",
        "rsi":    round(rsi, 2),
        "price":  close,
        "pair":   pair,
    }
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

 

All supported tools
-------------------

 

-   **ask_ga_market_outlook** - question (required), agent (the agentid
    optional)

-   **assessment_memory** — agentid, mode (required), message

-   **auto_place_order** — broker, pair, direction (required), order_type,
    units, lots, entry_price, risk_pct, stop_loss, take_profit, limit_price,
    stop_price, trailing_stop_distance, reasoning, confidence

-   **calculate_indicator** — broker, pair, indicator (required), period
    (required), timeframe (required), history, smooth_period

-   **close_position** — broker, pair, position_id (required), units, lots,
    reasoning

-   **get_account_status** — broker

-   **get_candles** — broker, pair, timeframe (required), count

-   **get_last_decision** — agentid

-   **get_open_positions** — broker, pair

-   **get_order_book** — broker, pair, status_filter, limit, with_aa_analysis

-   **get_session_status** — timestamp_utc, pair

-   **get_swing_levels** — broker, pair, timeframe (required), lookback,
    prominence, atr_period, min_gap_atr, max_levels, current_price,
    price_source, sort_by

-   **manage_sub_prompt** — agent (required), command (required), prompt

-   **modify_order** — broker, pair, position_id (required), stop_loss,
    take_profit, reasoning

-   **place_order** — broker, pair, direction (required), order_type (required),
    units, lots, entry_price, risk_pct, stop_loss, take_profit, limit_price,
    stop_price, trailing_stop_distance, reasoning, confidence

-   **raise_alarm** — severity (required), title (required), message (required),
    context

-   **trigger_sync** — broker, pair

Script Context: Entity Composer (EC) Script
===========================================

This document describes the execution context of an **EC (EventComposer)
Script** in OpenForexAI (see `openforexai/composers/composer.py`).

Function signature
------------------

The script must define exactly one async entry point:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
async def main(input, config, tools):
    ...
    return result_dict  # or None to skip output emission
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Return a `dict` to emit it as an `EC_OUTPUT`/`ec_output` event downstream.
Return `None` (or omit the return) to silently skip — no event is emitted.

Parameters
----------

### `input` — dict

The **raw trigger event's payload**, unwrapped (`input_json = dict(payload)` in
`composer.py`) — not a generic envelope. Its exact keys depend entirely on
which event triggered this run (`event_triggers` in this EC's config). It
**never contains `instrument`, `pair`, or `symbol`**, no matter which event
triggered it — that lives on `message` instead (below), never on `input`. This
is the most common scripting mistake here: don't write `input.get("pair")`,
it structurally can't work. For example, `m5_candle_trigger`'s payload looks
like:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
{
    "broker_name": "mt5_oxs_t",
    "candle": {"timestamp": "...", "open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1005, "spread": 1.2},
    "is_null_candle": False,
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`analysis_result`/`ec_output` (an upstream AA or EC relaying its result) instead
carry `{"response": "<raw text, usually JSON>", "trigger", "trigger_source", ...}`
— check the source event's own documentation/producer for its exact shape;
when unsure, log the whole thing (`log(str(input))`) once and check the
monitoring stream.

### `message` — dict (not a parameter — a global)

Metadata about the triggering event itself, separate from `input`:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
{
    "id": "...",                 # the triggering AgentMessage's id, or None
    "event_type": "m5_candle_trigger",
    "source_agent_id": "...",    # who/what published the trigger
    "instrument": "EURUSD",      # this EC's configured pair
    "chain": [...],              # correlation chain of message ids
    "correlation_id": "...",
    "payload": { ... },          # identical to `input` above
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Real production usage (from the `EC-RELAY` script, which sits between AA and BA):

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
symbol = message.get("instrument")
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### `config` — dict

The EC instance configuration — the JSON you entered in the **Config** tab. Use
this for per-instance settings without changing the script itself.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
threshold = float(config.get("threshold", 0.5))
pair      = str(config.get("pair", "EURUSD"))
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### `tools` — tool caller

Provides access to whatever tools are checked for this EC (`tool_config.allowed_tools`).
Call with `await tools.call("tool_name", **kwargs)` — **keyword arguments directly,
not a dict as a second positional argument**:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
candles = await tools.call("get_candles", timeframe="M5", count=20)
last_close = float(candles[-1]["close"]) if candles else None
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**`get_candles` is the one tool whose result is a bare list**, not a dict — `tools.call(...)`
returns exactly the tool's own return value (`content = json.dumps(raw_result)`, then
`json.loads()`), and `GetCandlesTool.execute()` returns `candles[-count:]` directly. Every
other tool here (`calculate_indicator`, `get_swing_levels`, `get_open_positions`, ...)
returns a dict — only `get_candles` doesn't. `candles.get("candles")` on the result is a bug
(`AttributeError` — lists have no `.get()`); use `candles` itself as the list.

Also note: `get_candles`'s `pair`/`broker` schema fields are accepted but currently ignored by
the tool — it always reads `context.broker_name`/`context.pair` (this EC's own configured
pair), never the call's own arguments. Passing `pair=...` here does nothing.

Available tools can vary by instance — check registered tools in the Tools
panel.

Other globals injected into the script namespace
-------------------------------------------------

Available as bare names, not parameters:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
log(message: str, level: str = "info", pin: bool = False) -> None
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Synchronous. Emits a structured message to the monitoring bus (filter by event
type `ec_script_log`). `level`: `"info"` / `"warning"` / `"error"`. `pin=True`
marks it pinned so monitors keep it visible. Real usage (from `EC-RELAY`):
`log(f"{symbol}: signal blocked - {count} position(s) already open", level="info", pin=True)`.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
async def emit(event_type: str, payload: dict | None = None, instrument: str | None = None) -> None
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Publishes an event to the EventBus directly, `source_agent_id` set to this EC's
own id — separate from (and in addition to) the return-value output event.
Real usage (from `EC-RELAY`): `await emit("ec_guard_block", {"reason": "tool_error", "pair": symbol})`.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
def debug(message: Any) -> None
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Streams live to this EC's **Test** tab, only while a run was started via its
"Test" button — a true no-op otherwise (zero cost in live/production runs).
Reports the calling source line and elapsed seconds. Filter in the monitoring
stream via event type `ec_debug_log`.

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
async def ask_llm(
    llm_name: str,
    messages: list[dict] | str | None = None, *,
    system_prompt: str = "", tools: list[dict] | None = None,
    temperature: float | None = None, max_tokens: int | None = None, timeout: float = ...,
) -> LLMResponseWithTools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Lets this EC make its own ad-hoc LLM call, independent of any AA/BA agent:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
# Shorthand: single user message
response = await ask_llm("azure_azmin", "What is the EURUSD trend?")
print(response.content)

# Full tool-use conversation
response = await ask_llm(
    "azure_gpt4mini",
    messages=[{"role": "user", "content": "..."}],
    system_prompt="You are a Forex expert.",
    tools=[...],
)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`response.content` (text, may be `None` if the model only called tools),
`response.tool_calls` (list, may be empty), `response.stop_reason`
(`"end_turn"` | `"tool_use"` | `"error"`).

Common tool calls
-----------------

### Get candles

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
candles = await tools.call("get_candles", timeframe="M5", count=20)
last    = candles[-1] if candles else {}
close   = float(last.get("close", 0))
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### Calculate indicator

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
resp = await tools.call("calculate_indicator", indicator="RSI", period=14, timeframe="H1")
rsi_val = resp.get("value")
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### Get swing levels

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
resp       = await tools.call("get_swing_levels", timeframe="H1")
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
    candles = await tools.call("get_candles", timeframe="M5", count=10)
except Exception as e:
    return {"error": str(e)}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An unhandled exception fails the whole run (`EC_RUN_FAILED` + `SYSTEM_ERROR` on
the monitoring bus) — the `try`/`except` above is only needed if you want to
still emit a partial/fallback output instead of failing outright.

Full example
------------

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
async def main(input, config, tools):
    pair      = config.get("pair", "EURUSD")
    threshold = float(config.get("rsi_threshold", 30.0))

    candles = await tools.call("get_candles", timeframe="M5", count=5)
    rsi_r   = await tools.call("calculate_indicator", indicator="RSI", period=14, timeframe="H1")

    last    = candles[-1] if candles else {}
    close   = float(last.get("close", 0))
    rsi     = rsi_r.get("value")

    if rsi is None or rsi > threshold:
        return None

    log(f"{pair}: RSI {rsi:.1f} <= {threshold} — long signal", level="info", pin=True)
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

All argument names above match each tool's registered schema, but always
call `tools.call("tool_name", **kwargs)` with keyword arguments — never a
dict as a positional second argument.

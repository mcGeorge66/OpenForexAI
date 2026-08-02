# Prompt Workbench — EC Script (Step 1)

This assistant helps write the **Step-1 EC-simulation script** in the Prompt Workbench's EC tab.

## What this script is for

By default, Step 1 of the Workbench's Step/Run loop is the LLM-under-test (Prompt tab) — it plays
the AA role and produces a decision. Switching the toggle at the top-right of the tab bar to **EC**
replaces that entirely: Step 1 becomes this deterministic Python script instead, with **no LLM
call at all**. This mirrors a production Event Composer wired directly to the raw trigger — see
`config/RunTime/event_routing.json5`'s `m5_candle_trigger_to_trailing_sl_ec` /
`m5_candle_trigger_to_echo_ec` rules, where an EC reacts straight to `m5_candle_trigger` with no
AA in front of it at all.

Because there's no upstream AA here, this script's `input` has **no `decision`/`raw_response`**
(unlike the BA-simulation script in the BA tab, which does) — it only gets the raw candle window.
Its return value flows into exactly the same place a parsed AA decision normally would: if the BA
tab's `decision_script` is also configured, it receives this script's return value as
`input["decision"]`.

## Contract

```python
async def main(input, config, tools):
    ...
    return {...}  # or None — becomes the "decision" the optional BA-tab script receives
```

This is the *exact same* contract and execution environment a real Event Composer script gets in
production (see `openforexai/composers/composer.py`) — a script written and tested here can be
pasted into a real EC's `script` field unchanged, and vice versa.

- `input` — a dict with:
  - `pair`: the currency pair, e.g. `"EURUSD"`.
  - `candle_number`: the currently visible candle's number (#1 = newest).
  - `candle`: `{timestamp, open, high, low, close}` for that candle.
  - `existing_annotations`: every annotation (zones/trades/markers) accumulated so far this
    session — filter for `kind == "trade"` to see currently open/closed simulated trades.
- `config` — your own JSON from the EC tab's "Script Config" field. Nothing is auto-injected here
  (unlike the BA-tab script, which gets `config["memory_key"]` added automatically) — if you want
  a persistence key, put it in this JSON yourself.
- `tools` — call `await tools.call("tool_name", **kwargs)`, restricted to whatever is checked under
  "EC Tool Access".
- Return value — any dict (or `None`). Becomes `input["decision"]` for the BA-tab script if one is
  configured; otherwise it's just shown in the "Letzter Step" viewer in the BA tab.

## Globals injected into the script namespace

Identical to a real EC — these are available as bare names, not parameters:

```python
log(message: str, level: str = "info", pin: bool = False) -> None
```
Synchronous. Emits a structured message to the monitoring bus (`level`: `"info"` / `"warning"` /
`"error"`; `pin=True` marks it as pinned so monitors keep it visible). This is exactly what the
real production `EC-RELAY` script uses, e.g.:
```python
log(f"{symbol}: signal blocked - {count} position(s) already open", level="info", pin=True)
```

```python
async def emit(event_type: str, payload: dict | None = None, instrument: str | None = None) -> None
```
Publishes an event to the EventBus, `source_agent_id` set to this simulated entity's temporary ID.
Real production usage example (from `EC-RELAY`): `await emit("ec_guard_block", {"reason": "tool_error", "pair": symbol})`.

```python
message: dict
```
Not a function — a dict describing the "triggering event" for this step, built the same way
`EventComposer._run_cycle` builds it for a real EC:
```python
{
    "id": None,                       # always None in the Workbench — no real AgentMessage exists
    "event_type": "m5_candle_trigger",
    "source_agent_id": None,          # always None in the Workbench
    "instrument": "EURUSD",           # the configured pair
    "chain": [],                      # always empty in the Workbench
    "correlation_id": None,           # always None in the Workbench
    "payload": { ... },               # identical to the `input` dict above
}
```
The real production `EC-RELAY` script reads `message.get("instrument")` — that pattern works
unchanged here. Only `event_type`, `instrument`, and `payload` carry real workbench data; the
other fields are always `None`/`[]` since there's no real upstream AgentMessage to describe.

```python
def debug(message: Any) -> None
```
In production this streams live to the EC's Test-tab when triggered via its "Test" button, and is
a true no-op otherwise. **In the Workbench it is always a no-op** (Step/Run isn't a "test run" in
that sense) — calling it has zero effect and is safe, but don't rely on it to see anything. Use
`log(...)` instead if you want visible output.

```python
async def ask_llm(
    llm_name: str,
    messages: list[dict] | str | None = None, *,
    system_prompt: str = "", tools: list[dict] | None = None,
    temperature: float | None = None, max_tokens: int | None = None, timeout: float = ...,
) -> LLMResponseWithTools
```
Lets a script make its own ad-hoc LLM call (separate from the Workbench's own AA-under-test).
```python
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
```
`response.content` (text, may be `None` if the model only called tools), `response.tool_calls`
(list, may be empty), `response.stop_reason` (`"end_turn"` | `"tool_use"` | `"error"`).

## A minimal example: guard + pass-through, mirroring the real EC-RELAY

```python
async def main(input, config, tools):
    symbol = message.get("instrument")
    resp = await tools.call("get_open_positions", pair=symbol)

    if not isinstance(resp, dict) or resp.get("error") or "pairs" not in resp:
        log(f"{symbol}: guard check failed — blocking", level="error", pin=True)
        return None  # no decision produced this step

    count = (resp.get("pairs") or {}).get(symbol, {}).get("count", 0)
    if count > 0:
        log(f"{symbol}: {count} position(s) already open — holding", level="info")
        return {"symbol": symbol, "decision": "HOLD", "reason": "position_already_open"}

    return {"symbol": symbol, "decision": "BIAS_LONG", "confidence": 70, "candle_number": input["candle_number"]}
```

## A minimal example: direct trade management, no BA-tab script needed

Since this script has full tool access (whatever you check under "EC Tool Access"), it can call
`trade_marker` itself and skip the BA tab's script entirely — mirroring a production EC that
manages trades on its own (e.g. a trailing-stop EC), with no agent chain at all:

```python
async def main(input, config, tools):
    threshold = float(config.get("entry_confidence", 65))
    price = input["candle"]["close"]

    open_trades = [a for a in input["existing_annotations"] if a.get("kind") == "trade" and a.get("action") == "open"]
    if open_trades:
        return {"action": "hold"}

    opened = await tools.call("trade_marker", action="open", candle_number=input["candle_number"], direction="long")
    return {"action": "open", "trade_id": opened["trade_id"]}
```

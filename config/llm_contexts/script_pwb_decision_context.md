# Prompt Workbench — BA Decision Script

This assistant helps write the **BA-simulation script** in the Prompt Workbench's Simulation tab.

## What this script is for

The Prompt Workbench's Step/Run loop mirrors the real AA→BA production split:

- **Step 1** produces a decision each step — a directional market read, not a trade instruction.
  By default this is the **AA-under-test** (the LLM, configured via the Prompt tab and "AA Tool
  Access"; empty tool access runs it via `Agent._run_decision_only_cycle`, the exact method real
  production AA agents use for their decision). The Prompt/EC toggle at the top-right of the tab
  bar can switch Step 1 to a deterministic **EC script** instead (no LLM at all) — see
  `script_pwb_ec_context.md` for that contract. Either way, this script (Step 2) receives the
  result identically: a `decision` dict, whichever kind of Step 1 produced it.
- This script plays the **BA role**: given Step 1's decision, it deterministically decides
  whether/how to act, and draws the outcome on the chart. It is plain Python, not a second LLM
  call — fast, cheap, and fully under your control.
- This runs with the *exact same* execution environment a real Event Composer script gets in
  production (see `openforexai/composers/composer.py`) — `log`/`emit`/`debug`/`message`/`ask_llm`
  globals included (documented below), not just `input`/`config`/`tools`. A script written and
  tested here can be pasted into a real EC's `script` field unchanged.

## Contract

```python
async def main(input, config, tools):
    ...
    return {"action": "open" | "hold" | "close", ...}  # or None
```

- `input` — a dict with:
  - `decision`: the AA's parsed JSON decision for this step (e.g. `{"decision": "BIAS_LONG", "confidence": 72, "reasoning": "...", "invalidation_level": 1.0980, "target": 1.1050}`), or `{}` if the AA's answer wasn't valid JSON.
  - `raw_response`: the AA's raw answer text (useful if `decision` parsing failed).
  - `pair`: the currency pair, e.g. `"EURUSD"`.
  - `candle_number`: the currently visible candle's number (#1 = newest).
  - `candle`: `{timestamp, open, high, low, close}` for that candle.
  - `existing_annotations`: every annotation (zones/trades/markers) accumulated so far this session — filter for `kind == "trade"` to see currently open/closed simulated trades yourself if you don't want to rely on `assessment_memory`.
- `config` — your own JSON from the "Script Config" field, with one key always injected: `config["memory_key"]` (the value of the "Memory Key" field).
- `tools` — call `await tools.call("tool_name", **kwargs)`, restricted to whatever is checked under "BA Script Tool Access" (default: `assessment_memory`, `trade_marker`).
- Return value — whatever dict you want; it's shown in the chat under the step's answer. It has no required shape (unlike `input["decision"]`, nothing here is parsed by the Workbench itself) — this is not what actually draws to the chart. The chart is drawn by whatever `trade_marker` calls your script makes.

## Globals injected into the script namespace

Identical to a real EC — these are available as bare names, not parameters:

```python
log(message: str, level: str = "info", pin: bool = False) -> None
```
Synchronous. Emits a structured message to the monitoring bus (`level`: `"info"` / `"warning"` /
`"error"`; `pin=True` marks it as pinned so monitors keep it visible).

```python
async def emit(event_type: str, payload: dict | None = None, instrument: str | None = None) -> None
```
Publishes an event to the EventBus, `source_agent_id` set to this simulated entity's temporary ID.

```python
message: dict
```
Not a function — a dict describing the "triggering event" for this step, built the same way
`EventComposer._run_cycle` builds it for a real EC:
```python
{
    "id": None, "event_type": "analysis_result", "source_agent_id": None,
    "instrument": "EURUSD",   # the configured pair
    "chain": [], "correlation_id": None,
    "payload": { ... },       # identical to the `input` dict above
}
```
Only `event_type`, `instrument`, and `payload` carry real workbench data — `id`/`source_agent_id`/
`correlation_id`/`chain` are always `None`/`[]` since there's no real upstream AgentMessage here.

```python
def debug(message: Any) -> None
```
In production this streams live to an EC's Test-tab when triggered via its "Test" button, and is a
true no-op otherwise. **In the Workbench it is always a no-op** — safe to call, but use `log(...)`
if you want to actually see output.

```python
async def ask_llm(llm_name, messages=None, *, system_prompt="", tools=None, temperature=None, max_tokens=None, timeout=...) -> LLMResponseWithTools
```
Lets this script make its own ad-hoc LLM call, separate from the Step-1 AA-under-test:
```python
response = await ask_llm("azure_azmin", "Given this setup, is it a high-quality entry?")
print(response.content)
```
`response.content` (text, may be `None` if the model only called tools), `response.tool_calls`
(list, may be empty), `response.stop_reason` (`"end_turn"` | `"tool_use"` | `"error"`).

## Persisting state across steps and sessions

`assessment_memory` is the same tool used in production for EC↔agent messages. It stores one text message per key (`agentid`), backed by the database — it survives page reloads and new sessions, not just this one run.

```python
state_raw = await tools.call("assessment_memory", agentid=config["memory_key"], mode="get")
state = json.loads(state_raw["message"]) if state_raw.get("exists") else {}
...
await tools.call("assessment_memory", agentid=config["memory_key"], mode="set", message=json.dumps(state))
```

`json` is not pre-imported — put `import json` at the top of your script if you need it (the script namespace is a plain Python module, same as an Event Composer script).

## Drawing the decision on the chart

Use `trade_marker` exactly as documented for the tool itself:

```python
opened = await tools.call(
    "trade_marker", action="open", candle_number=input["candle_number"],
    direction="long" if input["decision"]["decision"] == "BIAS_LONG" else "short",
)
```

Remember: once a leg is recorded, its candle/direction are permanent (mirrors a real broker fill) — `op="change"` may only update a `note`, and `op="delete"` fails unless "delete of trades accepted" is checked. To end a position, call `trade_marker` again with `action="close"` and the same `trade_id`.

## A minimal example: confidence threshold + AA's own invalidation/target as exit

```python
import json

async def main(input, config, tools):
    decision = input.get("decision") or {}
    memory_key = config["memory_key"]
    threshold = float(config.get("entry_confidence", 65))

    raw = await tools.call("assessment_memory", agentid=memory_key, mode="get")
    state = json.loads(raw["message"]) if raw.get("exists") else {}
    open_trade_id = state.get("trade_id")

    price = input["candle"]["close"]

    if open_trade_id:
        # Already in a position — check the AA's own stop/target from when it was opened.
        if price <= state["invalidation_level"] or price >= state["target"]:
            await tools.call("trade_marker", action="close", trade_id=open_trade_id, candle_number=input["candle_number"])
            await tools.call("assessment_memory", agentid=memory_key, mode="set", message="{}")
            return {"action": "close", "trade_id": open_trade_id}
        return {"action": "hold", "trade_id": open_trade_id}

    bias = decision.get("decision")
    confidence = decision.get("confidence", 0)
    if bias in ("BIAS_LONG", "BIAS_SHORT") and confidence >= threshold:
        direction = "long" if bias == "BIAS_LONG" else "short"
        opened = await tools.call("trade_marker", action="open", candle_number=input["candle_number"], direction=direction)
        await tools.call("assessment_memory", agentid=memory_key, mode="set", message=json.dumps({
            "trade_id": opened["trade_id"],
            "invalidation_level": decision.get("invalidation_level"),
            "target": decision.get("target"),
        }))
        return {"action": "open", "trade_id": opened["trade_id"]}

    return {"action": "hold"}
```

`{"entry_confidence": 65}` in the Script Config field tunes the threshold without touching the script.

[Back to Config](ui.config.en.md)

# Entity Config — Event Composer (EC)

The `Entity Config` page is where you create, configure, and manage **Event Composers** (ECs). Event Composers are Python scripts that run as first-class members of the event bus alongside agents. They are a fundamental building block for workflow logic that does not require a full LLM agent cycle.

---

## What is an Event Composer?

An Event Composer is a Python script that:
- Lives on the event bus alongside agents
- Is triggered by events (just like agents)
- Can call any registered tool via the `tools` proxy
- Can optionally invoke an LLM via `ask_llm()`
- Returns a `dict` to publish an `ec_output` event, or `None` to stop the workflow

**The key difference from agents:** Agents always call an LLM as their core action. Event Composers do NOT automatically call an LLM — they are pure Python logic with optional LLM access. This makes them fast, predictable, and cheap to run.

### Why Event Composers Exist

In a multi-agent trading system, not every decision requires LLM reasoning. Many workflow steps are deterministic:

- "Forward this analysis to the BA agent" — no LLM needed, just relay
- "Stop the workflow if there is no trade signal" — no LLM needed, just check a field
- "Don't trade if a position is already open" — no LLM needed, just call `get_open_positions`
- "Add account margin data to the analysis before the BA agent sees it" — no LLM needed, just enrich

Event Composers handle all of these cases efficiently. They also provide a lightweight gateway for the rare case where a second LLM opinion is warranted (via `ask_llm()`).

### Position in the Workflow Chain

The typical AA → EC → BA workflow:

```
1. AA Agent runs on M5 trigger
   → Analyzes market data
   → Publishes analysis_result event

2. Event Routing: analysis_result from this AA → this EC
   → EC script executes

3. EC script:
   → Optionally filters, enriches, or transforms the input
   → Returns dict → ec_output event is published
   → Returns None → workflow stops, no ec_output

4. Event Routing: ec_output from this EC → BA Agent
   → BA Agent receives the (optionally enriched) analysis
   → BA Agent decides whether to place an order
```

This chain gives you a clean separation of concerns:
- **AA** handles market analysis
- **EC** handles workflow logic and filtering
- **BA** handles order execution

---

## EC ID Format

Every Event Composer has a unique ID following this format:

**`BROKER(5)-PAIR(6)-EC-NAME`**

Segments:
- **BROKER** — 5-character broker code (same as agent IDs), e.g. `OXS_T`, `GLOBL`
- **PAIR** — 6-character pair code, e.g. `EURUSD`, `ALL___`
- **EC** — fixed literal, always `EC`, identifies this as an Event Composer (not an agent)
- **NAME** — descriptive name, no strict length limit but keep it concise

**Examples:**
- `OXS_T-EURUSD-EC-RELAY` — EURUSD relay EC for OXS test broker
- `OXS_T-USDJPY-EC-RELAY` — USDJPY relay EC for OXS test broker
- `OXS_T-GBPUSD-EC-FILTER` — GBPUSD signal filter EC
- `GLOBL-ALL___-EC-ECHO` — Global echo/debug EC for all pairs
- `OXS_T-EURUSD-EC-RISK` — EURUSD risk check EC

---

## Editor Layout

The Entity Config page has three main areas:

1. **EC List panel** — left sidebar with all existing ECs and a "New EC" button
2. **Editor tabs** — center panel with Script, Config, and Test tabs
3. **Metadata fields** — right panel or inline with EC ID, enable, pair, broker, and all configuration fields

### EC List Panel

Lists all registered Event Composers. Click any EC to load it into the editor. Each entry shows:
- EC ID
- Enable status (active/inactive badge)
- Script status (last save or error indicator)

**New EC button:** Creates a blank EC entry with empty script and config. You must fill in a valid EC ID and save before the EC becomes active.

---

## Tab 1: Script

The Script tab contains a Monaco code editor (the same editor used in VS Code) with:
- Python syntax highlighting
- Auto-indentation
- Line numbers
- Find/replace (Ctrl+H)
- Horizontal and vertical scrolling

### Script Contract

Every EC script must define an `async def main(input, config, tools)` function. This is the only required entry point.

```python
async def main(input, config, tools) -> dict | None:
    """
    input:  The triggering event payload (Python dict).
            For analysis_result events, this is the full analysis JSON.
    config: The config_json from the EC configuration, parsed as Python dict.
            Contains any custom settings you define (thresholds, flags, etc.).
    tools:  ToolsProxy object for calling registered tools.
    
    Returns:
        dict  → published as ec_output event
        None  → workflow stops, no ec_output is published
    """
    ...
```

### Injected Functions

In addition to the three parameters, the following are available directly in the script scope (no import needed):

**`await tools.call("tool_name", **kwargs)`**

Calls any registered tool with keyword arguments. Returns the tool's result as a Python dict or list.

```python
candles = await tools.call("get_candles", pair="EURUSD", timeframe="H1", count=20)
positions = await tools.call("get_open_positions")
account = await tools.call("get_account_status")
```

**`await ask_llm(llm_module, question_or_messages, ...)`**

Calls an LLM without going through the full agent pipeline. Two usage forms:

Simple form (string question):
```python
response = await ask_llm(
    "azure_azmin",
    "Should I enter a BUY trade given this analysis? Answer YES or NO only."
)
answer = response.content  # string
```

Full form (messages list):
```python
response = await ask_llm(
    "azure_azmin",
    messages=[
        {"role": "user", "content": "Review this trade setup: ..."}
    ],
    system_prompt="You are a conservative risk manager.",
    tools=[]  # optional tool list for the LLM call
)
```

The `response` object has a `.content` attribute with the LLM's text response.

### What Makes a Good Script

- **Keep it focused:** One EC should do one thing well — relay, filter, enrich, or check
- **Return None explicitly** when you want to stop the workflow — don't raise exceptions for flow control
- **Use config for thresholds:** Don't hardcode values like max spread or min confidence in the script — put them in config_json so they can be changed without touching the script
- **Handle missing fields gracefully:** Use `.get()` with defaults rather than direct key access — analysis payloads can evolve over time
- **Be careful with ask_llm:** Each LLM call has cost and latency. Use it sparingly and only when genuine LLM reasoning adds value that deterministic logic cannot provide

---

## Tab 2: Config

The Config tab contains a JSON editor for the `config_json` field. This is a free-form JSON object that you define completely — it has no fixed schema.

The config is passed to your `main()` function as the `config` Python dict. Use it to externalize any values that might need tuning without script edits:

```json
{
  "max_spread": 20,
  "min_confidence": 0.65,
  "allowed_decisions": ["BUY", "SELL"],
  "position_limit": 1,
  "debug_mode": false
}
```

In your script:
```python
max_spread = config.get("max_spread", 20)
min_confidence = config.get("min_confidence", 0.65)
```

Good candidates for config_json values:
- Numeric thresholds (spread limits, confidence floors, ATR multiples)
- Feature flags (enable/disable specific checks)
- LLM module names for `ask_llm` calls
- Pair-specific overrides
- Message templates

---

## Tab 3: Test

The Test tab lets you execute the EC script immediately against the running system with a custom input payload.

### Test Workflow

1. Write your JSON test payload in the input editor (simulates the triggering event)
2. Click **Run**
3. The script executes against the live system (real tools, real data)
4. Results appear in the output panel

**Important:** You must **save** the script and config before testing. The Test tab always runs the saved version of the script, not the version currently open in the editor if unsaved. Saving automatically hot-reloads the EC in the running system.

### Input Editor

A JSON editor where you compose the test payload. Typically this is a sample `analysis_result` event payload:

```json
{
  "agent_id": "OXS_T-EURUSD-AA-ANLYS",
  "pair": "EURUSD",
  "decision": "BUY",
  "confidence": 0.78,
  "order_start_signal": "YES",
  "entry": 1.0921,
  "stop_loss": 1.0885,
  "take_profit": 1.0990,
  "analysis_summary": "Bullish breakout above key resistance...",
  "spread": 8
}
```

### Output Panel

After execution, the output panel shows:

| Element | Description |
|---|---|
| Status badge | Green "Success" or red "Error" |
| Latency | Execution time in milliseconds |
| Output JSON | The dict returned by `main()`, formatted with line breaks |
| Copy button | Copies the full JSON output to clipboard |

If `main()` returned `None`, the output shows `null` with a note that the workflow would have stopped.

If the script raised an exception, the error badge appears with the exception message and traceback.

---

## All Configuration Fields

### ec_id

**Required.** The unique identifier for this Event Composer.

Format: `BROKER(5)-PAIR(6)-EC-NAME`

Must not conflict with any existing EC or agent ID. The `EC` literal in position 3 is what distinguishes EC IDs from agent IDs.

### enable

`true` — The EC is active and receives events.
`false` — The EC configuration is stored but inactive.

Use to temporarily disable an EC without deleting it. Hot-reload safe — disabling takes effect without restart.

### pair

The currency pair context for this EC. Used when tools are called without an explicit pair argument. Also used for event routing matching.

Example: `EURUSD`

Set to `ALL___` for ECs that handle signals from multiple pairs (generic relay or enrichment logic).

### broker

The broker module this EC is associated with. Used as default context for tool calls that require a broker (e.g. `get_open_positions`).

### timer

Periodic activation independent of events.

```json
{
  "enabled": true,
  "interval_seconds": 300
}
```

Most ECs do not use timers — they react to events. Use timers for ECs that need to run a periodic check (e.g. monitor open positions every 5 minutes).

### AnyCandle

Integer divisor applied to `m5_agent_trigger` events. Works identically to the agent AnyCandle setting.

- `1` — every M5 candle
- `3` — every 15 minutes
- `6` — every 30 minutes
- `12` — every hour

Only relevant if `m5_agent_trigger` is in event_triggers.

### event_triggers

List of event types that activate this EC. Same event names as used for agents.

Common values:
- `analysis_result` — output from AA agents (most common for relay ECs)
- `ec_output` — output from another EC (chained ECs)
- `m5_agent_trigger` — new M5 candle
- `timer` — periodic activation

### session_filter

Same format as agent session_filter. Restricts when the EC processes events.

```json
[
  {"session": "london", "pre": 10, "post": 0},
  {"session": "new_york", "pre": 0, "post": -30}
]
```

Use the same session filter as the AA agent it is paired with to ensure consistent behavior — if the AA only runs during London/NY, the EC should also only process during those sessions.

### tool_config

Controls tool execution within the EC script.

```json
{
  "allowed_tools": ["get_open_positions", "get_account_status", "get_candles"],
  "max_tool_turns": 5,
  "script_timeout_seconds": 60
}
```

| Field | Description |
|---|---|
| `allowed_tools` | List of tools the script is permitted to call. Calls to other tools will be rejected. |
| `max_tool_turns` | Maximum number of tool calls the script may make per execution. Default: 10. |
| `script_timeout_seconds` | Maximum execution time for the script in seconds. Default: 60. Scripts that exceed this are terminated. |

### config_json

JSON string passed as the `config` parameter to `main()`. Define any custom settings your script needs here. No fixed schema — completely free-form.

### script

The Python script content. Defined on the Script tab. Stored as a string in the configuration.

---

## The Workflow Chain in Detail

Understanding how ECs fit into the larger system:

### Step 1: AA Agent Analysis

The AA agent for EURUSD runs on M5 candles (every 15 minutes with AnyCandle=3). It builds a market snapshot, analyzes conditions, and publishes an `analysis_result` event:

```json
{
  "event_type": "analysis_result",
  "source_agent": "OXS_T-EURUSD-AA-ANLYS",
  "pair": "EURUSD",
  "decision": "BUY",
  "confidence": 0.82,
  "order_start_signal": "YES",
  "entry": 1.0921,
  "stop_loss": 1.0885,
  "take_profit": 1.0990
}
```

### Step 2: Event Routing

The event routing configuration (in the Event Routing config page) directs `analysis_result` events from `OXS_T-EURUSD-AA-ANLYS` to `OXS_T-EURUSD-EC-RELAY`.

### Step 3: EC Executes

The EC script runs with `input` = the analysis payload above. The script applies its logic (relay, filter, enrich) and either returns a dict or None.

### Step 4: ec_output Published

If the script returned a dict, the system publishes an `ec_output` event with the returned dict as payload.

### Step 5: BA Agent Receives

Event routing directs `ec_output` from `OXS_T-EURUSD-EC-RELAY` to `OXS_T-ALL___-BA-ANLYS`. The BA agent receives the payload via `pass_trigger=true` and makes its execution decision.

---

## Complete Script Examples

### Example 1: Transparent Relay

The simplest possible EC — forwards the analysis unchanged. Use this as a starting point when you want the EC framework without any filtering logic yet.

```python
async def main(input, config, tools):
    return input  # forward unchanged, publish as ec_output
```

**When to use:** When you need the EC infrastructure (for future filtering or enrichment) but don't want any logic today. The relay pattern lets you add logic later by modifying only the EC script, without changing agent configurations.

---

### Example 2: Signal Filter (Stop on No Signal)

Stops the workflow if the AA agent did not generate a trade signal.

```python
async def main(input, config, tools):
    # Only proceed if there is an active trade signal
    if input.get("order_start_signal") != "YES":
        return None  # stop - no trade signal, BA agent will not run
    
    # Only proceed for directional decisions
    decision = input.get("decision", "NEUTRAL")
    if decision == "NEUTRAL":
        return None  # stop - neutral decision, nothing to trade
    
    # Only proceed if confidence is above threshold
    min_confidence = config.get("min_confidence", 0.70)
    confidence = input.get("confidence", 0)
    if confidence < min_confidence:
        return None  # stop - confidence too low
    
    return input  # all checks passed, forward to BA agent
```

**config_json example:**
```json
{
  "min_confidence": 0.70
}
```

**When to use:** This is the standard filter EC for any trading pair. It prevents the BA agent from running on every analysis cycle, only waking it up when there is a real trade opportunity.

---

### Example 3: Position Guard (Prevent Duplicate Positions)

Checks whether a position is already open for this pair before allowing a new order.

```python
async def main(input, config, tools):
    # Check for active signal first
    if input.get("order_start_signal") != "YES":
        return None
    
    pair = input.get("pair", "EURUSD")
    
    # Check for existing open positions
    positions = await tools.call("get_open_positions", pair=pair)
    
    max_positions = config.get("max_positions", 1)
    if positions and len(positions) >= max_positions:
        # Position already exists - don't open another
        return None
    
    return input  # no existing position, allow trade
```

**config_json example:**
```json
{
  "max_positions": 1
}
```

**When to use:** Any system where you want strict one-position-per-pair discipline. Prevents pyramiding unless you explicitly set `max_positions` higher.

---

### Example 4: Spread Filter (Skip During High Spread)

Prevents trading when the broker spread is too wide (common during news events and market open/close).

```python
async def main(input, config, tools):
    if input.get("order_start_signal") != "YES":
        return None
    
    spread = input.get("spread", 0)
    max_spread = config.get("max_spread", 20)
    
    if spread > max_spread:
        # Spread too wide - skip this signal
        return None
    
    return input
```

**config_json example:**
```json
{
  "max_spread": 20
}
```

**When to use:** Always include spread checking in production trading systems. The AA agent calculates spread and includes it in the analysis payload. The EC checks it before allowing execution.

Note: The spread value in the analysis payload is in broker-native units (typically pips × 10 for standard 5-digit pricing). A value of `20` typically means 2.0 pips.

---

### Example 5: LLM Second Opinion (Risk Manager)

Uses `ask_llm()` to get a conservative LLM to review the trade setup before forwarding it.

```python
async def main(input, config, tools):
    if input.get("order_start_signal") != "YES":
        return None
    
    analysis_summary = input.get("analysis_summary", "No analysis provided")
    decision = input.get("decision", "NEUTRAL")
    confidence = input.get("confidence", 0)
    
    llm_module = config.get("llm_module", "azure_azmin")
    
    # Ask a second LLM to review the trade
    prompt = (
        f"Trade review request:\n"
        f"Direction: {decision}\n"
        f"Confidence: {confidence:.0%}\n"
        f"Analysis: {analysis_summary}\n\n"
        f"Should this trade proceed? Answer YES or NO only."
    )
    
    response = await ask_llm(
        llm_module,
        prompt,
        system_prompt=(
            "You are a conservative risk manager. "
            "Your job is to prevent bad trades, not to encourage good ones. "
            "When in doubt, say NO."
        )
    )
    
    answer = response.content.strip().upper()
    
    if "NO" in answer:
        return None  # second opinion says no
    
    # Add risk review note to output
    return {
        **input,
        "risk_review": "APPROVED",
        "risk_reviewer": llm_module
    }
```

**config_json example:**
```json
{
  "llm_module": "azure_azmin"
}
```

**When to use:** High-stakes trading where a second opinion provides genuine risk reduction. Note: this adds latency (one extra LLM call per trade signal) and cost. Use judiciously.

---

### Example 6: Data Enrichment (Context Injection)

Enriches the analysis payload with additional market context before passing it to the BA agent.

```python
async def main(input, config, tools):
    if input.get("order_start_signal") != "YES":
        return None
    
    pair = input.get("pair", "EURUSD")
    
    # Collect additional context that the AA agent didn't include
    h4_candles = await tools.call("get_candles", pair=pair, timeframe="H4", count=5)
    open_positions = await tools.call("get_open_positions")
    account = await tools.call("get_account_status")
    
    # Enrich the input with additional data
    enriched = {
        **input,
        "h4_context": h4_candles,
        "existing_positions": open_positions,
        "account_balance": account.get("balance"),
        "margin_free": account.get("margin_free"),
        "margin_level_pct": account.get("margin_level_pct")
    }
    
    # Risk check: don't trade if margin level is dangerously low
    margin_level = account.get("margin_level_pct", 999)
    min_margin_level = config.get("min_margin_level_pct", 200)
    
    if margin_level < min_margin_level:
        return None  # insufficient margin level
    
    return enriched
```

**config_json example:**
```json
{
  "min_margin_level_pct": 200
}
```

**When to use:** When the BA agent's system prompt references account data or H4 context that the AA agent doesn't collect. The EC handles the enrichment so the BA agent receives everything it needs in a single payload.

---

## Combining Multiple Checks

In practice, most production ECs combine several checks into a single script:

```python
async def main(input, config, tools):
    pair = input.get("pair", "EURUSD")
    
    # 1. Signal check
    if input.get("order_start_signal") != "YES":
        return None
    
    if input.get("decision") == "NEUTRAL":
        return None
    
    # 2. Confidence check
    min_confidence = config.get("min_confidence", 0.65)
    if input.get("confidence", 0) < min_confidence:
        return None
    
    # 3. Spread check
    max_spread = config.get("max_spread", 25)
    if input.get("spread", 0) > max_spread:
        return None
    
    # 4. Position check
    positions = await tools.call("get_open_positions", pair=pair)
    if positions and len(positions) >= config.get("max_positions", 1):
        return None
    
    # 5. Margin check
    account = await tools.call("get_account_status")
    margin_level = account.get("margin_level_pct", 999)
    if margin_level < config.get("min_margin_level_pct", 150):
        return None
    
    # All checks passed — enrich and forward
    return {
        **input,
        "available_margin": account.get("margin_free"),
        "existing_positions_count": len(positions) if positions else 0
    }
```

**config_json example:**
```json
{
  "min_confidence": 0.65,
  "max_spread": 25,
  "max_positions": 1,
  "min_margin_level_pct": 150
}
```

This single EC handles signal filtering, confidence gating, spread filtering, position limiting, and margin checking — all in one fast Python script without an LLM call.

---

## Chained ECs

ECs can be chained: EC A publishes `ec_output` → Event Routing sends it to EC B → EC B processes and publishes another `ec_output` → BA Agent.

This is useful when different concerns need to be separated into independent scripts:

```
AA Agent → EC-FILTER (signal check) → EC-ENRICH (data enrichment) → BA Agent
```

Each EC in the chain can return None to stop the workflow at any point.

Configure chaining in Event Routing:
- Route `analysis_result` from AA → EC-FILTER
- Route `ec_output` from EC-FILTER → EC-ENRICH
- Route `ec_output` from EC-ENRICH → BA

---

## Save and Hot Reload

When you save an EC (Update button):
1. The script and configuration are written to the system configuration
2. The EC is immediately hot-reloaded in the running system
3. The next triggering event will run the new script version

**Save before testing:** The Test tab always runs the saved version. If you edit the script and run a test without saving, you are testing the old version. Always save first.

Hot reload is safe and does not affect any currently running EC instances. Pending or in-flight executions complete with the old script; subsequent triggers use the new version.

---

## Troubleshooting Common Issues

### EC runs but produces no ec_output

Check that your script returns a dict (not None) for the case you expect to produce output. Add a debug return temporarily:

```python
async def main(input, config, tools):
    # Temporary: return everything to see what comes in
    return {"debug": True, "input_received": input}
```

Use the Test tab with a representative payload to verify.

### EC raises a KeyError

The input payload did not contain the expected key. Use `.get()` with a default:

```python
# Unsafe
signal = input["order_start_signal"]

# Safe
signal = input.get("order_start_signal", "NO")
```

### EC times out

The script exceeded `script_timeout_seconds`. Common causes:
- A tool call that hangs (broker not responding)
- A loop that doesn't terminate
- `ask_llm()` taking too long

Increase `script_timeout_seconds` in tool_config if the script legitimately needs more time, or investigate the root cause.

### ask_llm returns unexpected content

The `response.content` is a raw string from the LLM. Check that your parsing logic handles variations: `"YES"`, `"Yes"`, `"YES, this trade looks good"`. Use `.strip().upper()` and check with `"YES" in answer` rather than `answer == "YES"`.

---

## Summary: EC vs Agent

| Feature | Event Composer (EC) | Agent |
|---|---|---|
| LLM call | Optional (`ask_llm()`) | Always |
| Trigger types | Events, timer, candle | Events, timer, candle |
| Snapshot profile | Not supported | Supported |
| Script language | Python (`async def main`) | System prompt (natural language) |
| Execution speed | Fast (no mandatory LLM) | Slower (LLM call on every run) |
| Cost | Low (tools only, LLM optional) | Higher (LLM every run) |
| Best for | Filtering, routing, enrichment | Analysis, decision-making |
| Returns | `dict` (continue) or `None` (stop) | Publishes event with LLM output |

[Back to Config](ui.config.en.md)

# Decision Prompt

The `Decision Prompt` page manages named prompt profiles that control what instruction text an agent receives as its system prompt during a snapshot-driven run.

Every snapshot-driven agent cycle has two configurable layers:

1. the **snapshot profile** — what data to collect and forward
2. the **decision prompt profile** — what instruction the LLM receives

This page covers layer 2.

## When the Decision Prompt is Used

After the snapshot is built by the Snapshot Engine, the AA agent initiates an LLM call. The call is structured as:

- **System message**: the text selected and assembled by the Decision Prompt profile (the instruction to the LLM — the "rules of engagement")
- **User message**: the assembled snapshot (the market data the LLM reasons about)

The Decision Prompt profile determines what appears in the system message. This is the most direct lever for controlling LLM behaviour: it defines the strategy, the reasoning framework, the output format, and the decision criteria.

## What a Decision Prompt Profile Is

A decision prompt profile is a named set of values:

| Field | Purpose |
|---|---|
| `name` | Unique identifier used to assign the profile to an agent |
| `description` | Short human-readable label shown in lists and dropdowns |
| `fallback_snapshot_profile` | Optional: snapshot profile to use for selector script data when no regular snapshot is assigned |
| `script` | Python selector script that determines which prompt version to use |
| `prompts` | Array of prompt entries; the script selects one by its `id` |

Each entry in `prompts` has:

| Field | Purpose |
|---|---|
| `id` | Integer used by the selector script to identify this entry |
| `description` | Human-readable label |
| `mode` | How the prompt integrates into the system prompt (`replace` or `append`) |
| `prompt` | The instruction text sent to the LLM; may contain `{placeholder}` tokens |
| `use_placeholders` | When checked, `{key}` tokens in the prompt are resolved from `placeholders` |

All profiles are stored in `system.json5` under the key `decision_prompt_profiles`.

---

## How Prompt Selection Works

When an agent runs a snapshot-driven cycle:

1. The snapshot is built and forwarded to the LLM as the user message.
2. The **selector script** runs. The snapshot is available via several variables (see below).
3. The script writes an integer to `result` — this is the prompt ID to use.
4. The system finds the prompt entry with that ID and uses its text and mode.
5. If no entry matches, the first entry in the list is used as fallback.

The default script `result = 1` always selects the prompt with id `1`.

---

## Selector Script

The selector script is a short Python script that runs each time an agent cycle executes. It determines which prompt version to use and can optionally populate placeholder values.

### Script Variables

The selector script has the following variables pre-populated:

| Variable | Content |
|---|---|
| `snapshot` | The full snapshot dict as built by the snapshot profile |
| `tool_outputs` | Shortcut: `snapshot["tool_outputs"]` — the processed tool block results |
| `assembled` | Shortcut: `snapshot["assembled"]` — the output of the assembly transform script, if configured |
| `placeholders` | An empty `{}` dict; fill it to supply values for prompt `{placeholder}` tokens |
| `result` | Pre-set to `1`; overwrite with the desired prompt id |

`tool_outputs` and `assembled` are empty dicts `{}` when the respective keys are not present in the snapshot.

The script has access to standard Python builtins: `int`, `float`, `str`, `dict`, `list`, `len`, `max`, `min`, `round`, `sorted`, `any`, `all`, `enumerate`, `zip`, `isinstance`, and more. Network access and file I/O are not available.

The snapshot structure shown in the **Test Snapshot** panel on the right is exactly what the script receives as `snapshot`.

### Example: always use prompt 1

```python
result = 1
```

### Example: select prompt based on account balance

```python
balance = tool_outputs.get("get_account_status_1", {}).get("balance", 0)
result = 2 if balance < 1000 else 1
```

Prompt 2 is selected when the account balance is below 1000, otherwise prompt 1.

### Example: select prompt based on open positions

```python
positions = tool_outputs.get("get_open_positions_2", [])
result = 2 if len(positions) > 0 else 1
```

### Example: select prompt based on market session

```python
session = snapshot.get("session", {})
is_london = session.get("london_open", False)
is_newyork = session.get("newyork_open", False)

if is_london and is_newyork:
    result = 3  # London/NY overlap — highest liquidity prompt
elif is_london or is_newyork:
    result = 1  # Standard active session prompt
else:
    result = 2  # Off-hours low-liquidity prompt
```

### Example: select prompt based on ATR volatility

```python
atr = snapshot.get("atr_14", 0)
atr_threshold_high = snapshot.get("atr_high_threshold", 0.0020)
atr_threshold_low = snapshot.get("atr_low_threshold", 0.0005)

if atr > atr_threshold_high:
    result = 3  # High volatility — tighter filter prompt
elif atr < atr_threshold_low:
    result = 2  # Low volatility — avoid trading prompt
else:
    result = 1  # Normal volatility — standard prompt
```

---

## Prompt Placeholders

When **Placeholders** is checked for a prompt entry, `{key}` tokens in the prompt text are replaced with values from the `placeholders` dict before the prompt is sent to the LLM.

The script is responsible for filling `placeholders`. Values can be any string, including transformed or computed values — not just raw numbers from the snapshot.

### Setting Placeholders in the Selector Script

```python
acc = tool_outputs.get("get_account_status_1", {})
balance = acc.get("balance", 0)
positions = tool_outputs.get("get_open_positions_2", [])

placeholders["broker"]    = snapshot.get("broker_name", "")
placeholders["balance"]   = str(balance)
placeholders["currency"]  = acc.get("currency", "USD")
placeholders["pos_count"] = str(len(positions))
placeholders["status"]    = "sufficient" if balance > 500 else "critical"

result = 1
```

### Prompt Text Using Placeholders

```
You are managing account {broker}. Current balance: {balance} {currency}.
Open positions: {pos_count}. Account status: {status}.
Decide whether to open a new position or stand aside.
```

After substitution, the prompt sent to the LLM:

```
You are managing account OXS_T. Current balance: 9824.93 USD.
Open positions: 0. Account status: sufficient.
Decide whether to open a new position or stand aside.
```

### Extended Placeholder Example for Forex Trading

```python
# Market data from snapshot
symbol = snapshot.get("symbol", "UNKNOWN")
timeframe = snapshot.get("timeframe", "M5")
trend = snapshot.get("trend_direction", "UNKNOWN")
atr = snapshot.get("atr_14", 0)
session = snapshot.get("session_name", "UNKNOWN")

# Account data from tools
acc = tool_outputs.get("get_account_status_1", {})
balance = acc.get("balance", 0)
equity = acc.get("equity", balance)
margin_free = acc.get("margin_free", 0)

# Derived values
atr_pips = round(atr / 0.0001, 1)
risk_capacity = "HIGH" if equity > 5000 else ("MEDIUM" if equity > 2000 else "LOW")

# Fill placeholders
placeholders["symbol"]      = symbol
placeholders["timeframe"]   = timeframe
placeholders["trend"]       = trend
placeholders["atr_pips"]    = str(atr_pips)
placeholders["session"]     = session
placeholders["balance"]     = f"{balance:.2f}"
placeholders["equity"]      = f"{equity:.2f}"
placeholders["free_margin"] = f"{margin_free:.2f}"
placeholders["capacity"]    = risk_capacity

result = 1
```

Prompt with all placeholders:

```
You are an expert Forex trader analysing {symbol} on the {timeframe} chart.
Current session: {session}.
Trend direction: {trend}.
ATR (14): {atr_pips} pips.

Account state: Balance {balance} USD | Equity {equity} USD | Free Margin {free_margin} USD.
Risk capacity: {capacity}.

Your task is to analyse the current market snapshot and return a structured trading decision.
```

### Placeholder Rules

- Only keys present in `placeholders` are resolved; unknown tokens like `{foo}` are kept as-is.
- `None` values resolve to an empty string.
- Placeholders are only active when the **Placeholders** checkbox is enabled for that prompt entry.
- If **Placeholders** is disabled, the prompt text is used literally, `{tokens}` included.

---

## Mode — replace vs append

### replace

The prompt text completely replaces the agent's base system prompt.

Use when:
- you want full control over the entire instruction the LLM receives
- the agent has a generic or empty base prompt and this prompt IS the full instruction
- you are writing a purpose-built prompt for a specific agent type or strategy

This is the most common setting.

### append

The prompt text is appended to the agent's base system prompt.

Use when:
- the agent has a permanent base instruction that should always be present
- the decision prompt adds situational guidance on top
- you want to share a base prompt across agents but vary the appended layer per strategy

Example structure with append mode:

**Agent base system prompt** (set in Agent Config):
```
You are OpenForexAI, an expert automated Forex trading system.
You always return structured JSON responses.
You never deviate from the specified output format.
```

**Decision Prompt (append mode)**:
```
Today's trading session is {session}.
Current strategy focus: {trend}-following entries on {symbol}.
Prioritise high-confidence setups with R:R above 1.5.
```

Combined prompt the LLM receives:
```
You are OpenForexAI, an expert automated Forex trading system.
You always return structured JSON responses.
You never deviate from the specified output format.

Today's trading session is London.
Current strategy focus: BULLISH-following entries on EURUSD.
Prioritise high-confidence setups with R:R above 1.5.
```

---

## Fallback Snapshot Profile

A decision prompt profile can optionally reference a **fallback snapshot profile**.

Set the `fallback_snapshot_profile` field in the profile form to the name of an existing snapshot profile.

**When it takes effect:** when an agent has a decision prompt profile assigned but no snapshot profile. In a normal snapshot-driven cycle the regular snapshot provides data to both the selector script and the LLM. When no snapshot profile is assigned, the LLM receives no snapshot data — but the selector script still needs market data to make a meaningful selection.

The fallback snapshot is built using the named snapshot profile. Its data is passed to the selector script via the same variables (`snapshot`, `tool_outputs`, `assembled`, `placeholders`). The fallback snapshot is **not** forwarded to the LLM as a user message — it is used exclusively to drive prompt selection and placeholder filling.

**Use case:** an agent whose LLM serves a purpose other than market analysis (e.g. trade management, commentary) but still needs to select a prompt based on current account state or market conditions.

---

## Profiles and Agent Assignment

A profile is not active on its own — it must be assigned to an agent.

Assignment happens in `Config → Agent Config`. Each agent has a `decision_prompt_profile` field that references a profile by name.

Workflow:

1. Create or edit a profile here in `Decision Prompt`.
2. Go to `Config → Agent Config`.
3. Select the agent.
4. Set `decision_prompt_profile` to the profile name.
5. Save.

Multiple agents can share the same profile. Changing the profile affects all agents referencing it on the next run.

---

## Practical Use Cases

### Use Case 1: Single Strategy, Always the Same Prompt

The simplest configuration: one prompt, always selected.

```python
result = 1
```

Prompt 1 (replace mode): a complete, self-contained trading strategy instruction. No placeholders needed.

This is appropriate when:
- you have a single, stable strategy
- you trade one or two pairs with identical logic
- the strategy does not need to adapt to market conditions

### Use Case 2: Strategy Switches by Session

Different sessions have different market characteristics. London tends to be trending; Asian session tends to be ranging.

```python
session = snapshot.get("session_name", "")
if "london" in session.lower() or "newyork" in session.lower():
    result = 1  # Trend-following prompt
else:
    result = 2  # Range-trading prompt
```

Prompt 1: instructs the LLM to favour trend continuation entries, higher R:R targets.
Prompt 2: instructs the LLM to favour mean-reversion entries near range boundaries, tighter R:R.

### Use Case 3: Dynamic Prompt with Account Context

For managed accounts or risk-aware trading where the prompt should reflect current account health:

```python
acc = tool_outputs.get("get_account_status_1", {})
drawdown_pct = acc.get("drawdown_percent", 0)

placeholders["symbol"] = snapshot.get("symbol", "")
placeholders["session"] = snapshot.get("session_name", "")

if drawdown_pct > 10:
    result = 3  # Defensive mode: very conservative, capital protection priority
    placeholders["mode"] = "DEFENSIVE"
elif drawdown_pct > 5:
    result = 2  # Cautious mode: reduced position sizing guidance
    placeholders["mode"] = "CAUTIOUS"
else:
    result = 1  # Normal mode: standard strategy
    placeholders["mode"] = "NORMAL"
```

Each prompt version instructs the LLM differently on risk tolerance and entry criteria.

### Use Case 4: Multi-Pair Specialisation

Different pairs benefit from different instructions. GBPUSD has a different typical spread, volatility profile, and news sensitivity than EURUSD.

```python
symbol = snapshot.get("symbol", "")
placeholders["symbol"] = symbol
placeholders["session"] = snapshot.get("session_name", "")

if symbol == "GBPUSD":
    result = 2  # GBP-specific prompt with wider spread guidance
elif symbol == "USDJPY":
    result = 3  # JPY-specific prompt with carry trade context
else:
    result = 1  # Default EURUSD / generic prompt
```

---

## Using the Editor

### Left Panel

Contains the profile form: `name`, `description`, the selector script, and the prompts list.

**Selector Script** — the script textarea with a **Copy** button and a **Test** button. The Test button opens the test window (see below).

**Prompts** — click **+ New Prompt** to add an entry. Each card has:
- `ID` — integer (must be unique within the profile)
- `Description` — human-readable label
- `Mode` — `replace` or `append`
- `Placeholders` checkbox — enables `{token}` substitution for this entry
- Prompt textarea with a **Copy** button
- **Duplicate** and **Delete** buttons

### Right Panel — Test Snapshot

Select an **Agent** and optionally a **Snapshot Profile** from the dropdowns, then click **Load Snapshot** to generate a live snapshot from the agent's current market context. The snapshot JSON is displayed with a **Copy** button.

The loaded snapshot is pre-filled into the test window when you open it.

### Saving

- **Update** — overwrites the currently selected profile
- **Save as New** — creates a new profile under the name in the `name` field
- **Delete** — removes the selected profile from `system.json5`

Renaming: change `name` and click **Update**. The old entry is replaced. Any agent referencing the old name must be updated in `Agent Config`.

### Validation

The editor blocks saving until:
- `name` is non-empty and unique across all profiles
- `description` is non-empty
- prompt IDs are unique within the profile

---

## Testing the Script

Click **Test** next to the selector script to open the test window.

**Left side — Snapshot Input**
Editable JSON, pre-filled from the right panel (or `{}` if no snapshot was loaded). Edit freely to simulate different conditions.

**Right side — Script Result**
Click **Run** to execute the script. The result shows:
- the integer in `result`
- the matched prompt entry (id, description, mode, and up to ~400 chars of prompt text)
- if **Placeholders** is enabled for the matched entry: a **Resolved** section showing the prompt text after `{token}` substitution, with its own **Copy** button
- any script error (script errors do not affect the saved profile)

Edit the snapshot JSON and click **Run** again to test different scenarios.

### Testing Tips

- Copy a real snapshot from the Test Snapshot panel, then modify specific fields to test edge cases
- Test with an empty snapshot `{}` to verify your script handles missing data gracefully
- Test all branch paths — if your script has three `if` conditions, test all three
- Verify placeholder values look correct in the Resolved view before going live

---

## Runtime Override

The `Agent Chat → Execute` function supports a `decision_prompt_profile_override` parameter. This lets you test a modified prompt for a single run without saving it to `system.json5`. The override applies only to that run and does not affect other agents or persist afterward.

---

## Prompt Writing Guidelines

A well-written decision prompt is specific, structured, and unambiguous. The following guidelines apply:

**Be explicit about output format.**
The LLM must return a machine-parseable response. Define the exact JSON structure you expect:

```
Return your decision as JSON with this exact structure:
{
  "signal": "BUY" | "SELL" | "NO_SIGNAL",
  "confidence": <integer 0-100>,
  "entry": <float>,
  "stop_loss": <float>,
  "take_profit": <float>,
  "reasoning": "<string>"
}
```

**Define what constitutes a valid signal.**
Do not leave this open to interpretation:

```
Only return BUY or SELL when ALL of the following are true:
- Trend direction is confirmed by at least two of: EMA alignment, structure break, momentum
- The entry point is at a valid support/resistance level or swing point
- ATR-based stop distance is between 1.0x and 2.5x ATR
- There are no high-impact news events within 30 minutes
Otherwise return NO_SIGNAL.
```

**Define confidence clearly.**
Give the LLM a rubric for confidence scoring:

```
Confidence scoring:
90-100: Multiple confirming factors, textbook setup, high-liquidity session
70-89: Clear directional bias with at least two confirming factors
50-69: Some signal present but one factor is uncertain or conflicting
Below 50: Return NO_SIGNAL instead
```

**Specify the strategy type.**
A trend-following prompt and a mean-reversion prompt are fundamentally different:

```
Strategy: Trend continuation
Enter only in the direction of the higher-timeframe trend.
Do not fade moves. Do not enter at extremes.
Look for pullbacks to structure as entry points.
```

Suggested screenshot:
- [Decision Prompt editor with multi-version profile](image/ui-17-decision-prompt-editor.png)

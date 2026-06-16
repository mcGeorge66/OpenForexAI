[Back to Config](ui.config.en.md)

# Agent Config

`Agent Config` is the central tool for creating, configuring, and managing individual agents. All settings are saved directly to `config/system.json5`. Changes take effect when the agent process is restarted or the agent is reloaded via trigger.

---

## Layout

The page consists of three areas:

- **Agent Selection** — select the agent to edit
- **Agent Editor** — all configuration fields
- **Sidebar** — live preview of the current configuration and validation errors

---

## Agent Selection

The dropdown at the top lists all agents in the system. Each entry shows `Agent-ID | Type | Status | LLM | Broker`. Selecting an agent populates all fields with its current values.

---

## Action Buttons

| Button | Color | Function |
|---|---|---|
| **New Empty Agent** | Amber | Clears all fields for a new agent — saves nothing yet |
| **Update** | Green | Overwrites the currently selected agent in the config |
| **Save As New** | Blue | Creates a new agent with the current Agent ID — fails if the ID already exists |
| **Delete** | Red | Deletes the currently selected agent from the config |

> **Note:** `Update` and `Delete` operate on the agent last selected from the dropdown, not necessarily the ID currently typed in the field.

---

## Fields in the Agent Editor

### Agent ID

**Format:** `BROKER(5)-PAIR(6)-TYPE(2)-NAME(1–5)`, e.g. `OAPR1-EURUSD-AA-ANLYS`

- **BROKER** — 5-character broker code, e.g. `OAPR1`
- **PAIR** — 6-character currency pair, e.g. `EURUSD` or `ALL___`
- **TYPE** — 2-character type code (see *Type* field)
- **NAME** — 1–5 character short name, e.g. `ANLYS`, `EXEC`, `MON`

The ID is automatically uppercased. It serves as the unique key for routing and startup — no two agents may share the same ID. Required field; validation fails if the format is incorrect.

---

### Enable

`true` — The agent is loaded on startup and receives events.  
`false` — The configuration remains stored but the agent is inactive and will not start.

Use this to temporarily disable agents without deleting their configuration.

---

### Pass Trigger

Controls whether the **content** of the triggering event is passed to the LLM as a user message.

`false` (default) — The LLM receives an empty user message. The agent still runs, but has no access to the event content — it works purely from its System Prompt and its own tool calls.

`true` — The event content is passed directly to the LLM as a user message:
- For `analysis_result`: the full analysis text from the AA agent
- For `timer`: a generic message ("Periodic analysis cycle...")
- For other events: trigger name, source, and payload details

**Example — AA → BA chain:**

An AA agent analyzes EURUSD and publishes an `analysis_result` with the content: *"BUY, confidence 0.87, entry 1.0920, SL 1.0880"*. A BA agent is configured so that `analysis_result` triggers it.

- `pass_trigger=false`: The BA wakes up, but the LLM receives an empty message — it does not know what the AA analyzed. Only useful if the BA retrieves the result itself via a tool call.
- `pass_trigger=true`: The BA receives the analysis text directly as its user message and can act on it immediately, e.g. place an order.

**Rule of thumb:**
- AA agent with `m5_agent_trigger` → `false` (fetches market data itself via tools)
- BA agent with `analysis_result` trigger → `true` (needs to know what was analyzed)
- Timer agents → usually `false` (the timer message contains no useful data)

---

### Comment

Free-text field for internal notes, e.g. `"Analysis agent for the Europe session"`. Has no effect on runtime behavior. Improves readability of the config file.

---

### Pair

The trading pair this agent is responsible for, e.g. `EURUSD`, `GBPUSD`, `USDJPY`.  
**Format:** 6 characters, uppercase. Automatically uppercased.

- Only active when **Type = AA**
- Disabled for other types (BA, GA, AD)
- Required for AA agents

Special value `ALL___` can be used if the agent should apply to all pairs (if supported by the backend).

---

### Type

The agent's role code:

| Code | Name | Use |
|---|---|---|
| **AA** | Analysis Agent | Analyzes market data, makes trading decisions, pair-specific |
| **BA** | Broker Agent | Communicates with the broker adapter, executes orders |
| **GA** | Global Agent | System-wide tasks, e.g. risk management |
| **AD** | Adapter | Internal system use (e.g. bridge agents) |

The type affects which fields are active (e.g. *Pair* only for AA) and how routing works internally.

---

### LLM

The LLM module this agent should use. Options come from the `modules.llm` section of `system.json5`.

Each LLM module has its own model provider, context limit, and default settings. Required field — agents cannot be saved without an LLM selection.

---

### Broker

The broker module this agent is assigned to. Options come from the `modules.broker` section of `system.json5`.

Determines which broker adapter the agent receives account data, prices, and order execution from. Required field.

---

### Temperature

Controls the randomness of LLM outputs:

| Value | Meaning |
|---|---|
| `-- module default --` (empty) | Uses the default value configured in the LLM module |
| `0.1` | Very deterministic — recommended for analysis and execution agents |
| `0.5` | Balanced |
| `1.0` | Creative and variable |

`0.1` is recommended for analysis and trading agents. Higher values are only useful for agents that should produce creative or varied outputs (e.g. reporting agents).

---

### Snapshot Profile

Optional named profile from the Snapshot Config section. When set, the system automatically builds a market context block at runtime (prices, indicators, orderbook status, etc.) and injects it into the agent prompt.

**Without profile:** The agent must fetch all context information itself via tools.  
**With profile:** Context is already in the prompt — the agent saves tool calls and receives structured data directly.

Leave empty if no snapshot is needed or if the agent builds its own context via tools.

---

### Decision Prompt Profile

Optional named prompt profile. Overrides or extends the agent's default decision behavior for this specific use case.

Can be used to run the same base agent with different decision logic without modifying the System Prompt.

---

### Timer Interval

Time interval in seconds at which the agent is triggered periodically — **only active if `timer` is added as a Kickoff Trigger**.

Default: `300` (5 minutes). The field is disabled and grayed out as long as no `timer` trigger is active.

Examples:
- `60` — every minute
- `300` — every 5 minutes
- `3600` — hourly

---

### AnyCandle

Determines how often the agent reacts to M5 candles (`m5_agent_trigger`).

| Value | Effect |
|---|---|
| `1` | Agent runs on every 5-minute candle |
| `3` | Agent runs on every third candle (equivalent to 15 minutes) |
| `12` | Agent runs once per hour |

Only relevant if `m5_agent_trigger` is active as a Kickoff Trigger. Minimum value: `1`.

---

### System Prompt

The primary instruction text for the LLM agent. Defines how the agent behaves, what decision logic it uses, what it should and should not do.

Required field — configurations without a System Prompt cannot be saved.

- **Copy** button (top right): copies the current prompt to clipboard
- **Expand** button (square icon): opens the prompt in a fullscreen editor window for comfortable editing of long prompts

The prompt has direct influence on analysis quality and decision logic. Changes to the System Prompt should be tested carefully.

---

### Kickoff Triggers

Events that trigger the agent. The agent is inactive until one of the configured events arrives.

**Available triggers:**

| Trigger | Meaning |
|---|---|
| `m5_agent_trigger` | Each new 5-minute candle (default) |
| `prompt_updated` | The agent's System Prompt was changed |
| `agent_query` | Another agent or process queries this agent directly |
| `analysis_result` | An analysis result was published on the bus |
| `signal_generated` | A trading signal was generated |
| `account_status_updated` | Account status (balance, margin, etc.) changed |
| `risk_breach` | A risk limit was exceeded |
| `order_book_sync_discrepancy` | Inconsistency detected in the orderbook |
| `timer` | Periodic execution according to *Timer Interval* |

**Usage:**
1. Select a trigger from the dropdown
2. Click the green `+` button to add it
3. To remove, click the red `−` next to the trigger tag

Multiple triggers are possible. At least one trigger is required.

---

### Session Filter

Restricts when the agent is active during the trading day. If no filter is configured, the agent responds regardless of time of day.

**Available sessions:**

| Session | Typical trading hours (UTC) |
|---|---|
| `sydney` | 21:00 – 06:00 |
| `tokyo` | 00:00 – 09:00 |
| `london` | 07:00 – 16:00 |
| `new_york` | 12:00 – 21:00 |

**Pre / Post Offsets (in minutes):**

- **Pre** — shifts the session start. Negative value = agent activates earlier (e.g. `-15` = 15 minutes before session open)
- **Post** — shifts the session end. Positive value = agent stays active longer (e.g. `30` = 30 minutes after session close)

**Usage:**
1. Click `Add session`
2. Select session from the dropdown
3. Adjust Pre/Post offsets as needed
4. Multiple sessions are possible — the agent is active if *at least one* session is active

---

### Allowed Tools

The tools the LLM agent is permitted to call in this configuration. The agent can only use tools from this list — all others are blocked.

**Usage:**
1. Select a tool from the dropdown (list comes from backend configuration)
2. Click the green `+` button to add it
3. To remove, click the red `−` next to the tool tag

**Default tools:** `get_candles`, `calculate_indicator`, `raise_alarm`

Which tools make sense depends on the agent type. AA agents need market data tools; BA agents need order execution tools.

---

### Tool Config — Forced Arguments

For each allowed tool, arguments can be fixed here. These values are automatically applied at runtime and **cannot be overridden by the LLM**.

Useful to ensure the agent always uses the correct pair, broker, or context parameters — regardless of what the model attempts to send.

**Placeholders** can be used as argument values:

| Placeholder | Replaced by |
|---|---|
| `{llm}` | Name of the configured LLM module |
| `{broker}` | Name of the configured broker module |
| `{pair}` | The configured trading pair |
| `{type}` | The agent type (AA, BA, ...) |
| `{name}` | The name portion of the Agent ID |
| `{agent_id}` | The full Agent ID |

**Usage:** An input block is shown for each allowed tool. Fields left empty are not forced — the LLM can fill them freely. The **Clear** button removes all forced arguments for a tool at once.

> Required tool arguments are marked with `*`.

---

### Max Tool Turns

Maximum number of tool calls the agent may make in a single execution cycle.

Prevents infinite loops if the model enters a recursive or stuck tool-call pattern.

Default: `8`. Minimum: `1`.

For complex analysis agents with many tool calls, a higher value may be appropriate. For simple agents, `3–5` is usually sufficient.

---

### Max Tokens

Maximum token budget for a single response or execution cycle.

Default: `4096`. Minimum: `1`.

Affects both cost and possible output length. Increase for detailed analyses or long System Prompts. The actual model limit (from the LLM module) may further constrain this value.

---

## Sidebar: Live Summary and Validation

### Live Summary

Shows the current configuration as a text preview — as it would be saved in `system.json5`. Useful for a quick check before saving.

### Validation

Lists all errors that would prevent saving:

- Agent ID format invalid
- Required fields missing (LLM, Broker, Type, System Prompt)
- No Kickoff Trigger configured

If no errors are present, `No validation issues detected.` appears in green.

---

## Typical Workflow: Creating a New Agent

1. Click **New Empty Agent** — all fields are cleared
2. Enter the **Agent ID** in the correct format
3. Select **Type** (usually `AA`)
4. Select **LLM** and **Broker** from the dropdowns
5. Enter **Pair** (for AA agents)
6. Write or paste the **System Prompt** — use the Expand button for the fullscreen editor if needed
7. Configure **Kickoff Triggers**
8. Add **Allowed Tools**
9. If needed: configure Session Filter, Forced Arguments, Timer
10. Check the right sidebar — no validation errors
11. Click **Save As New**

---

## Save Behavior and Hot Reload

When you click **Update** or **Save As New**, the UI:
1. Validates the complete configuration
2. Writes the updated agent entry to `config/system.json5`
3. Sends an `agent_config_requested` event on the event bus

The `agent_config_requested` event triggers a hot reload of agent configurations — the agent is reloaded with the new settings **without requiring a full system restart**. Changes to the system prompt, tool list, session filter, and most other fields take effect immediately on the next agent cycle.

**What requires a restart:**
- Changes to broker module selection (broker adapters are initialized at startup)
- Changes to LLM module selection (LLM clients are initialized at startup)
- Adding an agent with `enable=true` for the first time (the agent process is spawned at startup)

**What hot-reloads safely:**
- System prompt
- Allowed tools and forced arguments
- Session filter
- AnyCandle divisor
- Timer interval
- Max tool turns / Max tokens
- enable flag (disabling an agent hot-reloads; re-enabling requires restart)

---

## Agent ID Format — Complete Specification

The Agent ID is the primary identifier for every agent in the system. It is used for routing, logging, and event targeting.

**Format:** `BROKER(5)-PAIR(6)-TYPE(2)-NAME(1-5)`

Each segment is separated by a hyphen. No other characters are allowed.

### BROKER (5 characters)

A 5-character code identifying which broker or broker group this agent belongs to. Must be exactly 5 characters — pad with underscores if needed.

Examples:
- `OXS_T` — OXS broker, test/demo account
- `OXS_L` — OXS broker, live account
- `SYSTM` — system-level agents not tied to a specific broker
- `GLOBL` — global agents

This segment is used for event routing — an `analysis_result` from an EURUSD agent can be routed to only the BA agent with the matching broker code.

### PAIR (6 characters)

The currency pair this agent operates on, exactly 6 characters. Must be exactly 6 characters — pad with underscores if needed.

Examples:
- `EURUSD` — Euro vs US Dollar
- `GBPUSD` — British Pound vs US Dollar
- `USDJPY` — US Dollar vs Japanese Yen
- `ALL___` — applies to all pairs (used for BA and GA agents that serve multiple pairs)

AA agents must always have a specific pair (not `ALL___`). BA and GA agents typically use `ALL___` to receive signals for all pairs they manage.

### TYPE (2 characters)

Exactly 2 characters identifying the agent's role:
- `AA` — Analysis Agent (analyzes market data, produces trading decisions)
- `BA` — Broker/Execution Agent (communicates with broker, places orders)
- `GA` — Global/System Agent (system-wide tasks: risk, reporting, monitoring)
- `AD` — Adapter (internal bridge agents)

### NAME (1-5 characters)

A short descriptive name for the agent. 1 to 5 characters.

Common naming conventions:
- `ANLYS` — analysis agent
- `EXEC` — execution agent
- `RELAY` — relay/routing agent
- `REPO` — reporting agent
- `RISK` — risk management agent
- `MON` — monitoring agent

**Complete examples:**
- `OXS_T-EURUSD-AA-ANLYS` — OXS test broker, EURUSD analysis agent named ANLYS
- `OXS_T-ALL___-BA-ANLYS` — OXS test broker, all pairs broker/execution agent
- `SYSTM-ALL___-GA-REPO` — system-level global reporting agent

---

## Type — Detailed Breakdown

### AA — Analysis Agent

The primary workhorse. AA agents are pair-specific and responsible for:
- Collecting market data (candles, indicators, swing levels)
- Analyzing market conditions against the system prompt instructions
- Producing a structured decision (BUY/SELL/NEUTRAL, confidence, entry, SL, TP)
- Publishing `analysis_result` events consumed by BA agents or ECs

**Typical configuration for AA agents:**
- `event_triggers`: `[m5_agent_trigger]`
- `pass_trigger`: `false` (builds own context via tools or snapshot profile)
- `snapshot_profile`: set to an AA-specific profile that collects market data
- `AnyCandle`: set to 3 or 6 for less frequent analysis (every 15 or 30 minutes)
- `session_filter`: restrict to London and/or New York sessions

### BA — Broker/Execution Agent

Receives analysis results and decides whether and how to execute trades. BA agents:
- Are triggered by `ec_output` (from Event Composer relay) or `analysis_result` directly
- Read the analysis payload passed via `pass_trigger=true`
- Check account status, existing positions, risk levels
- Call `place_order`, `auto_place_order`, or do nothing
- One BA agent typically serves all pairs for a given broker

**Typical configuration for BA agents:**
- `event_triggers`: `[ec_output]` (receives filtered/relayed analysis)
- `pass_trigger`: `true` (needs the analysis JSON as input)
- `pair`: `ALL___`
- `snapshot_profile`: none or a lightweight account-status profile
- Allowed tools: `get_open_positions`, `get_account_status`, `place_order`, `auto_place_order`, `close_position`, `get_order_book`

### GA — Global Agent

System-wide agents that operate across all pairs and brokers. Examples:
- Daily P&L reporting
- Risk limit monitoring
- System health checks
- End-of-day position reconciliation

**Typical configuration for GA agents:**
- `event_triggers`: `[timer]` with a longer interval (e.g. 3600 seconds = hourly)
- `pass_trigger`: `false`
- `pair`: `ALL___`

---

## Session Filter — Comprehensive Guide

The session filter restricts when an agent processes triggers. An agent configured with a session filter will only run when at least one of its configured sessions is active at the time of the trigger.

**Important:** Session times are compared against the **candle timestamp**, not the server's system clock. The `broker_candle_utc_offset_hours` value in `system.json5` defines the UTC offset of the candle timestamps from the broker's data feed.

### Session Windows (Standard UTC Times)

| Session | Open UTC | Close UTC |
|---|---|---|
| Sydney | 21:00 (prev day) | 06:00 |
| Tokyo | 00:00 | 09:00 |
| London | 07:00 | 16:00 |
| New York | 12:00 | 21:00 |

These are approximate standard times. The actual open/close times adjust for daylight saving time (DST) in the relevant countries.

### Pre and Post Offsets

| Field | Meaning | Example |
|---|---|---|
| pre (positive) | Start the session window LATER than the official open | `pre=10` → start 10 minutes after session opens |
| pre (negative) | Start the session window EARLIER than the official open | `pre=-15` → start 15 minutes before session opens |
| post (positive) | End the session window LATER than the official close | `post=30` → end 30 minutes after session closes |
| post (negative) | End the session window EARLIER than the official close | `post=-30` → end 30 minutes before session closes |

### Practical Calculation Example

Agent configured with:
- London: `pre=10`, `post=0`
- New York: `pre=0`, `post=-30`
- `broker_candle_utc_offset_hours=3` (broker candles are UTC+3)

**London session (normal summer time, BST = UTC+1):**
- Standard London open: 07:00 UTC = 10:00 broker time
- With pre=10: agent starts at 10:10 broker time
- Standard London close: 16:00 UTC = 19:00 broker time
- With post=0: agent ends at 19:00 broker time

**New York session (summer time, EDT = UTC-4):**
- Standard NY open: 12:00 UTC = 15:00 broker time
- With pre=0: agent starts at 15:00 broker time
- Standard NY close: 21:00 UTC = 00:00 broker time (next day)
- With post=-30: agent ends at 23:30 broker time

**Result:** The agent runs from 10:10 to 19:00 broker time (London window) and from 15:00 to 23:30 broker time (NY window). During the London-NY overlap (15:00–19:00 broker time), both sessions are active, but the agent runs in either case.

### Multiple Sessions

When multiple sessions are configured, the agent is active if **any** of the configured sessions is currently active. Sessions can overlap (e.g. London/New York overlap 12:00–16:00 UTC), and the agent runs throughout the combined window.

### When to Use Session Filters

- **AA agents:** Almost always use session filters — restrict analysis to the sessions where the pair is most liquid and active. EURUSD benefits from London + New York; USDJPY from Tokyo + London overlap.
- **BA agents:** Often use the same filter as their paired AA agents, or a slightly wider window to handle late signals.
- **GA agents with timers:** Usually no filter — let the timer run at any time.

---

## AnyCandle — Frequency Control

The `AnyCandle` parameter is a divisor applied to the `m5_agent_trigger` event. It controls how often the agent actually processes an M5 candle trigger.

The system counts M5 candles (each one occurs every 5 minutes) and only wakes the agent when the count is divisible by the AnyCandle value.

| AnyCandle | Trigger frequency | Equivalent interval |
|---|---|---|
| 1 | Every M5 candle | 5 minutes |
| 2 | Every 2nd candle | 10 minutes |
| 3 | Every 3rd candle | 15 minutes |
| 4 | Every 4th candle | 20 minutes |
| 6 | Every 6th candle | 30 minutes |
| 12 | Every 12th candle | 60 minutes |
| 24 | Every 24th candle | 2 hours |
| 48 | Every 48th candle | 4 hours |

**Important note:** AnyCandle only applies to `m5_agent_trigger`. If the agent has other triggers (e.g. `timer`, `agent_query`), those fire at their own cadence regardless of AnyCandle.

**Choosing the right value:**
- For H4 or D1 chart analysis, there is no need to run every 5 minutes. AnyCandle=12 (hourly) or AnyCandle=48 (4-hourly) makes more sense.
- For M15 scalping setups, AnyCandle=3 (every 15 minutes) is appropriate.
- For aggressive systems monitoring every 5 minutes, AnyCandle=1.

---

## Tool Config — forced_arguments Deep Dive

The `forced_arguments` configuration in `tool_config` is a critical safety and consistency mechanism. It ensures that certain tool arguments are always set to specific values, regardless of what the LLM attempts to pass.

### Why forced_arguments Matters

When a BA agent calls `place_order`, you want to guarantee that:
- The `pair` argument matches the pair from the analysis signal
- The `broker` argument matches the configured broker
- The `comment` always includes the agent_id for traceability

Without forced_arguments, the LLM might hallucinate a wrong pair name, or forget to include the broker context.

### Format

```json
{
  "tool_name": {
    "argument_name": "value_or_placeholder"
  }
}
```

### Placeholders

Placeholders are resolved at runtime from the agent's own configuration:

| Placeholder | Resolves to |
|---|---|
| `{pair}` | The agent's configured pair (e.g. `EURUSD`) |
| `{broker}` | The agent's configured broker module name |
| `{llm}` | The agent's configured LLM module name |
| `{agent_id}` | The full agent ID (e.g. `OXS_T-EURUSD-AA-ANLYS`) |
| `{type}` | The agent type code (`AA`, `BA`, `GA`) |
| `{name}` | The name segment of the agent ID (e.g. `ANLYS`) |

### Example Configuration

For a BA agent that should always trade on the correct pair with the correct broker:

```json
{
  "place_order": {
    "broker": "{broker}",
    "comment": "{agent_id}"
  },
  "get_candles": {
    "pair": "{pair}",
    "timeframe": "H1"
  },
  "get_swing_levels": {
    "pair": "{pair}",
    "timeframe": "H4"
  }
}
```

With this configuration:
- `place_order` always uses the agent's own broker and stamps orders with the agent_id
- `get_candles` always requests the agent's own pair on H1 timeframe — the LLM cannot request a different pair or timeframe
- `get_swing_levels` always analyzes the agent's own pair on H4

### Forced Arguments Interaction with LLM

If the LLM calls `get_candles` and passes `{"pair": "GBPUSD", "timeframe": "M5"}`, but forced_arguments has `{"pair": "{pair}", "timeframe": "H1"}` for a EURUSD agent, the tool actually executes with `pair=EURUSD, timeframe=H1`. The LLM's values are overridden silently.

This is intentional and desirable for safety. Use forced_arguments for any parameter that must never be wrong.

---

## Complete Agent Configuration Workflow Examples

### Example: Setting Up an EURUSD AA Agent

The EURUSD AA agent is the core analysis engine for EURUSD. It runs on M5 candles (every 15 minutes via AnyCandle=3), collects market data, and publishes analysis results for downstream processing.

**Configuration values:**
- Agent ID: `OXS_T-EURUSD-AA-ANLYS`
- Type: `AA`
- Enable: `true`
- LLM: `azure_azmin`
- Broker: `oxs_test`
- Pair: `EURUSD`
- AnyCandle: `3` (every 15 minutes)
- pass_trigger: `false` (builds its own context)
- snapshot_profile: `aa_eurusd_v1`
- event_triggers: `[m5_agent_trigger]`
- session_filter: London (pre=10, post=0), New York (pre=0, post=-30)
- Allowed tools: `get_candles`, `calculate_indicator`, `get_swing_levels`, `get_session_status`, `raise_alarm`
- forced_arguments:
  - `get_candles`: `{"pair": "{pair}"}`
  - `calculate_indicator`: `{"pair": "{pair}"}`
  - `get_swing_levels`: `{"pair": "{pair}"}`
- Max tool turns: `10`
- Max tokens: `8000`

### Example: Setting Up a BA Execution Agent

The BA agent receives filtered analysis results via the Event Composer relay and executes trades.

**Configuration values:**
- Agent ID: `OXS_T-ALL___-BA-ANLYS`
- Type: `BA`
- Enable: `true`
- LLM: `azure_azmin`
- Broker: `oxs_test`
- Pair: `ALL___`
- pass_trigger: `true` (receives analysis JSON as user message)
- snapshot_profile: (none — uses analysis from trigger)
- event_triggers: `[ec_output]`
- session_filter: (same as AA agents or none)
- Allowed tools: `get_open_positions`, `get_account_status`, `place_order`, `auto_place_order`, `close_position`, `modify_order`, `get_order_book`, `raise_alarm`
- forced_arguments:
  - `place_order`: `{"broker": "{broker}", "comment": "{agent_id}"}`
  - `auto_place_order`: `{"broker": "{broker}"}`
  - `close_position`: `{"broker": "{broker}"}`
- Max tool turns: `6`
- Max tokens: `4000`

### Example: Setting Up a GA Reporting Agent

A global agent that runs hourly and sends a system status summary.

**Configuration values:**
- Agent ID: `SYSTM-ALL___-GA-REPO`
- Type: `GA`
- Enable: `true`
- LLM: `azure_azmin`
- Broker: `oxs_test`
- Pair: `ALL___`
- pass_trigger: `false`
- event_triggers: `[timer]`
- Timer: enabled, interval_seconds: `3600`
- session_filter: (none — runs at all times)
- Allowed tools: `get_account_status`, `get_open_positions`, `get_order_book`, `get_last_decision`, `raise_alarm`
- Max tool turns: `5`
- Max tokens: `2000`

---

## Common Mistakes and How to Avoid Them

### Wrong Agent ID Format

**Mistake:** `EURUSD-AA-ANLYS` (missing BROKER segment, wrong lengths)

**Correct:** `OXS_T-EURUSD-AA-ANLYS` (all 4 segments, correct lengths)

The validation panel highlights format errors before you can save.

### BA Agent with pass_trigger=false

**Mistake:** BA agent configured with `pass_trigger=false` and triggered by `ec_output`. The agent wakes up but the LLM receives an empty message — it doesn't know what to trade.

**Correct:** BA agents should almost always have `pass_trigger=true` when triggered by analysis events. The analysis payload is the primary input for the BA agent's decision.

### Missing Session Filter on AA Agent

**Mistake:** AA agent runs on every M5 candle around the clock, wasting API calls during low-liquidity periods (Sydney session for a EURUSD agent).

**Correct:** Add a session filter restricting the AA agent to London and/or New York sessions where EURUSD is most liquid.

### AnyCandle=1 for a Daily Chart Analysis Agent

**Mistake:** An agent that analyzes D1 charts but AnyCandle=1 runs every 5 minutes, calling the same D1 candles that don't change until the next day.

**Correct:** Use AnyCandle=48 (every 4 hours) or AnyCandle=12 (hourly) for agents working with higher timeframe charts. Or use a timer trigger with a long interval instead of m5_agent_trigger.

### Conflicting forced_arguments

**Mistake:** Setting `get_candles.timeframe="H1"` in forced_arguments but the system prompt instructs the LLM to "analyze M15 candles" — the LLM attempts to call `get_candles` with `timeframe="M15"` but always gets H1 data. The LLM is confused.

**Correct:** Ensure forced_arguments and system prompt instructions are consistent. Either don't force the timeframe (let the LLM choose) or update the system prompt to reflect the forced value.

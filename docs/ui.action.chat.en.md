[Back to Action](ui.action.en.md)

# Agent Chat

Agent Chat is the primary **interactive interface** for working directly with agents. It combines two distinct modes of interaction: a free-text chat panel where you can ask the selected agent anything, and a structured execution surface that runs the full agent cycle in inspect mode so you can examine every step in detail. It also serves as the primary debugging tool when an agent produces unexpected output or behaves incorrectly.

---

## Table of Contents

1. [Page Layout Overview](#1-page-layout-overview)
2. [Left Panel — Chat Controls](#2-left-panel--chat-controls)
3. [Right Panel — Chart and Inspector (AA Agents)](#3-right-panel--chart-and-inspector-aa-agents)
4. [Inspector Tab: Overview](#4-inspector-tab-overview)
5. [Inspector Tab: Snapshot](#5-inspector-tab-snapshot)
6. [Inspector Tab: LLM](#6-inspector-tab-llm)
7. [Inspector Tab: Tools](#7-inspector-tab-tools)
8. [Inspector Tab: Runtime](#8-inspector-tab-runtime)
9. [For BA Agents — Text-Only Inspector](#9-for-ba-agents--text-only-inspector)
10. [Execute vs. Send — Key Differences](#10-execute-vs-send--key-differences)
11. [The Instruction Feature](#11-the-instruction-feature)
12. [Practical Workflows and Examples](#12-practical-workflows-and-examples)
13. [Debugging Guide](#13-debugging-guide)

---

## 1. Page Layout Overview

The Agent Chat page is split horizontally into two panels:

```
┌───────────────────────────┬──────────────────────────────┐
│                           │                              │
│   LEFT PANEL              │   RIGHT PANEL                │
│   Agent Selector          │   Candlestick Chart (AA)     │
│   Timeout Field           │   Timeframe Buttons          │
│   Instruction Textarea    │   Refresh Button             │
│   Save Instruction Button │   Indicator Buttons          │
│   ─────────────────────── │   ──────────────────────── ── │
│   Chat History            │   Inspector Tabs             │
│   (message thread)        │   Overview / Snapshot / LLM  │
│   ─────────────────────── │   Tools / Runtime            │
│   Execute Button          │                              │
│   Send Button             │                              │
│   Clear Chat Button       │                              │
│   Export .md Button       │                              │
└───────────────────────────┴──────────────────────────────┘
```

For BA agents, the right panel shows only the Inspector tabs without a chart.

---

## 2. Left Panel — Chat Controls

### Agent Selector Dropdown

Located at the top of the left panel. Lists every agent defined in `system.json5`. Selecting an agent sets the target for all subsequent actions — both Send and Execute operate on the currently selected agent.

When you change the selected agent:
- The chat history displayed clears and loads the history for the newly selected agent.
- The chart in the right panel (if applicable) resets to the new agent's configured pair and timeframe.
- The inspector tabs clear and await a new Execute run.
- The saved instruction for the newly selected agent loads into the Instruction textarea.

Each agent in the dropdown is labeled by its Agent ID. The type (AA/BA/GA) may be shown as a badge next to the ID so you can quickly identify what kind of agent you are about to interact with.

### Timeout Field

A numeric input field that controls how long the system waits for the LLM to respond before timing out a request.

- **Range:** 5 to 300 seconds
- **Default:** Typically 60 seconds (varies by configuration)
- **Units:** Seconds

**When to increase the timeout:**
- When working with large, complex snapshots that take longer for the LLM to process.
- When using a slow local model (e.g., Ollama running on modest hardware).
- When an agent's context is very large due to accumulated conversation history.

**When to decrease the timeout:**
- When debugging and you want failures to surface quickly rather than waiting the full default.
- When testing with a fast, lightweight model and responses arrive in under 10 seconds consistently.

The timeout applies to both Send and Execute operations. It does not affect scheduled background cycles — those use the timeout configured in `system.json5`.

### Instruction Textarea

A text area where you can type a persistent instruction that will be prepended as a context prefix to every chat and Execute request for the currently selected agent.

This is not the system prompt (which is defined in configuration). The instruction is an additional, user-managed prefix that supplements the system prompt. Think of it as a sticky note that you attach to every message you send to this agent during a session — and it persists across sessions once saved.

**Example instructions:**
- `"You are currently analyzing EURUSD on June 3, 2026. Focus on the H1 structural bias. Ignore M5 noise."`
- `"The NFP report just released 30 minutes ago. Consider elevated volatility in your assessment."`
- `"I want you to be extra conservative — only output BIAS_LONG if confidence is above 80%."`

Instructions are per-agent — each agent has its own saved instruction. Switching agents loads that agent's saved instruction.

### Save Instruction Button

Persists the current content of the Instruction textarea to storage. The instruction will survive page refreshes and browser restarts and will reload automatically the next time you select this agent.

**Important:** The instruction only takes effect for new messages sent after saving. If you modify the instruction mid-session, previous messages in the chat history were sent without the modification.

To clear the instruction entirely, delete all text from the textarea and click Save Instruction.

### Chat Message History

The central area of the left panel shows the conversation history as a scrollable message thread. Messages are displayed in chronological order with:
- A **You** label for messages you sent via the Send button.
- An **Agent** label for responses from the LLM.
- An **Execute** label (or similar) for the summary output from a full Execute cycle run.

Each message bubble has a **copy button** (clipboard icon) that copies the full text of that message to the clipboard. This is useful for extracting analysis output or error messages for external use.

The history accumulates during your session. It is not the same as the agent's operational history — it is your interactive session. Clicking Clear Chat removes this session history from view.

### Execute Button

Triggers a **full agent cycle in inspect mode** for the currently selected agent. See [Section 10](#10-execute-vs-send--key-differences) for the detailed comparison. In brief:

- Builds the full market snapshot as the runtime would during a scheduled cycle.
- Runs the LLM reasoning with the real system prompt, the snapshot, and any saved instruction.
- Executes any tool calls the LLM makes.
- Captures all monitoring events, token counts, timing, and intermediate steps.
- Populates all five Inspector tabs with the results.
- Does **not** submit orders to the broker or persist the analysis as an operational cycle output. It is a read-only inspection run.

The Execute button is the primary tool for:
- Verifying that an agent works correctly after a configuration change.
- Understanding what the agent would decide given current market conditions.
- Debugging why a scheduled cycle produced unexpected output.

### Send Button

Sends the text currently typed in the chat input field as a **free-text direct message** to the LLM. See [Section 10](#10-execute-vs-send--key-differences) for the comparison. In brief:

- Does **not** build a snapshot.
- Does **not** run the system prompt from configuration (unless the instruction includes it).
- Simply sends your text plus any saved instruction to the LLM and returns the response.
- Useful for quick questions, exploring the model's knowledge, or asking follow-up questions about a previous Execute result.

### Clear Chat Button

Removes all messages from the current chat history display. This is a local display clear only — it does not delete any database records or affect the agent's operational state.

Use Clear Chat to start fresh when a session becomes cluttered with many rounds of Execute and Send messages.

### Export .md Button

Downloads the entire current chat history as a Markdown file. The export includes:
- All messages in the conversation thread with sender labels and timestamps.
- A clean, readable format suitable for archiving, sharing, or pasting into documentation.

This is useful for:
- Saving analysis output from a debugging session for later review.
- Sharing the results of an Execute run with a colleague.
- Building a record of what an agent decided and why on a specific date.

---

## 3. Right Panel — Chart and Inspector (AA Agents)

When an AA agent is selected, the right panel shows a candlestick chart at the top and the Inspector tabs below it.

### Candlestick Chart

Displays the last N candles (configurable, default 100) for the agent's configured instrument and timeframe. The chart is rendered using the same rendering engine as the Chart Analysis page, providing a consistent visual experience.

The chart shows:
- Standard OHLCV candlestick bars with color coding (bullish/bearish).
- Any indicators added via the indicator buttons below the chart controls.
- Historical analysis markers if present from previous scheduled cycles.

### Refresh Button (Manual Only)

Reloads the candlestick data from the broker for the current pair and timeframe. This is a **manual refresh only** — the chart does not auto-poll for new candles. You must click Refresh to see the latest price action.

**When to refresh:**
- Before clicking Execute to ensure the snapshot is built against up-to-date data.
- After a significant market move to update the visual reference.
- After switching timeframes if the chart did not reload automatically.

There is intentionally no auto-refresh on this chart. The Chat page is a diagnostic tool, not a live trading terminal. Auto-polling would add noise and distract from the analysis workflow.

### Timeframe Buttons

**Available:** M5, M15, H1 (additional timeframes may be available depending on configuration)

Clicking a timeframe button reloads the chart with candles at that resolution. The timeframe selection on the chart is independent of the agent's configured analysis timeframe. You can display M5 candles while the agent was configured to analyze H1 — this is useful for zooming into entry-level detail while the agent reasons about the higher timeframe.

### EMA / RSI Add Buttons

Quick-add buttons for the two most common indicators:
- **EMA:** Adds an Exponential Moving Average overlay to the price chart. After clicking, you can set the period and color in the indicator row that appears.
- **RSI:** Adds a Relative Strength Index oscillator panel below the chart. After clicking, you can set the period.

Multiple instances of each indicator can be added. To remove an indicator, click the trash icon on its row.

---

## 4. Inspector Tab: Overview

The Overview tab provides a **high-level summary** of the most recent Execute run. It is the first tab to read when you want to quickly assess what happened.

### Trigger Source

Shows what initiated this cycle. For Execute runs from the Chat page, this shows `manual` or `chat_execute`. For cycles triggered by the scheduler, it would show the trigger type (e.g., `cron`, `candle_close`). This helps you understand whether you are looking at a manually-triggered diagnostic run or a real operational cycle.

### Elapsed Time

Total wall-clock time from the start of the cycle to completion, in milliseconds or seconds. This is the end-to-end duration including:
- Snapshot building (price data fetches, tool calls)
- LLM API round-trip time
- Post-processing and validation

A high elapsed time often points to either slow LLM response (check the Timeout setting) or slow tool execution (check the Tools tab).

### Total Tokens

Combined token count for the entire cycle: input tokens (everything sent to the LLM) plus output tokens (the LLM's response). This is useful for:
- Estimating API cost for this type of cycle.
- Identifying if the context has grown too large (approaching model context limits).
- Comparing token usage before and after prompt optimization.

### Validation Status

Shows whether the LLM's output passed the expected schema validation. Possible values:
- `VALID` — the output matched the expected structure and all required fields are present.
- `INVALID: [reason]` — the output did not conform to the expected schema. The reason string describes what was missing or malformed.
- `SKIPPED` — validation was not applied (e.g., for free-text Send responses).

When validation fails, the BA agent that reads this AA agent's output may reject it or fall back to a safe state. Always investigate `INVALID` states.

### Built User Message / Snapshot Summary

A compact summary of the context that was assembled and sent to the LLM. Shows:
- The number of candles included.
- Which indicators were computed.
- Which tools were called during snapshot building.
- Any context flags that were active (e.g., session filter, DXY correlation).

This gives you a quick sense of how rich the context was before diving into the full Snapshot tab.

### Final LLM Output

The raw output returned by the LLM, as-received before any post-processing. For AA agents, this is typically a structured JSON block containing the decision fields. For BA agents, it may include trade decision logic. For GA agents, it may be free text or structured alerts.

Reading the final output here lets you confirm at a glance what the agent decided and with what stated reasoning — without needing to scroll through the full LLM tab.

---

## 5. Inspector Tab: Snapshot

The Snapshot tab shows the **complete market snapshot JSON** that was assembled and provided to the LLM as its context. This is the full picture of what the agent "saw" when it made its decision.

### What the Snapshot Contains

The snapshot is a structured JSON object typically including:

```json
{
  "instrument": "EUR_USD",
  "timeframe": "H1",
  "timestamp": "2026-06-03T10:00:00Z",
  "candles": [...],
  "indicators": {
    "ema_20": 1.08523,
    "rsi_14": 58.4,
    ...
  },
  "swing_levels": {
    "resistance": [...],
    "support": [...]
  },
  "session_context": {
    "current_session": "London",
    "overlap": false
  },
  "account_state": {
    "open_positions": [...],
    "balance": ...,
    "margin_used": ...
  },
  "dxy": {
    "close": 104.23,
    "direction": "DOWN",
    "correlation": -0.87
  }
}
```

The exact fields present depend on which snapshot blocks are enabled in the agent's configuration. Not all agents include all sections.

### Using the Snapshot Tab

**Verifying data freshness:** Check the `timestamp` field. If you are running Execute and the snapshot shows a timestamp from hours ago, the market data may be stale. Click Refresh on the chart and run Execute again.

**Verifying indicator values:** If an agent produced an unexpected decision, check the `indicators` block. Are the EMA, RSI, and other values what you expected given the current price action? If the values look wrong, the issue may be in the indicator configuration or the timeframe mismatch.

**Verifying swing levels:** Check `swing_levels.resistance` and `swing_levels.support`. Are the levels relevant? Are there too many or too few? If levels look wrong, investigate the swing level configuration in `system.json5`.

**Verifying account state:** For BA agents, check `account_state.open_positions`. If the agent is aware of existing positions, does it make sense that it chose not to add another trade given the risk already open?

The Snapshot tab has a **Copy** button that copies the full JSON to the clipboard for external analysis.

---

## 6. Inspector Tab: LLM

The LLM tab shows the **complete, unredacted communication** between the system and the LLM for this cycle. This is the most detailed debugging surface available.

### Effective System Prompt

The first section shows the full system prompt that was sent to the LLM for this cycle. This is the resolved, effective prompt — it includes:
- The base system prompt from configuration.
- Any dynamic injections (e.g., current date/time, session context).
- The saved Instruction if one is set.

Reading this section confirms what behavioral instructions the LLM received. If the agent is behaving unexpectedly, start here: does the system prompt say what you expect it to say?

### Request / Response Turns

The LLM tab shows all turns of the conversation in sequence. For a single-shot analysis cycle, there is typically one request and one response. For tool-using agents (those that call data tools during reasoning), there may be multiple turns:

**Turn 1 — Initial Request:**
- Full system prompt (shown separately above)
- User message including the snapshot and any instruction
- Token count for this request

**Turn 1 — Response (if tool calls):**
- The LLM's response requesting tool execution
- Each tool call listed with name and arguments
- This is not the final answer — the LLM is asking for more data

**Turn 2 — Tool Results Injected:**
- The tool results from Turn 1's calls, formatted back as a user message
- Token count including accumulated context

**Turn 2 — Final Response:**
- The LLM's actual decision/analysis output
- This becomes the final output shown in the Overview tab

Understanding this multi-turn structure is essential for debugging agents that use tools. The decision was made in the last response turn; earlier turns are reasoning and data-gathering.

### What to Look for in the LLM Tab

**Hallucinated values:** Compare the LLM's stated values (e.g., "EMA is at 1.0862") against the Snapshot tab. If they differ, the LLM may be confabulating. This indicates a context formatting issue or a model that is struggling with numeric precision.

**Reasoning chain:** Does the LLM's stated reasoning match the data in the snapshot? A coherent reasoning chain (data → analysis → conclusion) is a healthy sign. Non-sequitur conclusions despite correct data suggest a prompt clarity issue.

**Tool call arguments:** Did the LLM request the right tools with the right parameters? Incorrect tool arguments cause incorrect data to be fetched, leading to wrong decisions.

**Model refusals or errors:** If the LLM refused to respond, returned an error, or produced off-format output, it will be visible here. Common causes: context too long, model policy triggered, or invalid tool call format.

---

## 7. Inspector Tab: Tools

The Tools tab shows every tool call that was made during the cycle, with full details.

### Structure of a Tool Call Entry

Each entry in the Tools tab shows:

```
Tool: get_candles
Arguments:
  instrument: EUR_USD
  timeframe: H1
  count: 100
Result:
  [array of candle objects...]
Duration: 243ms
Status: SUCCESS
```

### Available Tool Types

Depending on the agent's configuration, tools may include:

- **get_candles** — Fetches OHLCV candle data from the broker for a specified instrument and timeframe.
- **get_indicators** — Calculates technical indicators (EMA, RSI, ATR, etc.) for a dataset.
- **get_swing_levels** — Computes swing high/low levels from price data.
- **get_account_state** — Reads current account balance, open positions, and margin usage.
- **get_dxy** — Fetches DXY (Dollar Index) price data and computes correlation.
- **place_order** — Submits a trade order to the broker (BA agents only).
- **close_position** — Closes an open position (BA agents only).
- **system_alert** — Sends a notification (GA agents).

### Using the Tools Tab for Debugging

**Slow cycles:** If elapsed time is high, check the Duration field on each tool call. A single slow tool call (e.g., a slow broker API response taking 5+ seconds) often explains the entire cycle delay.

**Wrong data:** If the snapshot contains unexpected values, verify the tool call arguments. Did `get_candles` use the right timeframe? Was `count` sufficient for the indicator calculation period?

**Failed tool calls:** A `Status: FAILED` entry means the tool returned an error. The Result field shows the error message. Common causes: broker disconnected, invalid instrument name, insufficient data for the requested period.

**Missing tool calls:** If you expected a tool to be called (based on the LLM tab showing a tool request) but it is not in the Tools tab, there may be a tool registration issue. Check `system.json5` for the agent's tool configuration.

---

## 8. Inspector Tab: Runtime

The Runtime tab shows the **stream of monitoring events** from the cycle. This is the lowest-level view of what happened, in execution order.

### Event Log Format

Each event entry shows:
- A timestamp (relative to cycle start or absolute).
- An event type label (e.g., `CYCLE_START`, `SNAPSHOT_BUILD`, `LLM_REQUEST`, `TOOL_CALL`, `VALIDATION`, `CYCLE_COMPLETE`, `CYCLE_ERROR`).
- A message with context details.

**Example Runtime log for a healthy cycle:**
```
[0ms]    CYCLE_START       agent=eurusd-h1-analyst trigger=execute
[12ms]   SNAPSHOT_BUILD    starting snapshot assembly
[23ms]   TOOL_CALL         get_candles EUR_USD H1 count=100
[267ms]  TOOL_RESULT       get_candles completed 100 candles
[268ms]  TOOL_CALL         get_indicators ema_20 rsi_14
[301ms]  TOOL_RESULT       get_indicators completed
[302ms]  SNAPSHOT_COMPLETE snapshot assembled, 8 blocks
[302ms]  LLM_REQUEST       model=gpt-4o tokens_estimate=3200
[1843ms] LLM_RESPONSE      tokens_in=3247 tokens_out=412
[1845ms] VALIDATION        status=VALID schema=aa_decision
[1846ms] CYCLE_COMPLETE    elapsed=1846ms
```

**Example Runtime log for a failed cycle:**
```
[0ms]    CYCLE_START       agent=eurusd-executor trigger=execute
[8ms]    SNAPSHOT_BUILD    starting
[19ms]   TOOL_CALL         get_account_state broker=oanda-live
[5021ms] TOOL_ERROR        get_account_state TIMEOUT after 5000ms
[5022ms] CYCLE_ERROR       Tool call failed: get_account_state timeout
                           Stack: Error: Tool timeout...
```

### What to Look for in the Runtime Tab

**Where did it fail?** Find the first `CYCLE_ERROR` or `TOOL_ERROR` event. Everything before it succeeded; the issue started there.

**How long did each step take?** The timestamps reveal where time was spent. An LLM request that takes 45 seconds indicates a timeout issue or a very large context being processed slowly.

**Was the snapshot assembled completely?** Look for `SNAPSHOT_COMPLETE`. If the cycle errored before this event, the LLM never received context, so the issue is in data fetching, not in the model itself.

**Validation errors:** A `VALIDATION INVALID` event means the LLM responded but in an unexpected format. Read the validation error message to understand which required field was missing or malformed. This typically means a prompt update is needed to reinforce the expected output structure.

---

## 9. For BA Agents — Text-Only Inspector

When a BA (Broker/Execution) agent is selected, the right panel **does not show a candlestick chart**. BA agents operate on structured analysis inputs from AA agents rather than directly on raw price charts. Showing a chart for a BA agent would be misleading — the BA agent does not "see" a chart during its cycle.

Instead, the right panel shows only the five Inspector tabs.

### BA Agent Execute Behavior

When you click Execute for a BA agent:
- The agent reads the most recent AA agent output from the database (as it would during a scheduled cycle).
- It applies its execution logic: checks account state, computes position sizing, evaluates timing and spread conditions.
- It runs its LLM reasoning to decide whether to act and how.
- It does **not** submit a real order to the broker in execute/inspect mode — it goes through all the logic but stops at the actual order submission step.

**This means you can safely run Execute on a BA agent without risking real trades.** The inspection run simulates the full logic without side effects.

### Testing BA Agents with Custom AA Output

You can test how a BA agent would react to a specific AA analysis by:
1. Selecting the BA agent in the dropdown.
2. Typing or pasting a custom AA analysis JSON into the chat input field.
3. Clicking Execute.

The BA agent will use your injected analysis as if it were the real AA output, allowing you to test specific scenarios ("how would the BA react to a BIAS_LONG with confidence 92% and order_start_signal=YES?").

---

## 10. Execute vs. Send — Key Differences

Understanding the distinction between Execute and Send is fundamental to using Agent Chat effectively.

### Execute — Full Agent Cycle

| Aspect | Detail |
|---|---|
| **What it does** | Runs the complete agent cycle in inspect mode |
| **Snapshot built?** | YES — full market snapshot assembled from broker and tools |
| **System prompt used?** | YES — the real system prompt from configuration |
| **Tool calls made?** | YES — all configured tools execute as in a real cycle |
| **Inspector populated?** | YES — all five tabs fill with data |
| **Orders submitted?** | NO — execution is inspection-only; no real trades placed |
| **When to use** | Debugging, verification, understanding what the agent would decide |
| **Input field used?** | Optional — if text is in the input field it is appended to the cycle input |

### Send — Direct LLM Message

| Aspect | Detail |
|---|---|
| **What it does** | Sends your text directly to the LLM as a chat message |
| **Snapshot built?** | NO — no market data is fetched or assembled |
| **System prompt used?** | NO (only the saved Instruction prefix is included) |
| **Tool calls made?** | NO — no tools are invoked |
| **Inspector populated?** | Minimally — only the LLM tab shows the exchange |
| **Orders submitted?** | NO |
| **When to use** | Quick questions, follow-ups, exploring model knowledge |
| **Input field used?** | YES — required; this is the message sent to the LLM |

### Practical Guidance

Use **Execute** when you want to know: "What would this agent decide right now, given real current market data?"

Use **Send** when you want to ask: "Given what you just told me in the last Execute, why did you assess the trend as bearish despite the EMA being above price?"

A common workflow is to run Execute first to get a full cycle result, then use Send to ask follow-up questions about specific aspects of that result.

---

## 11. The Instruction Feature

The Instruction feature is one of the most powerful and underused tools in Agent Chat. It provides a persistent, per-agent context prefix that supplements the system prompt without requiring configuration file changes.

### How Instructions Work

When you have text saved in the Instruction textarea for an agent, it is automatically prepended to every message sent to the LLM — both via Send and during Execute runs. The LLM sees:

```
[Instruction text you saved]

[Normal system prompt or user message]
[Snapshot or query]
```

The instruction appears before the rest of the context, giving it high visibility and weight in the model's reasoning.

### Practical Instruction Examples

**Adding event context:**
```
IMPORTANT CONTEXT: The Federal Reserve announced a 0.25% rate cut today at 14:00 UTC.
USD pairs may show elevated volatility for the next 2-4 hours. Weight this in your
analysis, particularly for EUR_USD and GBP_USD.
```

**Adjusting conservatism for a specific period:**
```
For this session, apply a high-conviction filter. Only output BIAS_LONG or BIAS_SHORT
with order_start_signal=YES if your confidence exceeds 85%. Otherwise output NEUTRAL.
```

**Adding chart context you can see but the agent cannot:**
```
I can see a clear descending triangle forming on the M30 chart from the last 8 hours.
The horizontal support is at 1.0850. The pattern apex is approximately 6 candles ahead.
Factor this pattern into your assessment.
```

**Adding session context:**
```
We are currently in the London/New York overlap session (13:00-17:00 UTC). Volume
and volatility are elevated. Prioritize H1 structure over M15 noise.
```

### Instructions vs. System Prompt

The system prompt (defined in `system.json5`) is the agent's permanent character and behavioral framework. You do not change it frequently.

The Instruction is your session-level context addition — it is for situational information that is true right now but would not belong in the permanent system prompt. After the context is no longer relevant, delete the instruction and save a blank one to clear it.

---

## 12. Practical Workflows and Examples

### Workflow 1: Checking Current EURUSD Trend

**Goal:** Quickly understand what the EURUSD analysis agent thinks about the current market.

1. Select your EURUSD AA agent from the dropdown.
2. Click Refresh on the chart (right panel) to load the latest candles.
3. Click **Execute**.
4. Wait for the cycle to complete (typically 5–30 seconds).
5. Read the **Overview** tab: what is the Decision? What is the Confidence score? What does the Final LLM Output say?
6. Read the last few sentences of the LLM output for the reasoning summary.
7. Optionally: click **Send** with a follow-up like "Can you elaborate on why you rated conviction as medium rather than high?"

**Expected outcome:** You have a structured, data-driven analysis of the current EURUSD market in under 60 seconds, with full transparency into the data that drove the conclusion.

### Workflow 2: Running Full Analysis and Reading Inspector Results

**Goal:** Deep-dive inspection of an agent cycle to validate behavior.

1. Select the agent.
2. Click **Execute**.
3. Read **Overview** first — establish: did it succeed? What was the decision? How long did it take?
4. Switch to **Snapshot** — verify the market data looks correct. Are the indicator values sensible? Are swing levels reasonable?
5. Switch to **Tools** — how many tool calls were made? Did any fail or take unusually long?
6. Switch to **LLM** — read the system prompt. Read the final response turn. Does the reasoning match the data?
7. Switch to **Runtime** — look for any warning or error events. Verify the cycle completed cleanly.

**Expected outcome:** You can confirm the agent is operating correctly or identify the exact step where something went wrong.

### Workflow 3: Debugging Unexpected Agent Output

**Scenario:** The EURUSD H1 analyst produced `BIAS_SHORT` with `order_start_signal=YES` but the chart clearly shows the H1 candles in an uptrend.

1. Select the agent.
2. Click **Execute** to reproduce the behavior with current data.
3. Go to **Snapshot** → check `candles`. Are the most recent candles bullish? Does the snapshot reflect what you see on the chart?
4. Check `indicators.ema_20` — is it in the expected range? Is it above or below price?
5. Go to **LLM** → read the reasoning. What did the model say to justify the bearish bias? Did it cite specific values? Are those values accurate?
6. If the model cited incorrect values, cross-reference with Snapshot. This is either a context formatting issue or model confabulation.
7. If the values were correct but the conclusion was wrong, the issue is in the system prompt logic or the model's interpretation of the trading strategy.

**Common resolutions:**
- Snapshot shows stale candles → Click Refresh before Execute and try again.
- Model cited wrong EMA value → System prompt may need to explicitly label which indicator is which to avoid confusion.
- Correct data, wrong conclusion → System prompt may need clearer entry criteria definitions.

### Workflow 4: Using Instructions to Add Event Context

**Scenario:** CPI inflation data was released 20 minutes ago. You want the agent to factor this in.

1. Select the affected agent (e.g., EURUSD H1 analyst).
2. In the Instruction textarea, type:
   ```
   US CPI data just released (10:30 UTC). Result: 3.1% vs 3.0% expected (slight surprise).
   USD strengthened on the print. EUR/USD dropped 40 pips in the first 5 minutes.
   Consider this macro event in your bias assessment for the next 2 hours.
   ```
3. Click **Save Instruction**.
4. Click **Execute**.
5. Read the Overview — does the agent's reasoning incorporate the CPI context?

### Workflow 5: Testing a BA Agent With Custom AA Output

**Scenario:** You want to see how the EURUSD executor (BA) responds to a strong bullish signal.

1. Select the BA agent.
2. In the chat input, paste a constructed AA output:
   ```json
   {
     "decision": "BIAS_LONG",
     "confidence": 91,
     "order_start_signal": "YES",
     "entry_quality": "HIGH",
     "reasoning": "H1 trend is clearly bullish. EMA20 rising, price above EMA. RSI at 62 (momentum without overbought). London session active."
   }
   ```
3. Click **Execute**.
4. Read the Overview — did the BA decide to enter? What position size did it calculate?
5. Read the Runtime tab — did it pass all its internal checks (spread, margin, existing positions)?

**This lets you test BA agent logic without waiting for the AA agent to naturally generate a strong signal.**

---

## 13. Debugging Guide

### The agent errors repeatedly — where do I start?

1. Run **Execute** on the Chat page.
2. Go to **Runtime** tab immediately — find the `CYCLE_ERROR` event.
3. Read the error message. It tells you which step failed.
4. For `TOOL_ERROR`: go to **Tools** tab and find the failed call. Fix the underlying issue (broker connectivity, invalid configuration).
5. For `LLM_ERROR`: go to **LLM** tab. Was the request even sent? Did it time out? Did the model return a malformed response?
6. For `VALIDATION INVALID`: the model responded but the output did not match the expected schema. Read the validation reason and update the system prompt to reinforce the expected output format.

### The agent makes the right decision in chat but wrong decisions on schedule

This typically means the scheduled cycle has different context than the manual Execute. Compare:
- **Snapshot tab on Execute** — is the data current and correct?
- Scheduled cycles may run at candle close with different timing. The snapshot may include different candle counts or indicator values depending on exactly when the cycle fires.
- Check if the Instruction textarea has a saved instruction — scheduled cycles also receive the instruction. Is the instruction still relevant or is it biasing the scheduled output?

### Token count is very high — how do I reduce it?

1. Go to **Snapshot** tab — which blocks are very large? The `candles` array is often the largest element.
2. Consider reducing the candle count in the agent's snapshot configuration.
3. Check if multiple redundant indicators are being computed and included.
4. Review the system prompt in the **LLM** tab — is it excessively long? Are there sections that could be condensed?

### The chart on the right shows old data even after Refresh

1. Verify the agent is configured for the pair and timeframe you expect.
2. Check that the broker interface is **CONNECTED** (Initial page). If the broker is disconnected, the chart fetch will silently fail and display cached data.
3. Try switching to a different timeframe and back to force a reload.

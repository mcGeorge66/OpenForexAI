[Back to Test](ui.test.en.md)

# LLM Checker

`LLM Checker` sends message sequences directly to a configured LLM module and shows the full response including tool trace. It is intentionally separate from the Agent Chat workflow — no agent cycle, no snapshot pipeline, no routing rules. What runs here is a direct LLM conversation with freely configurable context.

Use cases:
- Verify LLM connectivity before an agent goes live
- Test system prompt variants without modifying the agent
- Observe tool-calling behavior in isolation

---

## Layout

The page is split in two: chat history on the left, configuration panel on the right.

---

## Configuration Panel (Right)

### LLM

Dropdown. **Required** — no message can be sent without a selection. Shows all LLM modules from the system configuration.

After selection, Temperature and Max Tokens are automatically pre-filled with the module's values (can be overridden).

### Agent

Dropdown. Optional. Selecting an agent automatically pre-fills: Broker, Pair, System Prompt, allowed tools. Useful for quickly loading an agent's configuration context without fully starting it.

### Broker

Dropdown. Optional. Sets the broker context for tools that require one (e.g. `get_candles`, `place_order`).

### Pair

Text field. Optional. Currency pair for context, e.g. `EURUSD`. Automatically uppercased.

### System Prompt

Textarea (4 rows). Instruction text for the LLM. Default: `"You are a helpful assistant. Use tools when necessary."`

Double-clicking opens a draggable large-format editor window. Changes there are applied with "Take over" or discarded with "Close".

### Temperature

Text field. Controls LLM output randomness (0.1 = deterministic, 1.0 = creative). Pre-filled from the LLM module. Can be left empty. Must be a number if filled.

### Max Tokens

Text field. Maximum token budget for the response. Pre-filled from the LLM module. Must be a number if filled.

### Max Tool Turns

Text field. Maximum number of tool call iterations per message. Default: `8`. Prevents infinite loops. Must be a number.

### Tool Filter

Text field. Filters the tool list by name or description (case-insensitive). Useful when many tools are configured.

### Select visible / Clear visible

Two buttons:
- **Select visible**: Enables all currently filtered tools at once
- **Clear visible**: Disables all currently filtered tools at once

### Tool Checkboxes

One checkbox per available tool. Only enabled tools are made available to the LLM for this test. Empty by default — tools must be deliberately activated.

---

## Chat Panel (Left)

### Message Input

Textarea (3 rows). The message to send to the LLM. Enter sends, Shift+Enter adds a line break.

Disabled when: no LLM selected, request is in progress.

### Send

Sends the message with the current configuration. Disabled when: no LLM, empty message, or request in progress.

### Clear chat

Clears the entire chat history, tool trace, and all metadata.

---

## Chat History

Alternating message bubbles:
- **Green**: User messages
- **Blue**: Assistant responses with timestamp

While a request is running, "Running LLM + tool loop..." is shown.

---

## LLM ↔ Tool Trace

Collapsible section below the history. Shows the internal flow of the last request:

**LLM entries (per turn):**
- Turn number
- Stop reason (e.g. `tool_use`, `end_turn`)
- Number of tool calls
- Response text (truncated to 380 characters)

**Tool entries (per call):**
- Tool name
- Turn number
- Arguments
- Result (truncated to 320 characters)

**Metadata:**
- Total token count
- Final stop reason

---

## Error Messages

Shown directly in the chat when:
- Temperature, Max Tokens, or Max Tool Turns are not valid numbers
- The API returns an error

---

## Typical Workflow

1. Select **LLM**
2. Optional: select **Agent** (pre-fills context)
3. Adjust System Prompt if needed
4. Enable relevant **Tools**
5. Enter message and send
6. Review response and tool trace

---

## Purpose and Philosophy

The LLM Checker is the fastest way to test any LLM configuration registered in the system without touching live agents. Unlike Agent Chat — which routes messages through the full agent pipeline including snapshot builder, event bus, tool orchestration, and session filter — the LLM Checker sends requests directly to the LLM module and returns raw responses. This isolation is its core value.

**What makes LLM Checker different from Agent Chat:**

When an AA agent runs normally, the pipeline is:
1. Event triggers the agent
2. Snapshot builder collects candles, indicators, swing levels, and account data
3. All that context is injected into the system prompt area
4. The completed prompt is sent to the LLM
5. The LLM responds, possibly calling tools
6. The result is published as an event on the bus

The LLM Checker skips all of steps 1, 2, 3, and 5. You get a direct conversation with the LLM — exactly what you typed, exactly the system prompt you wrote, exactly the tools you enabled. Nothing else.

This means:
- A test in LLM Checker does NOT reproduce full agent behavior automatically
- To reproduce agent behavior accurately, you must paste the actual snapshot JSON as your user message
- However, for testing the LLM's raw reasoning, prompt instruction-following, and tool call logic, LLM Checker is ideal

---

## Configuration Panel — Detailed Reference

### LLM Module Selector

Dropdown showing all LLM modules defined in `config/system.json5` under `modules.llm`. **Required field** — no message can be sent without selecting an LLM.

When you select an LLM module, the Temperature and Max Tokens fields are automatically pre-filled with the module's configured defaults. You can override these values for this test session without modifying the module's base configuration.

Examples of LLM modules you might see:
- `azure_azmin` — Azure OpenAI deployment
- `anthropic_claude` — Anthropic Claude via API
- `openai_gpt4` — OpenAI GPT-4 direct

The LLM module determines the model provider, API key, endpoint, and default parameters. All of these are defined in the module configuration file in `modules/llm/`.

### Agent Selector

Dropdown showing all agents in the system. **Optional** but extremely useful. Selecting an agent automatically pre-fills:
- **Broker** — from the agent's broker field
- **Pair** — from the agent's pair field
- **System Prompt** — from the agent's system_prompt field
- **Allowed Tools** — checkboxes are set to match the agent's `allowed_tools` list
- **Temperature** — from the agent's tool_config or LLM module default
- **Max Tokens** — from the agent's tool_config

This makes the "select agent, test directly" workflow one click: choose the agent you want to debug, click the agent in the dropdown, and the LLM Checker is configured to mimic that agent's context.

**Important:** Selecting an agent does NOT modify the agent. All pre-filled values are local to this session. The live agent continues running with its own unmodified configuration.

### Broker Selector

Dropdown showing all broker modules. **Optional.** When set, this value is passed to all tools that accept a broker parameter (e.g. `get_order_book`, `place_order`, `get_account_status`).

Override this independently from the agent selector when you want to test a prompt against a different broker — for example, testing EURUSD agent logic against a paper trading broker.

### Pair Input

Text field accepting a currency pair string such as `EURUSD`, `GBPUSD`, `USDJPY`. Automatically uppercased. **Optional.** When set, tools that require a pair (such as `get_candles`) receive this value.

The field is a datalist input, meaning it shows suggested values from known agent configurations as you type. You can also type any valid pair freely.

### System Prompt

Textarea (4 rows by default). The instruction text the LLM receives at the start of every conversation in this session.

Default value when nothing is loaded: `"You are a helpful assistant. Use tools when necessary."`

**Expanding the editor:** Double-click anywhere in the textarea to open a large-format draggable modal editor. This modal provides a full-height editing surface suitable for prompts of several hundred lines. Click "Take over" in the modal to apply your changes, or "Close" to discard them.

**Take Over button:** Appears next to the System Prompt field. When an Agent is selected, clicking "Take over" copies the selected agent's current system prompt verbatim into the editor, replacing whatever was there. This is the primary mechanism for debugging: load the exact prompt the agent is using, then modify or test it directly.

If the selected agent has no system prompt, "Take over" clears the editor.

**Prompt scope:** The system prompt applies to the entire session. Every message you send in this session is accompanied by this system prompt. If you change the system prompt mid-session, the new version takes effect for all subsequent messages, but the conversation history from before the change remains in context (the LLM will have seen the old system prompt for earlier turns).

Best practice: clear the chat when you change the system prompt significantly, to avoid ambiguous context.

### Temperature

Controls the LLM's output randomness on a scale from 0.0 to 2.0 (depending on model):
- `0.0–0.1`: highly deterministic, recommended for analysis and trading decisions
- `0.3–0.5`: balanced, slight variation between runs
- `0.7–1.0`: noticeable creativity and variation
- Above `1.0`: significant unpredictability, rarely useful for trading

Pre-filled from the LLM module's default when an LLM or agent is selected. Can be left empty to use the module's default. Must be a valid number if filled.

For testing system prompts, keep temperature at `0.1` to get consistent, reproducible responses that let you isolate prompt effects from random variation.

### Max Tokens

Maximum output token budget per response. Pre-filled from the LLM module or agent config. Increase this if responses are being cut off. Decrease it to reduce API cost during rapid test iterations.

Common values:
- `1000–2000`: short, decisive responses (suitable for BA agent testing)
- `4000–8000`: detailed analysis (suitable for AA agent testing)
- `16000+`: very long analysis or document generation

### Max Tool Turns

Maximum number of tool call iterations per message. Default: `8`.

Each "turn" is one round of: LLM calls a tool → tool returns result → LLM continues. Setting this to `1` forces the LLM to stop after the first tool call and give a response. Setting it to `15` or higher allows complex multi-step reasoning chains.

If the LLM exceeds this limit, the conversation stops and reports: "Max tool turns reached."

### Tool Filter

Text input that filters the displayed tool checkboxes by name or description (case-insensitive). Useful when many tools are registered and you want to quickly find a specific one.

Type "candle" to show only tools containing "candle" in their name or description. Type "order" to show order-related tools. Clear the field to show all tools.

### Select Visible / Clear Visible

Two buttons that operate on the currently filtered tool list:
- **Select visible**: checks all checkboxes currently visible after filtering
- **Clear visible**: unchecks all checkboxes currently visible after filtering

Use these for quick bulk selection. For example: filter by "get_", then click "Select visible" to enable all read-only market data tools at once.

### Tool Checkboxes

One checkbox per registered tool. Only checked tools are passed to the LLM as available tools. An unchecked tool is completely invisible to the LLM — it will not attempt to call it.

**Empty by default.** Tools must be deliberately enabled. This is intentional: starting with no tools means the LLM responds based purely on its training and your system prompt, without accessing live data. This is useful for testing prompt structure before adding market data.

**Warning about order execution tools:** Enabling `place_order`, `auto_place_order`, `close_position`, or `modify_order` allows the LLM to execute real trades during this testing session. The LLM Checker uses the broker selected in the Broker dropdown. On a live broker, this means real orders. Use only on demo/test broker accounts unless intentionally testing live order execution.

---

## Chat Panel — Detailed Reference

### Message Input

Textarea (3 rows). Type your message to the LLM here.

- **Enter**: sends the message immediately
- **Shift+Enter**: inserts a line break without sending
- Disabled while a request is in progress

For testing purposes, you can paste any text here — including JSON payloads, structured market analysis, or sample tool outputs — to simulate what an agent would receive.

### Send Button

Sends the current message with the current configuration. The button shows a spinner during request processing. Disabled when:
- No LLM module selected
- Message input is empty
- A request is already in progress

Requests are processed in real time. The assistant's response streams token by token as it arrives from the API.

### Clear Chat Button

Removes all messages from the conversation history. The LLM will have no memory of previous exchanges after clearing.

A confirmation dialog prevents accidental clearing. Clearing does NOT reset the system prompt, tool selections, agent/broker/pair context, or any configuration fields — only the message history is removed.

Use clear chat:
- When you change the system prompt significantly (to avoid context contamination)
- Between different test scenarios
- When starting a fresh A/B comparison

---

## Chat History — Message Types

### User Messages

Displayed on the right side with a green/blue background (depends on UI theme). Each message shows:
- The message text
- Timestamp (HH:MM:SS format)
- A copy button to copy the plain text to clipboard

### Assistant Messages

Displayed on the left side. Each message shows:
- Response rendered as Markdown (headers, bold, code blocks, tables, lists all render)
- Timestamp
- Copy button (copies raw Markdown, not rendered HTML)
- Token usage shown in the trace below

The Markdown rendering matches what agents produce in production, so formatting quality of the system prompt can be evaluated directly.

### System Messages

Shown as centered neutral-color strips for informational events: session cleared, configuration changed, error from API, max tool turns reached.

### Running Indicator

While a request is processing, "Running LLM + tool loop..." appears in the chat area with a pulsing indicator. No further messages can be sent until the current request completes.

---

## LLM ↔ Tool Trace — Detailed Reference

Below the chat history is a collapsible section called "LLM ↔ Tool Trace". It shows the internal turn-by-turn execution log of the most recent request. This is the primary debugging surface.

### Structure

The trace is organized as a sequential list of turns. Each request starts at Turn 1 and increments for each tool-calling round.

**LLM Entry (per turn):**

| Field | Description |
|---|---|
| Turn | Turn number (1, 2, 3...) |
| Stop reason | Why the LLM stopped this turn: `tool_use` (called a tool), `end_turn` (finished responding) |
| Tool calls | Number of tool calls made in this turn |
| Response text | First 380 characters of the text response (truncated with "..." if longer) |

**Tool Entry (per call within a turn):**

| Field | Description |
|---|---|
| Tool name | Name of the tool that was called |
| Turn | Which turn this call belongs to |
| Arguments | The arguments the LLM passed to the tool |
| Result | First 320 characters of the tool result |

**Metadata (end of trace):**

| Field | Description |
|---|---|
| Total tokens | Total input + output tokens consumed by this request |
| Stop reason | Final stop reason for the entire request |

### Reading the Trace

A typical trace for "What is the RSI for EURUSD H1?" looks like:

```
[LLM Turn 1]
  Stop reason: tool_use
  Tool calls: 1
  Response: (empty — model went straight to tool call)

[Tool: calculate_indicator]
  Turn: 1
  Arguments: {"indicator": "RSI", "period": 14, "timeframe": "H1", "history": 1}
  Result: {"value": 58.3, "previous": 56.1, "timestamp": "2026-06-03T10:00:00"}

[LLM Turn 2]
  Stop reason: end_turn
  Tool calls: 0
  Response: The current H1 RSI for EURUSD is **58.3**, up slightly from...

[Metadata]
  Total tokens: 1,847
  Stop reason: end_turn
```

### What to Look for in the Trace

**Wrong tool arguments:** The trace reveals exactly what arguments the LLM chose. If the LLM called `get_candles` with `timeframe="M1"` when you expected `H1`, the trace shows this immediately. This usually indicates the system prompt doesn't specify the expected timeframe clearly enough.

**Missing tool calls:** If the LLM responded without calling any tools when it should have, the trace shows Stop reason `end_turn` with zero tool calls on Turn 1. This indicates the system prompt's instruction to use tools is insufficient, or the tools are not enabled.

**Excessive tool turns:** If the trace shows 8+ turns, the LLM may be in a loop. Check whether forced arguments are causing contradictory tool results, or whether the system prompt has competing instructions.

**Token consumption:** High token counts per request will show up in metadata. If a system prompt is consuming 3000+ tokens per call, optimization may be needed.

---

## Error Handling

Errors appear as system messages in the chat area (red background).

**Validation errors** (before request is sent):
- "Temperature must be a number" — non-numeric value in the Temperature field
- "Max Tokens must be a number" — non-numeric value in the Max Tokens field
- "Max Tool Turns must be a number" — non-numeric value

**API errors** (after request is sent):
- "Rate limit exceeded" — the LLM provider has throttled the request; wait and retry
- "Context length exceeded" — the combined system prompt + conversation history + tool schemas exceeds the model's context window; clear chat or shorten the system prompt
- "API key invalid" — the LLM module configuration has an incorrect API key
- HTTP 5xx errors — provider-side issues; retry after a moment

**Tool errors:**
- When a tool call fails, the error is shown inline in the tool trace with the error message in red
- The LLM receives the error text as the tool result and typically explains what happened in its response

---

## Practical Testing Workflows

### Workflow 1: Testing a New System Prompt Before Deployment

**Goal:** Verify a revised AA agent system prompt produces correct analysis output before saving it to the live agent configuration.

**Steps:**

1. Navigate to LLM Checker in the Test panel
2. Select the EURUSD AA agent from the Agent dropdown
   - This pre-fills: LLM module, Broker, Pair=EURUSD, System Prompt, and tool checkboxes
3. Click "Take over" to confirm the current live prompt is loaded
4. Expand the System Prompt editor (double-click the textarea) to open the modal
5. Edit the prompt — add, modify, or restructure sections as needed
6. Click "Take over" in the modal to apply
7. Enable tools relevant to the test: `get_candles`, `calculate_indicator`, `get_swing_levels`
8. Type a representative test message: `"Analyze current EURUSD market conditions on H1 and H4. Provide a trading decision with entry, SL, and TP."`
9. Send and observe:
   - Does the LLM call the expected tools?
   - Does the response follow the formatting rules in the prompt?
   - Is the decision logic applied correctly?
10. Iterate: adjust the prompt in the editor, clear the chat, send the same message again
11. When satisfied, copy the final prompt text and paste it into Agent Config

**Time estimate:** 5–30 minutes depending on prompt complexity. Much faster than agent cycle testing.

### Workflow 2: Reproducing an Unexpected Agent Decision

**Goal:** An agent placed a BUY order on a strong downtrend. Reproduce and understand why.

**Prerequisites:** You have the analysis output from the agent's log. It is a JSON object with fields like `decision`, `confidence`, `analysis_summary`, `order_start_signal`.

**Steps:**

1. Select the relevant BA agent from the Agent dropdown
2. Click "Take over" to load the BA agent's system prompt
3. Disable all order execution tools (`place_order`, `auto_place_order`) — test without executing real orders
4. Enable `get_order_book` and `get_open_positions` if relevant
5. Paste the exact analysis JSON the AA agent produced as your user message:
   ```json
   {
     "decision": "BUY",
     "confidence": 0.61,
     "analysis_summary": "Price is approaching support at 1.0880...",
     "order_start_signal": "YES"
   }
   ```
6. Send and observe what the BA agent's LLM reasons and decides
7. If it makes the same unexpected decision, the issue is in the BA prompt
8. If it makes a sensible decision, the issue may be in how the event was delivered (check Event Routing) or how the snapshot was injected

### Workflow 3: Validating Tool Output Quality

**Goal:** Verify that `get_swing_levels` returns correct H4 swing levels for GBPUSD.

**Steps:**

1. Select any GBPUSD agent or manually set Pair = GBPUSD
2. Enable only the `get_swing_levels` tool
3. Write a minimal system prompt: `"You are a data inspector. When asked for swing levels, call get_swing_levels and display all returned data verbatim."`
4. Send: `"Get GBPUSD H4 swing levels, max 8 levels, sorted by prominence."`
5. The LLM will call `get_swing_levels` — expand the tool result in the trace
6. Compare the returned levels against your chart
7. If levels look wrong, use Tool Executor for direct parameter control

### Workflow 4: Multi-Turn Context Consistency Test

**Goal:** Verify the LLM maintains consistent reasoning across several messages.

**Steps:**

1. Load an AA agent prompt
2. Enable `get_candles` and `calculate_indicator`
3. Send: `"What is the overall trend on H4 EURUSD based on the last 50 candles?"`
4. After the response, send: `"Now look at H1. Does it align with or contradict the H4 trend?"`
5. After the response, send: `"Given both timeframes, if you had to pick a direction right now, which would it be and why?"`
6. Evaluate: Is the final direction consistent with the LLM's earlier assessments? Does it apply the reasoning from the system prompt correctly?

The full conversation history is maintained across turns in the same session, mirroring how a stateful agent would behave if triggered multiple times.

### Workflow 5: Comparing Two Prompt Versions Side-by-Side

**Goal:** Determine which of two prompt versions handles a specific edge case better.

**Steps:**

1. Prepare your two prompt versions in a text editor
2. Paste Prompt Version A into the System Prompt editor
3. Send 4–5 standardized test messages (edge cases you care about)
4. Note the responses (or copy them)
5. Click "Clear Chat"
6. Paste Prompt Version B into the System Prompt editor
7. Send the same 4–5 messages
8. Compare responses

For a rigorous comparison, save your test messages in a separate file so you can paste them identically each time. Minor wording differences in the test messages can affect the LLM's response, so consistency is important.

---

## Key Concepts and Gotchas

### No Snapshot Building

The most important limitation: **the LLM Checker does not build a snapshot.** When an AA agent runs in production, it receives a rich context block injected into the prompt area, containing candle data, indicator values, swing levels, account status, and more — all pre-populated by the snapshot builder.

In the LLM Checker, the LLM only knows what you tell it. If you type "Analyze EURUSD", the LLM has no market data unless it calls tools to get some. This is the expected behavior — but it means a response from LLM Checker may differ from what the same prompt produces in production, where the snapshot provides data automatically.

To accurately simulate production: copy the actual snapshot output from agent logs and paste it as your user message in the LLM Checker. Then the LLM has the same input it would receive in production.

### Session State

The conversation history is maintained for the entire session until you click "Clear Chat" or reload the page. The LLM has full access to all previous messages in the session.

This is useful for multi-turn testing but can cause unexpected behavior if you change the system prompt mid-session. The LLM has already been operating under the previous instructions for earlier turns. When evaluating a new prompt version, always clear chat first.

### Tool Calls Are Real

Tools called in the LLM Checker execute against the live system with real data. `get_candles` returns actual market data. `get_account_status` returns real account information. `place_order` places real orders.

There is no sandbox mode. The LLM Checker is not isolated from the broker or market data infrastructure. This means:
- Market data retrieved is always current and accurate
- Account data is live
- Any order execution tool that runs places a real order

### Token Counting

The token count in the metadata includes:
- System prompt tokens
- All previous messages in the conversation history
- Tool schemas for all enabled tools
- The current response

Long system prompts + many enabled tools + long conversation history = very high token counts per request. If you see unusually high costs or context length errors, consider:
- Clearing chat to reset conversation history
- Disabling tools not needed for the test
- Shortening the system prompt for testing purposes

---

## Summary: When to Use LLM Checker vs Other Tools

| Task | Recommended Tool |
|---|---|
| Draft and test a new system prompt | LLM Checker |
| Reproduce an agent's decision | LLM Checker (paste snapshot as message) |
| Check raw tool output (exact parameters) | Tool Executor |
| Observe a full agent cycle with snapshot | Agent Chat |
| Test multiple prompts rapidly | LLM Checker (clear between runs) |
| Debug tool call arguments chosen by LLM | LLM Checker (read trace) |
| Deploy a tested prompt to live agent | Agent Config |
| Monitor live agent behavior | Monitor panel |

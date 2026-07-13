[Back to UI Handbook](ui.en.md)

# Test

The `Test` area currently contains:

- [LLM Checker](ui.test.llm_checker.en.md)
- [Tool Executor](ui.test.tool_executor.en.md)

Use these tools for isolated checks before going live or when debugging a problem. They are intentionally separate from the `Agent Chat` execute workflow: where Agent Chat tests a full agent cycle end-to-end, the Test tools test individual components in isolation.

---

## When to Use the Test Tools

Use the Test section:

- **Before first deployment**: verify LLM connectivity and tool availability before enabling live agents
- **After configuration changes**: validate that a new LLM module or tool configuration works as expected
- **When debugging**: isolate whether a problem originates from the LLM, a specific tool, or the agent logic
- **When writing new prompts**: test prompt formatting and LLM response structure before embedding in a Decision Prompt profile
- **When adding new tools to a snapshot**: verify tool output format matches what your transform scripts expect

The Test tools do not trigger agent cycles, do not produce trading signals, and do not interact with the broker. They are safe to use at any time, including during live trading.

---

## LLM Checker

Use `LLM Checker` to send a raw message sequence directly to a configured LLM and inspect the response.

This is useful for:

- verifying that an LLM module is connected and responding
- testing prompt formatting before embedding it in an agent profile
- checking tool-calling behavior in isolation
- estimating token costs for a given prompt

### How LLM Checker Works

LLM Checker lets you:

1. Select an LLM module from the dropdown
2. Compose a message sequence (system message + user message)
3. Optionally define tool definitions to include in the call
4. Send the request and inspect the raw response

The response view shows:
- the raw LLM output text
- structured JSON parsing result (if the response is valid JSON)
- token usage (input, output, total)
- latency (time from request to response)
- any error messages from the LLM provider

### Typical LLM Checker Workflow

**Testing a new Decision Prompt before saving:**

1. Open LLM Checker
2. Select the LLM module you will use for trading
3. Paste your draft system prompt into the system message field
4. Paste a sample snapshot JSON into the user message field (copy from Test Snapshot in Decision Prompt)
5. Click Send
6. Verify the response is structured JSON matching your expected format
7. Check confidence score, signal direction, and reasoning fields are present
8. Check token count to estimate daily LLM cost

**Verifying LLM connectivity after configuration change:**

1. Open LLM Checker
2. Select the modified LLM module
3. Enter a simple test message ("Respond with 'OK' if you can hear me")
4. Click Send
5. If a response arrives, the module is connected

**Checking tool-calling behaviour:**

1. Open LLM Checker
2. Select your LLM module
3. Write a system prompt that instructs the LLM to use a specific tool
4. Add the tool definition in the tools panel
5. Send and verify the LLM returns a tool_call block with correct parameters

### LLM Checker and Cost Management

Each LLM call in LLM Checker consumes API credits. The token display shows the cost of each test. Keep this in mind when doing extensive prompt testing:

- Use a cheaper model (GPT-4o-mini or Claude Haiku) for initial prompt drafting
- Switch to the production model for final validation
- A typical M5 snapshot with a full analysis prompt uses 800–2000 input tokens

See [LLM Modules](ui.config.llm_modules.en.md) for model configuration.

Suggested screenshot:
- [LLM Checker](image/ui-24-llm-checker.png)

---

## Tool Executor

Use `Tool Executor` to call a specific tool directly and inspect its output.

This is useful for:

- checking that a tool is reachable and returns expected data
- testing tool parameters before embedding them in a snapshot profile
- debugging tool output that appears unexpectedly in agent runs
- verifying the data format a tool returns before writing a transform script

### How Tool Executor Works

Tool Executor lets you:

1. Select a tool from the list of available system tools
2. Enter input parameters as JSON
3. Execute the tool directly
4. Inspect the raw output

The output view shows:
- the raw tool response (JSON or text)
- execution time
- any error messages

### Typical Tool Executor Workflow

**Before adding a tool to a snapshot profile:**

1. Open Tool Executor
2. Select the tool you want to add (e.g., `get_ohlcv`, `get_atr`, `get_swing_levels`)
3. Enter the parameters you plan to use (symbol, timeframe, period, etc.)
4. Execute
5. Examine the output structure
6. Note the exact key names — these are what your transform script will access via `tool_outputs`
7. Verify the values are reasonable for the current market

**Debugging a snapshot tool that returns unexpected values:**

1. Open Tool Executor
2. Select the tool that is producing unexpected output in your agent runs
3. Enter the same parameters used in the snapshot profile
4. Execute
5. Compare the output to what appeared in the Agent Chat inspector Snapshot tab
6. If outputs differ, there may be a timing issue or parameter mismatch

**Checking account tools before enabling live trading:**

1. Open Tool Executor
2. Select `get_account_status`
3. Execute without parameters
4. Verify the account balance, equity, and free margin are correct
5. Select `get_open_positions`
6. Execute and verify any open positions are correctly reported

### Available Tool Categories

Tools available in Tool Executor cover:

- **Market data**: OHLCV candles, ATR, moving averages, swing levels
- **Account data**: balance, equity, margin, open positions
- **Order management**: pending orders, position details
- **System utilities**: current time, session status, economic calendar

See [Tools Reference](openforexai.tools.en.md) for complete tool documentation.

Suggested screenshot:
- [Tool Executor](image/ui-25-tool-executor.png)

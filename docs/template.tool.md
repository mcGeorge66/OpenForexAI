[Back to Documentation Index](./README.md)

# Tool Development Template (OpenForexAI)

This folder is a practical starting point for building new tools.

## What Is In This Folder

- `demo_minimal_tool.py`
Minimal valid tool. Shows required fields and the basic `execute()` contract.

- `demo_context_event_tool.py`
Advanced example. Shows how to:
  - read runtime context (`broker_name`, `pair`, `data_container`, `extra["llm"]`)
  - emit monitoring events
  - publish an EventBus message

- `demo_tool_test.py`
Basic unit-test patterns for tool behavior and argument validation.

- `tool_registry_manager.py`
CLI helper to register, deregister, and list system tool registrations.

## Tool Contract (Required)

Every tool must subclass `BaseTool` and implement:

1. `name: str`
Unique registry key (no duplicates).

2. `description: str`
Clear action-oriented description for LLM and UI.

3. `input_schema: dict`
JSON schema used by:
  - LLM tool manifest
  - ToolExecutor UI form rendering
  - runtime argument shaping

4. `async def execute(arguments, context) -> Any`
Runtime logic. Must return JSON-serializable output.

## Where Tools Receive Information

Inside `execute(arguments, context)`:

1. `arguments`
User/LLM provided payload according to `input_schema`.

2. `context.agent_id`
Caller identity.

3. `context.broker_name` and `context.pair`
Resolved runtime execution scope.

4. `context.data_container`
Market/history data access.

5. `context.repository`
Database repository access.

6. `context.broker`
Live broker adapter instance.

7. `context.extra`
Optional values injected by caller (example: selected LLM instance).

## Where Tools Can Send Information

1. Return value from `execute()`
Primary response back to caller.

2. `context.monitoring_bus.emit(...)`
Operational telemetry, alerts, diagnostics.

3. `context.event_bus.publish(...)`
Domain/system events for other components.

4. Repository writes via `context.repository`
Persistent state updates when appropriate.

---
## Required Integration Steps For A Real Tool

After writing the tool class, integrate all of the following:

1. Place the tool file under `openforexai/tools/<domain>/`.

2. Register it in `openforexai/tools/__init__.py`:

```python
from openforexai.tools.my_domain.my_tool import MyTool
DEFAULT_REGISTRY.register(MyTool())
```

3. Allow it in agent config (`config/system.json`):
Add the tool name under each relevant agent `tool_config.allowed_tools`.

4. Configure approval mode (`config/agent_tools.json`) if needed:
Use `direct`, `supervisor`, or `human` depending on risk.

5. Ensure runtime context requirements are satisfied:
If your tool needs broker/pair/data, validate context early and fail fast.

---
## Automated Registration Script

Use the helper script to avoid manual copy/paste errors:

### 1) Show help

```bash
python template/tool/tool_registry_manager.py
```

When called without parameters, it prints a detailed usage guide.

### 2) List currently registered tools

```bash
python template/tool/tool_registry_manager.py --list
```

### 3) List allowed domains (strict mode)

```bash
python template/tool/tool_registry_manager.py --listdomain
```
This reads current subfolders under `openforexai/tools`.

### 4) Add a custom domain (strict mode)

```bash
python template/tool/tool_registry_manager.py --adddomain research
```

This creates `openforexai/tools/research`.

### 5) Delete a custom domain (strict mode)

```bash
python template/tool/tool_registry_manager.py --deletedomain research
```

### 6) Register a tool (copy + registry wiring)

```bash
python template/tool/tool_registry_manager.py \
  --register \
  --tool-name my_tool \
  --source-file template/tool/my_tool.py \
  --class-name MyTool \
  --domain system
```

What it does:
- Copies `--source-file` to `openforexai/tools/<domain>/<tool_name>.py`
- Adds import line to `openforexai/tools/__init__.py`
- Adds `DEFAULT_REGISTRY.register(MyTool())` to `openforexai/tools/__init__.py`

### 7) Deregister a tool (registry cleanup + move file back)

```bash
python template/tool/tool_registry_manager.py --deregister --tool-name my_tool
```

What it does:
- Removes matching import/register lines from `openforexai/tools/__init__.py`
- Moves tool source file from system tools folder back into `template/tool/`
- If filename already exists, adds a timestamp suffix to avoid overwrite

### 8) Strict mode behavior

- Register mode accepts only domains that already exist as subfolders in `openforexai/tools`.
- Unknown domains are rejected with an explicit error.
- Use `--adddomain` before registering to a new domain.
- Built-in domains (`account`, `market`, `orderbook`, `system`, `trading`) cannot be deleted.

### 9) Important scope note

This script manages registry wiring and file placement.
It does not automatically add/remove tool names in each agent's `allowed_tools` list.
You should still update `config/system.json` intentionally per agent.

---
## Step-By-Step Workflow: Idea To Monitored Production

1. Problem Definition
- Define the exact user/agent problem.
- Define expected inputs, outputs, side effects, and failure modes.
- Decide if this belongs in a tool (external action/data) vs prompt logic.

2. Design
- Pick tool name (verb-oriented, stable).
- Draft `input_schema` with explicit required fields and enums/ranges.
- Define safety checks and approval mode requirements.
- Define observability events to emit (`monitoring_bus`, logs, bus messages).

3. Implementation
- Create tool class inheriting `BaseTool`.
- Implement strict validation and clear errors.
- Keep tool deterministic where possible.
- Return structured JSON (avoid free-form strings for machine-consumed results).

4. Local Static Checks
- Run syntax/type checks.
- Confirm schema and result shape are consistent.

5. Unit Testing
- Add tests for:
  - happy path
  - invalid arguments
  - missing context dependencies
  - side effects (if any)

Example:

```bash
pytest template/tool/demo_tool_test.py -q
```

6. Registry And Config Wiring
- Register tool in `DEFAULT_REGISTRY` (manual or via `tool_registry_manager.py`).
- Add tool to target agents in `config/system.json`.
- Set approval behavior in `config/agent_tools.json` where required.

7. Controlled Functional Testing
- Start system in a safe environment.
- Use UI: `Test -> ToolExecutor`.
- Select Broker Adapter and LLM when needed.
- Execute with known inputs and verify deterministic output.

8. Safety Review
- Verify tool cannot perform unsafe actions without approval.
- Validate exception paths and failure transparency.
- Confirm secrets are never returned in tool output.

9. Staged Rollout
- Enable for limited agents first.
- Monitor call volume, errors, latency, and downstream effects.
- Keep rollback simple (remove from `allowed_tools` and/or registry).

10. Monitored Production Operation
- Watch monitoring events continuously.
- Track tool success/error rates and critical event frequency.
- Add alerts for repeated failures or risky patterns.
- Iterate schema and behavior based on real usage data.

>[!NOTE]
>## Practical Rules For Reliable Tools
>
>1. Validate early, fail clearly.
>2. Return machine-friendly JSON, not prose.
>3. Keep side effects explicit and observable.
>4. Emit monitoring events for important actions/failures.
>5. Make unsafe actions approval-gated.
>6. Prefer narrow, single-purpose tools over monolithic tools.
>This deletes `openforexai/tools/research` if it has no `.py` files.

---

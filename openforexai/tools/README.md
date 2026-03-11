# openforexai/tools — LLM Tool Plugin System

The tool system enables agents to call external functions during their LLM decision cycle. Tools provide access to market data, indicators, broker operations, and system utilities.

## Structure

```
tools/
├── base.py              # BaseTool ABC + ToolContext dataclass
├── registry.py          # ToolRegistry — stores and retrieves tools
├── dispatcher.py        # ToolDispatcher — executes tools with gating
├── config_loader.py     # Loads agent_tools.json5 per-agent config
├── __init__.py          # DEFAULT_REGISTRY with all built-in tools
├── account/
│   ├── get_account_status.py
│   └── get_open_positions.py
├── market/
│   ├── get_candles.py
│   └── calculate_indicator.py
├── orderbook/
│   └── get_order_book.py
├── trading/
│   ├── place_order.py
│   └── close_position.py
└── system/
    ├── alarm.py
    └── trigger_sync.py
```

---

## Built-in Tools

| Tool Name | Module | Description |
|---|---|---|
| `get_candles` | `market/` | Retrieve OHLCV candle bars for any timeframe |
| `calculate_indicator` | `market/` | Compute technical indicators (RSI, EMA, ATR, …) |
| `get_order_book` | `orderbook/` | Current pending orders and their state |
| `get_account_status` | `account/` | Balance, equity, margin, open positions count |
| `get_open_positions` | `account/` | Detailed list of all open positions with P&L |
| `place_order` | `trading/` | Submit a market/limit/stop order |
| `close_position` | `trading/` | Close an open position with reasoning |
| `raise_alarm` | `system/` | Emit a system alarm event |
| `trigger_sync` | `system/` | Trigger order book synchronisation |

---

## `base.py` — BaseTool and ToolContext

### ToolContext

Passed to every tool execution. Provides access to all live system components:

```python
@dataclass
class ToolContext:
    agent_id: str
    broker_name: str | None    # e.g. "OAPR1"
    pair: str | None           # e.g. "EURUSD"
    data_container: DataContainer
    repository: AbstractRepository
    broker: AbstractBroker
    monitoring_bus: AbstractMonitoringBus
    event_bus: EventBus
    extra: dict                # extension point for custom tools
```

### BaseTool Interface

```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does — shown to the LLM."
    input_schema = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
            "param2": {"type": "integer"}
        },
        "required": ["param1"]
    }

    async def execute(self, arguments: dict, context: ToolContext) -> Any:
        # Return any JSON-serialisable value
        # Raise any exception to signal an error
        result = do_something(arguments["param1"])
        return {"result": result}
```

Return values are automatically JSON-serialised. Exceptions are caught by `ToolDispatcher` and returned as `{"error": "..."}` with `is_error=True`.

---

## `registry.py` — ToolRegistry

Stores tool instances and provides them to the `ToolDispatcher`:

```python
registry = ToolRegistry()
registry.register(GetCandlesTool())
registry.register(CalculateIndicatorTool())

tool = registry.get("get_candles")
all_tools = registry.list_tools()
specs = registry.get_specs()   # list of ToolSpec dicts for LLM
```

The `DEFAULT_REGISTRY` in `__init__.py` contains all built-in tools and is used by bootstrap.

---

## `dispatcher.py` — ToolDispatcher

The dispatcher sits between the agent's LLM loop and the actual tool implementations. It handles three cross-cutting concerns:

### 1. Approval Gating

Each tool can require approval before execution:

| Mode | Behaviour |
|---|---|
| `"direct"` | Execute immediately (default) |
| `"supervisor"` | Publish `SIGNAL_GENERATED`, wait for `SIGNAL_APPROVED`/`SIGNAL_REJECTED` (15s timeout) |
| `"human"` | Block until Management API approval (planned, not yet implemented) |

Approval modes are configured per-tool per-agent in `config/RunTime/agent_tools.json5`.

### 2. Context Budget Tiers

As the conversation grows, the LLM token budget fills up. The dispatcher automatically restricts available tools based on how full the budget is:

```
0% – 84% used  →  "all" tier:      all configured tools available
85% – 99% used →  "safety" tier:   only raise_alarm
```

(Thresholds and tier names are configured per-agent in `system.json5 → tool_config.context_tiers`)

This prevents the LLM from starting expensive multi-step operations when it's running out of context.

### 3. Allowed-Tool Filtering

Each agent has an `allowed_tools` list in its config. The dispatcher silently filters out any tool not on the list before presenting the tool manifest to the LLM.

### 4. Monitoring Integration

Every tool invocation emits two monitoring events:
- `TOOL_CALL_STARTED` (with tool name and arguments)
- `TOOL_CALL_COMPLETED` (with result) or `TOOL_CALL_FAILED` (with error)

These are visible in `tools/monitor.py` with `--tools` filter.

### Usage

```python
dispatcher = ToolDispatcher(
    registry=tool_registry,
    context=ToolContext(agent_id=..., broker_name=..., ...),
    agent_tool_config=config["tool_config"],
)

# Get tool specs for LLM (filtered by allowed_tools + current context tier)
specs = dispatcher.get_specs(input_tokens=1200, max_tokens=4096)

# Execute tool calls from LLM response
results = await dispatcher.execute_tool_calls(tool_calls, input_tokens, max_tokens)
# Returns list[ToolResult]
```

---

## `config_loader.py` — Tool Configuration

Loads `config/RunTime/agent_tools.json5` for per-agent tool customisation. Supports:
- Per-agent approval mode overrides
- Per-tool approval mode overrides
- Context tier threshold and tool-set definitions
- Tool tags (grouping tools for tier sets)

---

## Adding a New Tool

1. Create `tools/<category>/my_tool.py`:

```python
from openforexai.tools.base import BaseTool, ToolContext

class MyNewTool(BaseTool):
    name = "my_new_tool"
    description = "Brief description for the LLM."
    input_schema = {
        "type": "object",
        "properties": {
            "value": {"type": "string", "description": "Input value"}
        },
        "required": ["value"]
    }

    async def execute(self, arguments: dict, context: ToolContext):
        return {"result": f"processed: {arguments['value']}"}
```

2. Register in `tools/__init__.py`:

```python
from openforexai.tools.market.my_tool import MyNewTool
DEFAULT_REGISTRY.register(MyNewTool())
```

3. Add to an agent's `allowed_tools` in `config/system.json5`.

The tool will automatically appear in the LLM's tool manifest for that agent.



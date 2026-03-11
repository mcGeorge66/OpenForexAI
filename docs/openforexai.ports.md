# openforexai/ports — Abstract Interfaces (Hexagonal Ports)

Abstract base classes that define the contracts for all external integrations. No implementation code lives here — only interfaces. The concrete implementations are in `openforexai/adapters/`.

This is the core of the hexagonal (ports & adapters) architecture: business logic depends only on these abstract ports, never on the concrete adapters.

## Files

| File | Abstract Class | Implemented by |
|---|---|---|
| `llm.py` | `AbstractLLMProvider` | `adapters/llm/` |
| `broker.py` | `AbstractBroker` | `adapters/brokers/` |
| `database.py` | `AbstractRepository` | `adapters/database/` |
| `data_container.py` | `AbstractDataContainer` | `adapters/database/` |
| `data_feed.py` | `AbstractDataFeed` | `adapters/data/` |
| `monitoring.py` | `AbstractMonitoringBus` | `monitoring/bus.py` |

---

## `llm.py` — AbstractLLMProvider

The LLM adapter interface. All LLM providers (Anthropic, OpenAI, Azure) implement this.

### Data Classes

```python
@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    raw: dict

@dataclass
class ToolCall:
    id: str             # provider-assigned call ID
    name: str           # tool name
    arguments: dict     # parsed JSON arguments

@dataclass
class ToolResult:
    tool_call_id: str   # matches ToolCall.id
    name: str
    content: str        # JSON-serialised result
    is_error: bool = False

@dataclass
class LLMResponseWithTools:
    content: str | None
    tool_calls: list[ToolCall]
    stop_reason: str    # "end_turn" | "tool_use" | "stop" | "max_tokens"
    model: str
    input_tokens: int
    output_tokens: int
    raw: dict

    @property
    def wants_tools(self) -> bool:
        # True when stop_reason == "tool_use" and tool_calls is non-empty
```

### Canonical ToolSpec Format

All LLM adapters accept tools in the Anthropic-style `input_schema` format and convert internally to their provider's wire format:

```python
ToolSpec = {
    "name": "calculate_indicator",
    "description": "Compute a technical indicator.",
    "input_schema": {
        "type": "object",
        "properties": {
            "indicator": {"type": "string"},
            "period": {"type": "integer"},
            "pair": {"type": "string"}
        },
        "required": ["indicator", "period", "pair"]
    }
}
```

### Required Methods

```python
class AbstractLLMProvider(ABC):

    @classmethod
    @abstractmethod
    def from_config(cls, cfg: dict) -> AbstractLLMProvider:
        # Factory method — only sanctioned way to create an adapter instance
        ...

    @abstractmethod
    async def complete(
        self, system_prompt, user_message, temperature, max_tokens
    ) -> LLMResponse:
        # Plain (non-tool) text completion
        ...

    @abstractmethod
    async def complete_structured(
        self, system_prompt, user_message, response_schema
    ) -> dict:
        # Pydantic-typed structured output
        ...

    @abstractmethod
    async def complete_with_tools(
        self, system_prompt, messages, tools, temperature, max_tokens
    ) -> LLMResponseWithTools:
        # Single turn of the tool-use loop
        ...

    @property
    @abstractmethod
    def model_id(self) -> str: ...
```

### Tool-Use Loop Protocol

```
Agent calls complete_with_tools(system_prompt, messages, tools)
    │
    ├── stop_reason == "end_turn" → final answer, exit loop
    │
    └── stop_reason == "tool_use":
          1. Agent executes tool_calls via ToolDispatcher
          2. Agent appends assistant turn + tool_result turn to messages
          3. Agent calls complete_with_tools() again
          4. Repeat until end_turn or max_tool_turns
```

---

## `broker.py` — AbstractBroker

The broker adapter interface. All broker implementations (OANDA, MT5) implement this.

### Key Methods

```python
class AbstractBroker(ABC):

    @property
    @abstractmethod
    def short_name(self) -> str:
        # e.g. "OAPR1" — used for DB table naming and agent ID prefix
        ...

    @abstractmethod
    async def get_candles(
        self, pair: str, timeframe: str, count: int
    ) -> list[Candle]:
        # Fetch historical candles directly from broker API
        ...

    @abstractmethod
    async def place_order(self, order: TradeOrder) -> TradeResult:
        ...

    @abstractmethod
    async def close_position(
        self, entry_id: str, close_reason: CloseReason
    ) -> TradeResult:
        ...

    @abstractmethod
    async def get_account_status(self) -> AccountStatus:
        ...

    @abstractmethod
    async def get_open_positions(self) -> list[Position]:
        ...

    @abstractmethod
    async def get_order_book(self, pair: str) -> list[OrderBookEntry]:
        ...
```

---

## `database.py` — AbstractRepository

The database adapter interface for all persistent storage.

### Key Methods

```python
class AbstractRepository(ABC):

    @abstractmethod
    async def save_candles(
        self, broker_name: str, pair: str, candles: list[Candle]
    ) -> None: ...

    @abstractmethod
    async def get_candles(
        self, broker_name: str, pair: str, timeframe: str,
        limit: int, before: datetime | None
    ) -> list[Candle]: ...

    @abstractmethod
    async def save_order_book_entry(self, entry: OrderBookEntry) -> None: ...

    @abstractmethod
    async def update_order_book_entry(self, entry: OrderBookEntry) -> None: ...

    @abstractmethod
    async def get_order_book_entries(
        self, broker_name: str, status: TradeStatus | None
    ) -> list[OrderBookEntry]: ...

    @abstractmethod
    async def save_agent_decision(self, decision: AgentDecision) -> None: ...

    @abstractmethod
    async def get_agent_decisions(
        self, agent_id: str, limit: int
    ) -> list[AgentDecision]: ...
```

---

## `monitoring.py` — AbstractMonitoringBus

```python
class AbstractMonitoringBus(ABC):

    @abstractmethod
    def emit(self, event: MonitoringEvent) -> None:
        # Synchronous, fire-and-forget, never raises
        ...

    @abstractmethod
    def subscribe(self, maxsize: int) -> asyncio.Queue[MonitoringEvent]:
        ...

    @abstractmethod
    def recent_events(
        self, since: datetime | None, limit: int
    ) -> list[MonitoringEvent]:
        ...
```

---

## Why Hexagonal Architecture?

| Benefit | Example |
|---|---|
| Swap LLM providers | Add `adapters/llm/gemini.py`, no agent code changes |
| Swap database | Set `OPENFOREXAI_DB_BACKEND=postgresql`, no business logic changes |
| Test without real broker | Inject a `MockBroker` in tests — agents don't know the difference |
| Add broker | Implement `AbstractBroker`, register in PluginRegistry |

The rule: **business logic (agents, tools, data analysis) imports only from `ports/`. Adapters import from `ports/` too — never the reverse.**


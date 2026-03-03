# adapters/llm — LLM Provider Adapters

Concrete implementations of `AbstractLLMProvider` for all supported LLM services. Each adapter translates the system's internal canonical format to the provider's specific API format.

## Files

| File | Provider | API |
|---|---|---|
| `__init__.py` | — | Self-registration of all adapters |
| `base.py` | — | Shared `llm_retry` decorator |
| `anthropic.py` | Anthropic Claude | Anthropic Python SDK |
| `openai.py` | OpenAI GPT | OpenAI Python SDK |
| `azure.py` | Azure OpenAI | Azure OpenAI (via OpenAI SDK) |

---

## Self-Registration

All adapters register at import time:

```python
# adapters/llm/__init__.py
PluginRegistry.register_llm_provider("anthropic",    AnthropicLLMProvider)
PluginRegistry.register_llm_provider("openai",       OpenAILLMProvider)
PluginRegistry.register_llm_provider("azure_openai", AzureOpenAILLMProvider)
```

---

## `base.py` — Shared Infrastructure

### `llm_retry` Decorator

Applied automatically to all `complete*` methods. Handles:
- API rate limits (429) — exponential backoff
- Service unavailable (503) — retry after delay
- Connection timeouts — retry immediately
- Non-retryable errors (401, 400, invalid request) — fail fast

```python
@llm_retry
async def complete_with_tools(self, ...):
    ...
```

Default: 3 attempts, 2s base delay, 60s max delay.

---

## `anthropic.py` — Anthropic Claude

Uses the official `anthropic` Python SDK.

### Tool Format

Anthropic natively uses `input_schema` — no conversion needed. The canonical internal format is Anthropic-style, so this adapter passes tools through as-is.

### Message Format

```python
# Anthropic native format
messages = [
    {"role": "user",      "content": "What is the EURUSD trend?"},
    {"role": "assistant", "content": [
        {"type": "text",     "text": "Let me check the candles."},
        {"type": "tool_use", "id": "...", "name": "get_candles", "input": {...}}
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "...", "content": "..."}
    ]}
]
```

### Config Keys (`config/modules/llm/anthropic_claude.json`)

```json
{
  "adapter": "anthropic",
  "api_key": "${ANTHROPIC_API_KEY}",
  "model": "${ANTHROPIC_MODEL:-claude-opus-4-5}"
}
```

---

## `openai.py` — OpenAI GPT

Uses the official `openai` Python SDK.

### Tool Format Conversion

Internal `input_schema` → OpenAI `function` format:

```python
# Internal (canonical)
{"name": "get_candles", "input_schema": {"type": "object", "properties": {...}}}

# OpenAI wire format
{"type": "function", "function": {
    "name": "get_candles",
    "parameters": {"type": "object", "properties": {...}}
}}
```

### Message Format

```python
# OpenAI native format
messages = [
    {"role": "user",       "content": "What is the EURUSD trend?"},
    {"role": "assistant",  "content": None, "tool_calls": [
        {"id": "...", "type": "function", "function": {"name": "get_candles", "arguments": "..."}}
    ]},
    {"role": "tool", "tool_call_id": "...", "content": "..."}
]
```

### Config Keys

```json
{
  "adapter": "openai",
  "api_key": "${OPENAI_API_KEY}",
  "model": "${OPENAI_MODEL:-gpt-4o}"
}
```

---

## `azure.py` — Azure OpenAI

Identical protocol to OpenAI but connects to an Azure-hosted deployment.

### Config Keys

```json
{
  "adapter": "azure_openai",
  "api_key": "${AZURE_OPENAI_API_KEY}",
  "endpoint": "${AZURE_OPENAI_ENDPOINT}",
  "deployment": "${AZURE_OPENAI_DEPLOYMENT:-gpt-4o}",
  "api_version": "${AZURE_OPENAI_API_VERSION:-2024-02-01}"
}
```

`deployment` is the name of your Azure OpenAI deployment (not the model name — those are set in Azure Portal).

---

## Adding a New LLM Provider

1. Create `adapters/llm/myprovider.py`:

```python
from openforexai.ports.llm import AbstractLLMProvider, LLMResponseWithTools, ...
from openforexai.adapters.llm.base import llm_retry

class MyLLMProvider(AbstractLLMProvider):

    @classmethod
    def from_config(cls, cfg: dict) -> "MyLLMProvider":
        return cls(
            api_key=cfg["api_key"],
            model=cfg.get("model", "my-default-model"),
        )

    @llm_retry
    async def complete_with_tools(
        self, system_prompt, messages, tools, temperature, max_tokens
    ) -> LLMResponseWithTools:
        # Convert tools from input_schema format to provider format
        # Call provider API
        # Convert response back to LLMResponseWithTools
        ...

    @property
    def model_id(self) -> str:
        return self._model
```

2. Register in `adapters/llm/__init__.py`:
```python
PluginRegistry.register_llm_provider("myprovider", MyLLMProvider)
```

3. Create `config/modules/llm/myprovider.json` and reference in `config/system.json`.

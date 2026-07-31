[Back to Documentation Index](README.md)

# adapters/llm — LLM Provider Adapters

Concrete implementations of `AbstractLLMProvider` for all supported LLM services. Each adapter translates the system's internal canonical format to the provider's specific API format.

## Files

| File | Provider | API |
|---|---|---|
| `__init__.py` | — | Self-registration of all adapters |
| `base.py` | — | Shared `llm_retry` decorator |
| `anthropic.py` | Anthropic Claude | Anthropic Python SDK |
| `openai.py` | OpenAI, Azure AI Foundry (v1), any OpenAI-compatible API | OpenAI Python SDK (`base_url` override) |
| `lmstudio.py` | LM Studio (local) | Subclasses `openai.py` with a local default `base_url` |
| `ollama.py` | Ollama (local) | Subclasses `openai.py` with a local default `base_url` |

---

## Self-Registration

All adapters register at import time:

```python
# adapters/llm/__init__.py
PluginRegistry.register_llm_provider("anthropic", AnthropicLLMProvider)
PluginRegistry.register_llm_provider("openai",    OpenAILLMProvider)
PluginRegistry.register_llm_provider("lmstudio",  LMStudioLLMProvider)
PluginRegistry.register_llm_provider("ollama",    OllamaLLMProvider)
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

### Config Keys (`config/modules/llm/anthropic_claude.json5`)

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

There is no separate Azure adapter. Azure AI Foundry's `/openai/v1` API is fully
OpenAI-compatible (no `api-version` query param, no `AzureOpenAI` SDK client) —
point `base_url` at your resource and use the deployment name as `model`:

```json
{
  "adapter": "openai",
  "api_key": "${AZURE_API_KEY}",
  "base_url": "https://<resource>.services.ai.azure.com/openai/v1",
  "model": "${AZURE_DEPLOYMENT}",
  "reasoning_effort": "medium"
}
```

Note: some models (confirmed for GPT-5-family Azure deployments) reject function
tools combined with `reasoning_effort` on `/chat/completions` — the adapter drops
`reasoning_effort` automatically whenever tools are present in the request rather
than failing, since tool-calling is core to the agent loop.

Optional keys shared by every provider on this adapter (OpenAI, Azure, LM Studio,
Ollama): `base_url`, `timeout_seconds` (default 30), `sdk_max_retries` (default 0),
`reasoning_effort`, `verbosity`, `transcript_enabled` + `transcript_path` (writes a
dated, size-capped forensic log of every request/response).

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

3. Create `config/modules/llm/myprovider.json5` and reference in `config/system.json5`.


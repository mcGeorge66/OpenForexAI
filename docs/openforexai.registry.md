# openforexai/registry — Component Registry

Two registries that together manage all pluggable components: `PluginRegistry` for class-level registration at import time, and `RuntimeRegistry` for live instances created by `bootstrap.py`.

## Files

| File | Purpose |
|---|---|
| `plugin_registry.py` | Class-level registry — adapters self-register at import |
| `runtime_registry.py` | Instance-level registry — live adapters created by bootstrap |

---

## `plugin_registry.py` — PluginRegistry

A class-only registry (no instance needed). Adapters register themselves at **import time** via their package `__init__.py`.

### How Self-Registration Works

```python
# openforexai/adapters/llm/__init__.py
from openforexai.registry.plugin_registry import PluginRegistry
from openforexai.adapters.llm.anthropic import AnthropicLLMProvider

PluginRegistry.register_llm_provider("anthropic", AnthropicLLMProvider)
```

When `bootstrap.py` imports `openforexai.adapters.llm`, this runs automatically. No explicit registration call is needed from bootstrap code.

### Registry Categories

```python
PluginRegistry.register_broker("oanda", OANDABroker)
PluginRegistry.get_broker("oanda")          # → OANDABroker class
PluginRegistry.list_brokers()               # → ["oanda", "mt5"]

PluginRegistry.register_llm_provider("anthropic", AnthropicLLMProvider)
PluginRegistry.get_llm_provider("anthropic")
PluginRegistry.list_llm_providers()

PluginRegistry.register_repository("sqlite", SQLiteRepository)
PluginRegistry.get_repository("sqlite")
PluginRegistry.list_repositories()

# DataContainer (preferred alias for repository)
PluginRegistry.register_data_container("sqlite", SQLiteDataContainer)
PluginRegistry.get_data_container("sqlite")
```

Note: `_data_containers` and `_repositories` share the same internal dict — `AbstractDataContainer IS-A AbstractRepository`.

### Error Handling

`get_broker("unknown")` raises `ValueError` with a list of registered names, making misconfiguration immediately obvious.

---

## `runtime_registry.py` — RuntimeRegistry

Holds live adapter **instances** created during bootstrap. Unlike `PluginRegistry` (which holds classes), `RuntimeRegistry` holds the actual connected objects.

```python
RuntimeRegistry.set_llm("azure_openai", azure_llm_instance)
RuntimeRegistry.get_llm("azure_openai")          # → live AzureOpenAILLMProvider

RuntimeRegistry.set_broker("oanda", oanda_instance)
RuntimeRegistry.get_broker("oanda")              # → live OANDABroker

RuntimeRegistry.list_llms()                      # → ["azure_openai"]
RuntimeRegistry.list_brokers()                   # → ["oanda"]
```

### Bootstrap Flow

```
bootstrap.py:
    1. import adapters.llm      → PluginRegistry gets AnthropicLLMProvider, OpenAILLMProvider, ...
    2. import adapters.brokers  → PluginRegistry gets OANDABroker, MT5Broker
    3. import adapters.database → PluginRegistry gets SQLiteRepository

    4. For each LLM module in system.json5:
          klass = PluginRegistry.get_llm_provider("azure_openai")
          instance = klass.from_config(llm_cfg)
          RuntimeRegistry.set_llm("azure_openai", instance)

    5. For each broker module in system.json5:
          klass = PluginRegistry.get_broker("oanda")
          instance = klass.from_config(broker_cfg)
          RuntimeRegistry.set_broker("oanda", instance)

    6. When creating agents:
          agent's LLM = RuntimeRegistry.get_llm(agent_config["llm"])
          agent's broker = RuntimeRegistry.get_broker(agent_config["broker"])
```

### Thread Safety

`RuntimeRegistry` uses plain dict operations (GIL-protected). Bootstrap happens before the async task group starts, so no concurrent write contention occurs.

---

## Adding a New Adapter

### New LLM Provider

1. Create `adapters/llm/myprovider.py`:
   ```python
   class MyLLMProvider(AbstractLLMProvider):
       @classmethod
       def from_config(cls, cfg):
           return cls(api_key=cfg["api_key"], model=cfg["model"])
       ...
   ```

2. Register in `adapters/llm/__init__.py`:
   ```python
   PluginRegistry.register_llm_provider("myprovider", MyLLMProvider)
   ```

3. Create `config/modules/llm/myprovider.json5`:
   ```json
   {"adapter": "myprovider", "api_key": "${MY_API_KEY}", "model": "my-model"}
   ```

4. Reference in `config/system.json5`:
   ```json
   "modules": {"llm": {"myprovider": "config/modules/llm/myprovider.json5"}}
   ```

The same pattern applies for brokers and database backends.


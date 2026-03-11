# LLM Adapter Templates

This folder contains templates and helper scripts for LLM provider development.

## Files

- `demo_llm_provider.py`: Minimal `AbstractLLMProvider` implementation.
- `demo_llm_test.py`: Basic test patterns for text + tool-use flow.
- `llm_adapter_manager.py`: Register/deregister/list LLM providers in the system.

## Adapter Contract

An LLM adapter must implement `AbstractLLMProvider`:
- `from_config(cfg)`
- `complete(...)`
- `complete_structured(...)`
- `complete_with_tools(...)`
- `model_id` property

Return types must use:
- `LLMResponse`
- `LLMResponseWithTools`
- `ToolCall` for tool-use turns

## Information Flow

Inputs:
1. Module config from `config/modules/llm/*.json`
2. Prompts and message history from agents
3. Canonical tool specs from tool dispatcher

Outputs:
1. Completion text (`LLMResponse.content`)
2. Structured responses for schema-based calls
3. Tool-call requests (`LLMResponseWithTools.tool_calls`)
4. Token/model metadata for observability and cost tracking

## Adapter Manager Script

### Help (no parameters)
```bash
python template/llm/llm_adapter_manager.py
```

### List registered LLM providers
```bash
python template/llm/llm_adapter_manager.py --list
```

### Register provider
```bash
python template/llm/llm_adapter_manager.py \
  --register \
  --name demo_llm \
  --source-file template/llm/demo_llm_provider.py \
  --class-name DemoLLMProvider
```

### Deregister provider
```bash
python template/llm/llm_adapter_manager.py --deregister --name demo_llm
```

## Development Workflow (Idea -> Production)

1. Define scope:
- model family, latency/cost constraints, tool-calling capability, context limits.

2. Design:
- map provider API to canonical response objects.
- define retry/backoff and timeout behavior.

3. Implement:
- start from `demo_llm_provider.py`.
- implement robust error mapping and token accounting.

4. Test:
```bash
pytest template/llm/demo_llm_test.py -q
```
- add tests for tool-use loops and malformed provider payloads.

5. Register and configure:
- register provider using manager script.
- create `config/modules/llm/<name>.json`.
- reference in `config/system.json -> modules.llm`.

6. Controlled rollout:
- enable for one low-risk agent first.
- watch monitoring and failure patterns.

7. Monitored production:
- track latency, timeout rates, tool-call correctness, and token cost.
- keep rollback path (switch module key) immediate.


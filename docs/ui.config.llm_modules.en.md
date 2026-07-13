[Back to Config](ui.config.en.md)

# LLM Modules

LLM Modules is a direct editor for the configuration files of individual LLM adapter modules. Each module has its own file that can be selected and edited here. This page is intended for operators who need to adjust LLM adapter parameters directly — model IDs, API keys, endpoints, temperature defaults, token limits, timeout settings, and retry behavior.

---

## Table of Contents

1. [LLM Architecture Overview](#llm-architecture-overview)
2. [Interface](#interface)
3. [Save Behavior](#save-behavior)
4. [How LLM Modules Are Registered](#how-llm-modules-are-registered)
5. [Module Configuration Fields](#module-configuration-fields)
6. [Azure OpenAI Configuration](#azure-openai-configuration)
7. [Anthropic Claude Configuration](#anthropic-claude-configuration)
8. [OpenAI Configuration](#openai-configuration)
9. [Timeout and Retry Settings](#timeout-and-retry-settings)
10. [Multiple LLM Modules](#multiple-llm-modules)
11. [Security: API Key Handling](#security-api-key-handling)
12. [Typical Workflow](#typical-workflow)
13. [Testing LLM Module Changes](#testing-llm-module-changes)
14. [Troubleshooting LLM Issues](#troubleshooting-llm-issues)

---

## LLM Architecture Overview

Since OpenForexAI v0.7, all LLM communication flows through the Event Bus. This is a significant architectural difference from older versions where agents called LLMs directly.

### Event Bus LLM Flow

```
AA Agent
  → publishes llm_request to bus
  → Bus routes via llm_request routing rule → LLM Service
  → LLM Service (e.g. azure_azmin) calls provider API
  → Provider API returns response (may take 70–80 seconds for complex prompts)
  → LLM Service publishes llm_response to bus
  → Bus routes llm_response back to originating agent
  → Agent processes response
```

### Bus Registration

Each LLM module registers on the bus under a unique member ID. For a module named `azure_azmin`, the bus member ID is `llm:azure_azmin`. Routing rules in Event Routing must target this ID.

### Concurrency

Multiple LLM requests are handled simultaneously. Each request gets its own async task inside the LLM service. A slow request from one agent does not block requests from other agents.

### Timeout

The default timeout for LLM requests is 180 seconds. Complex prompts with large snapshots typically take 70–80 seconds. The 180-second limit provides a safety buffer. If a provider is slow or unreachable, the agent receives a timeout error and logs it, then waits for the next trigger cycle.

### Agent-to-LLM Assignment

Each agent specifies which LLM module to use via the `llm` field in its Agent Config entry. Different agents can use different LLM modules simultaneously:
- EURUSD agent → `azure_azmin` (fast, cost-efficient)
- GBPUSD agent → `azure_premium` (higher-quality model)
- Test agent → `anthropic_claude` (alternative provider for comparison)

---

## Interface

### Header Bar

| Element | Function |
|---------|----------|
| **Module selector** | Dropdown listing all LLM modules registered in `modules.llm` of `system.json5` |
| **File path** | Full path to the selected module's config file |
| **Refresh** | Reload the current file version from disk (only active when a module is selected) |
| **Save** | Validate and write the file (only active when a module is selected) |
| **Position** | Current cursor position as line:column |

### Module Selector

The dropdown is populated from the `modules.llm` array in `system.json5`. Each entry in that array is a file path; the dropdown shows the filename portion (e.g. `azure_azmin.json5`).

After selecting a module, the editor loads its file content automatically.

### Line Numbers

Displayed on the left side of the editor. Sync-scrolls with the text.

### Editor Textarea

Free-text JSON5 editing. Syntax highlighting:

| Color | Applied to |
|-------|-----------|
| Cyan | Object keys |
| Green | String values |
| Amber | Boolean values |
| Gray | `null` values |
| Purple | Numeric values |

### Status Messages

- **"Saved."** — File successfully written
- **Error message** — Parse error or validation failure; file not written

---

## Save Behavior

1. Content is parsed as JSON5
2. Top-level result must be a JSON object
3. On error: error message shown, file not written
4. On success: file written to disk

The LLM module picks up new configuration at the next system start or module reload. Changes to `api_key`, `deployment`, or `model` require a system restart to take effect. Changes to `default_temperature` and `default_max_tokens` take effect on the next LLM call after reload.

---

## How LLM Modules Are Registered

The path chain for an LLM module:

1. `config/system.json5` has `modules.llm: ["config/llm/azure_azmin.json5"]`
2. On startup, the system reads this path and loads `azure_azmin.json5`
3. The module is instantiated as an LLM service and registered on the bus as `llm:azure_azmin`
4. A routing rule in Event Routing sends `llm_request` events to `llm:azure_azmin`
5. Agents whose `llm` field is `azure_azmin` send their LLM requests to this service

To add a new LLM module:
1. Create the config file (e.g. `config/llm/new_provider.json5`)
2. Add its path to `modules.llm` in `system.json5`
3. Add a routing rule that routes `llm_request` to `llm:new_provider` (or specific agents to this LLM)
4. Restart the system

---

## Module Configuration Fields

All LLM module config files share common fields regardless of provider:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `adapter` | string | yes | Provider adapter type: `azure_openai`, `anthropic`, `openai` |
| `name` | string | yes | Module name (must match the filename stem, e.g. `azure_azmin`) |
| `default_temperature` | float | no | Default sampling temperature (0.0–2.0). Per-agent overrides take precedence. |
| `default_max_tokens` | integer | no | Default maximum output tokens. |
| `timeout` | integer | no | Request timeout in seconds. Default: 180. |
| `retry_attempts` | integer | no | Number of retry attempts on transient errors. Default: 2. |
| `retry_delay_seconds` | float | no | Delay between retries in seconds. Default: 2.0. |
| `prompt_caching` | boolean | no | Enable provider-side prompt caching (Anthropic only). Default: false. |

Provider-specific fields are described in the sections below.

---

## Azure OpenAI Configuration

```json5
{
  adapter: "azure_openai",
  name: "azure_azmin",
  endpoint: "https://your-resource.openai.azure.com/",
  api_key_env: "AZURE_OPENAI_API_KEY",
  deployment: "gpt-4o-mini",
  api_version: "2024-08-01-preview",
  default_temperature: 0.3,
  default_max_tokens: 2000,
  timeout: 180,
  retry_attempts: 2,
  retry_delay_seconds: 3.0,
  // Optional: reasoning effort for o-series models
  // reasoning_effort: "medium",
}
```

### Azure-Specific Fields

| Field | Description |
|-------|-------------|
| `endpoint` | Your Azure OpenAI resource endpoint URL. Ends with `/`. |
| `api_key_env` | Name of the environment variable containing the API key. Recommended over `api_key`. |
| `api_key` | Plaintext API key. Use only when environment variables are not available. |
| `deployment` | The deployment name created in Azure OpenAI Studio (not the model name). |
| `api_version` | Azure API version string. Use the most recent stable version. |
| `reasoning_effort` | For o-series reasoning models only: `"low"`, `"medium"`, `"high"`. Controls depth of chain-of-thought. |

### Common Azure Deployments

| Model | Deployment Example | Use Case |
|-------|-------------------|----------|
| GPT-4o mini | `gpt-4o-mini` | Fast, cost-efficient, suitable for most analysis |
| GPT-4o | `gpt-4o` | Higher quality, slower, more expensive |
| o3-mini | `o3-mini` | Reasoning model, very capable but higher latency |
| o4-mini | `o4-mini` | Reasoning model with improved speed |

For standard forex analysis, `gpt-4o-mini` or `gpt-4o` provide good cost/quality balance. Reasoning models (o-series) can improve signal quality but increase latency to 120–180 seconds per call.

---

## Anthropic Claude Configuration

```json5
{
  adapter: "anthropic",
  name: "anthropic_claude",
  api_key_env: "ANTHROPIC_API_KEY",
  model: "claude-sonnet-4-6",
  default_temperature: 0.3,
  default_max_tokens: 2000,
  timeout: 180,
  retry_attempts: 2,
  retry_delay_seconds: 3.0,
  prompt_caching: true,
  // Optional: extended thinking
  // thinking_budget_tokens: 5000,
}
```

### Anthropic-Specific Fields

| Field | Description |
|-------|-------------|
| `api_key_env` | Environment variable name for the Anthropic API key. |
| `api_key` | Plaintext API key (not recommended). |
| `model` | Model ID. Examples: `claude-opus-4-5`, `claude-sonnet-4-6`, `claude-haiku-4-5`. |
| `prompt_caching` | When `true`, enables Anthropic's prompt caching feature. Reduces costs and latency for repeated system prompts. Recommended: `true`. |
| `thinking_budget_tokens` | For extended thinking: maximum tokens allocated to chain-of-thought. Values: 1024–16000+. Increases latency significantly. |

### Anthropic Model Selection

| Model | Speed | Quality | Cost |
|-------|-------|---------|------|
| claude-haiku-4-5 | Fastest | Good | Lowest |
| claude-sonnet-4-6 | Fast | Very good | Medium |
| claude-opus-4-5 | Slowest | Best | Highest |

For forex analysis, `claude-sonnet-4-6` provides an excellent balance. Enable `prompt_caching: true` for significant cost reduction when system prompts are large and stable.

---

## OpenAI Configuration

```json5
{
  adapter: "openai",
  name: "openai_gpt4",
  api_key_env: "OPENAI_API_KEY",
  model: "gpt-4o",
  default_temperature: 0.3,
  default_max_tokens: 2000,
  timeout: 180,
  retry_attempts: 2,
  retry_delay_seconds: 3.0,
}
```

### OpenAI-Specific Fields

| Field | Description |
|-------|-------------|
| `api_key_env` | Environment variable name for the OpenAI API key. |
| `api_key` | Plaintext API key (not recommended). |
| `model` | OpenAI model ID: `gpt-4o`, `gpt-4o-mini`, `o3-mini`, etc. |
| `base_url` | Optional custom base URL for OpenAI-compatible APIs (e.g. local LLM servers). |

---

## Timeout and Retry Settings

### Timeout

`timeout: 180` means the system waits up to 180 seconds for the provider to respond before declaring the request failed.

Typical response times:
- GPT-4o-mini: 10–30 seconds
- GPT-4o: 20–50 seconds
- Claude Sonnet: 15–40 seconds
- o-series reasoning models: 60–150 seconds
- Claude with extended thinking: 60–180 seconds

If you use reasoning models, do not reduce the timeout below 150 seconds.

### Retry

`retry_attempts: 2` means: if the first call fails with a transient error (rate limit, timeout, 503), retry up to 2 more times (3 total attempts).

`retry_delay_seconds: 3.0` is the wait between retries. Increase if the provider rate-limits heavily.

Errors that trigger retry:
- HTTP 429 (rate limited)
- HTTP 503 (service unavailable)
- Network timeout
- Connection reset

Errors that do not retry:
- HTTP 400 (bad request — prompt too long, invalid parameters)
- HTTP 401 (authentication failure — wrong API key)
- HTTP 404 (deployment not found)

---

## Multiple LLM Modules

OpenForexAI supports multiple LLM modules running simultaneously. Each module handles its own queue of requests independently.

### Configuration

In `system.json5`:
```json5
{
  modules: {
    llm: [
      "config/llm/azure_azmin.json5",
      "config/llm/azure_premium.json5",
      "config/llm/anthropic_claude.json5"
    ]
  }
}
```

### Routing

In Event Routing, add targeted rules to route specific agents to specific LLMs:

| Rule ID | Event | From | To |
|---------|-------|------|----|
| `default_llm` | `llm_request` | `*` | `llm:azure_azmin` |
| `eurusd_premium_llm` | `llm_request` | `OXS_T-EURUSD-AA-ANLYS` | `llm:azure_premium` |

The `eurusd_premium_llm` rule should have lower priority number (evaluated first), so EURUSD uses the premium LLM while all others fall through to `default_llm`.

### Use Cases for Multiple LLMs

- **Cost optimization**: Route high-volume pairs to a cheaper model, key pairs to a premium model
- **Quality testing**: Run identical pairs on two different models simultaneously and compare decision logs
- **Failover**: If one provider is down, reroute traffic via Event Routing without code changes
- **Provider diversification**: Reduce dependency on a single provider for business continuity

---

## Security: API Key Handling

### Environment Variable Method (Recommended)

```json5
{
  api_key_env: "AZURE_OPENAI_API_KEY"
}
```

The system reads the environment variable at startup. The key value never appears in configuration files. Set environment variables in your OS or via a `.env` file that is excluded from version control.

### Plaintext Method (Not Recommended)

```json5
{
  api_key: "sk-your-key-here"
}
```

Only use this if environment variables are not available. The key appears in the config file and in any version control history, backups, or log dumps of the file.

### Key Rotation

When rotating an API key:
1. Update the environment variable (or the plaintext field) in the module config
2. Save the file via LLM Modules
3. Restart the system or reload the module
4. Verify in [LLM Checker](ui.test.llm_checker.en.md) that requests succeed

---

## Typical Workflow

### Changing a Model ID

1. Select the module from the dropdown
2. Click **Refresh** to ensure current version is loaded
3. Change the `deployment` (Azure) or `model` (Anthropic/OpenAI) field
4. Click **Save**
5. Restart the system
6. Test via [LLM Checker](ui.test.llm_checker.en.md)

### Adjusting Temperature

1. Select the module
2. Change `default_temperature` (0.0 = deterministic, 1.0 = creative, 0.3 is a good default for trading decisions)
3. Save
4. No restart required — takes effect on next LLM call after module reload

### Adding a New Module

1. Create a new JSON5 file in `config/llm/` with appropriate content
2. Open System Config and add the path to `modules.llm`
3. Save System Config
4. Open LLM Modules — the new module appears in the dropdown
5. Verify its content
6. Add a routing rule in Event Routing to direct LLM requests to this module
7. Restart

---

## Testing LLM Module Changes

After changing any module configuration, verify the module works correctly:

1. Open [LLM Checker](ui.test.llm_checker.en.md) from the Test menu
2. Select the LLM module from the module dropdown
3. Enter a simple test prompt
4. Click Send
5. Verify a response is received within expected time

The LLM Checker bypasses the Event Bus and calls the module directly, making it the fastest way to verify connectivity and authentication without running a full agent cycle.

---

## Troubleshooting LLM Issues

### Symptom: LLM requests time out frequently

- Check provider status page for outages
- Increase `timeout` if using reasoning models (set to 200+ for o-series)
- Reduce `default_max_tokens` if prompts are very large (fewer tokens = faster response)
- Check network connectivity from the server to the provider endpoint

### Symptom: Authentication errors (HTTP 401)

- Verify the environment variable is set and accessible
- Check for leading/trailing whitespace in the key value
- Confirm the key has not expired or been revoked
- For Azure: confirm the key belongs to the correct resource (endpoint must match)

### Symptom: Deployment not found (HTTP 404)

- Azure only: the `deployment` field must exactly match the deployment name in Azure OpenAI Studio (case-sensitive)
- Verify the deployment is in the same region as the endpoint
- Check the `api_version` is supported for this deployment

### Symptom: Responses are very slow

- Complex snapshots with many fields increase prompt length and latency
- Consider reducing lookback counts in snapshot tool blocks
- Switch to a faster model for the production module and keep the slow model for testing
- Monitor response time trends in the decision log

### Log Messages

| Log Message | Meaning |
|-------------|---------|
| `[LLM] Request received from X, forwarding to provider` | Normal — request processing |
| `[LLM] Response delivered to X in Ns` | Normal — response time in seconds |
| `[LLM] Timeout after 180s for request from X` | Provider did not respond in time |
| `[LLM] Retry attempt 1/2 for request from X` | Transient error, retrying |
| `[LLM] Authentication failed for module Y` | API key issue |
| `[LLM] Rate limited, waiting Ns before retry` | Provider rate limit hit |

---

*This document covers LLM Modules as implemented in OpenForexAI v0.7+. To test LLM responses interactively, see [LLM Checker](ui.test.llm_checker.en.md). For agent-to-LLM assignment, see [Agent Config](ui.config.agent_config.en.md).*

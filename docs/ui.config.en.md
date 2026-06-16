[Back to UI Handbook](ui.en.md)

# Config

The `Config` area is the main maintenance surface for profiles, routing, and module definitions. Every aspect of how OpenForexAI behaves — which agents are active, what data the LLM receives, how orders are filtered, and which broker or LLM provider is used — is controlled through the Config pages.

## Sub-sections

| Page | Purpose |
|------|---------|
| [Agent Config](ui.config.agent_config.en.md) | Agent definitions, trading pairs, LLM bindings, risk settings |
| [Entity Config](ui.config.entity_config.en.md) | Tradeable entity (symbol) definitions — NEW |
| [Snapshot Config](ui.config.snapshot_config.en.md) | Market snapshot assembly; what data the LLM receives |
| [Decision Prompt](ui.config.decision_prompt.en.md) | LLM system prompts; selector scripts; placeholder substitution |
| [Event Routing](ui.config.event_routing.en.md) | Rules that determine which agents receive which events |
| [System Config](ui.config.system_config.en.md) | Central system.json5 global parameters |
| [LLM Modules](ui.config.llm_modules.en.md) | LLM provider connections (Azure OpenAI / Anthropic) |
| [Broker Modules](ui.config.broker_modules.en.md) | Broker adapter connections (MT5 / OANDA) |
| [Information](ui.config.information.en.md) | Editable README-style information content |
| [Bridge Tools](ui.config.bridge_tools.en.md) | Tool exposure and bridge-style tool configurations |
| [Helper Config](ui.config.helper_config.en.md) | Python helper functions for snapshot transform scripts |
| [Package Manager](ui.config.package_manager.en.md) | Export and import selected configuration packages |

Current menu order in the UI:

1. `Information`
2. `Agent Config`
3. `Snapshot Config`
4. `Decision Prompt`
5. `Entity Config`
6. `Bridge Tools`
7. `Event Routing`
8. `System Config`
9. `Helper Config`
10. `Package Manager`
11. `Broker Modules`
12. `LLM Modules`

Suggested screenshot:
- [Config menu order](image/ui-13-config-menu-overview.png)

---

## Information

Use this page for general editable information or README-style content exposed through the management API.

This page allows you to store freeform text that describes the system configuration, the strategy being used, or any operational notes. The content is accessible through the management API and can be used as a living documentation layer for your deployment.

---

## Agent Config

Use `Agent Config` to edit the runtime configuration of a specific agent.

Important current fields include:

- agent identity and runtime settings
- allowed tools
- snapshot profile selection
- decision prompt profile selection

### Agent Types

OpenForexAI uses several agent types:

| Type | Role |
|------|------|
| AA (Analysis Agent) | Receives candle events; builds snapshot; calls LLM for market analysis; produces trading signals |
| BA (Broker Agent) | Receives approved signals; calculates position sizing; places and manages orders at the broker |
| EC Relay | Applies rule-based filters to signals before they reach the BA agent |

### Key Agent Config Fields

**For AA Agents:**
- `snapshot_profile`: which snapshot profile to use for data assembly
- `decision_prompt_profile`: which Decision Prompt profile provides the LLM system instruction
- `llm_module`: which LLM provider/model to use for analysis
- `symbols`: list of trading pairs this agent analyses
- `timeframes`: which timeframes to listen on (M5, M15, H1, etc.)
- `risk_per_trade_pct`: percentage of account equity to risk per trade

**For BA Agents:**
- `broker_module`: which broker connection to use for execution
- `max_total_risk_pct`: maximum total open risk across all positions (default 3%)
- `atr_sl_multiplier`: ATR multiplier for stop-loss distance
- `atr_tp_multiplier`: ATR multiplier for take-profit distance

Suggested screenshot:
- [Agent Config with snapshot and decision prompt profile selection](image/ui-14-agent-config-profiles.png)

---

## Entity Config

`Entity Config` is a newer section for defining tradeable entities (symbols/instruments) and their properties.

This is separate from broker module configuration: the broker module defines the connection, while entity config defines the properties of each tradeable instrument that the system should know about.

### What Entity Config Defines

Each entity (symbol) can be configured with:

- **Display name**: human-readable label (e.g., "Euro / US Dollar")
- **Pip size**: the pip value for this instrument (e.g., 0.0001 for EURUSD)
- **Lot size**: standard lot definition
- **Trading hours**: when this symbol is available for trading
- **Spread model**: expected typical spread (used in risk calculations)
- **Category**: forex major, forex minor, exotic, index, commodity, etc.

### Why Entity Config Matters

Accurate entity configuration is essential for correct position sizing. The position size formula requires knowing the pip value for the instrument. If an entity is misconfigured (wrong pip size or lot definition), all position size calculations for that symbol will be wrong, which directly affects risk management.

Always verify entity config when adding a new symbol to trade.

---

## Snapshot Config

Use `Snapshot Config` to define what data is collected, interpreted, and forwarded into a snapshot-driven agent run.

The snapshot is the user message that the LLM receives. It contains all the market context the LLM needs to make a trading decision. The quality and relevance of the snapshot directly determines the quality of the LLM analysis.

### Snapshot Structure

A snapshot profile defines a set of **calculation blocks**. Each block is a data source or transformation:

- **Tool blocks**: call a system tool and include its output (e.g., get current OHLCV data, fetch ATR, query swing levels)
- **Transform blocks**: run a Python script to process, combine, or summarise tool outputs into a structured representation
- **Assembly block**: a final Python script that assembles all block outputs into the text/JSON that becomes the LLM user message

### Design Principles

- Include only what your strategy needs. More data is not always better.
- Structure the data clearly. The LLM performs better when data is labelled and organised logically.
- Use transform blocks to derive metrics (e.g., compute whether price is above or below a swing level) rather than leaving raw numbers for the LLM to interpret.
- Test snapshots using the Test Snapshot panel in Decision Prompt or the Tool Executor.

See the dedicated guide: [Snapshot Config](ui.config.snapshot_config.en.md)

Suggested screenshot:
- [Snapshot Config profile editor](image/ui-15-snapshot-config-editor.png)

---

## Decision Prompt

Use `Decision Prompt` to maintain named snapshot-aware prompt profiles for snapshot-driven agent cycles.

These profiles are not limited to AA runs. They are the runtime prompt layer that can be paired with any agent using a snapshot profile.

### What Decision Prompt Controls

The Decision Prompt profile defines:
1. **The system instruction** the LLM receives (the "rules of engagement" for the AI)
2. **How that instruction is selected** (via a Python selector script — different market conditions can trigger different prompts)
3. **Dynamic placeholder values** that are injected into the prompt text at runtime

### Most Important Config Page

For tuning trading performance, Decision Prompt is typically the highest-impact configuration page. Changing the prompt changes everything about how the LLM reasons about the market.

See the full guide: [Decision Prompt](ui.config.decision_prompt.en.md)

Suggested screenshot:
- [Decision Prompt editor](image/ui-17-decision-prompt-editor.png)

---

## Bridge Tools

Use `Bridge Tools` to define or maintain tool exposure and bridge-style tool configurations that can later be assigned to agents or reused by snapshot profiles.

Bridge tools allow external tools or APIs to be exposed to the agent system through a standardised interface. This enables:
- Custom data sources (proprietary indicators, external price feeds)
- External API integrations (sentiment data, news APIs)
- Custom calculation services

Suggested screenshot:
- [Bridge Tools console](image/ui-18-bridge-tools-console.png)

---

## Event Routing

Use `Event Routing` to maintain the rules that decide which agents receive which events.

Event routing is the configuration layer of the EC Relay. It defines:
- Which agent receives which event type
- Filter conditions (time of day, symbol, signal strength threshold)
- Whether an event is forwarded, blocked, or transformed before delivery

### Common Event Routing Patterns

**Time-of-day filter**: block signal forwarding between 22:00 and 01:00 UTC to avoid low-liquidity trading

**News blackout**: block signal forwarding for 30 minutes before and after high-impact economic events

**Confidence threshold**: only forward signals where LLM confidence exceeds a minimum value (e.g., 70)

**Symbol-specific routing**: route EURUSD signals to Agent A and GBPUSD signals to Agent B

Suggested screenshot:
- [Event Routing editor](image/ui-19-event-routing-editor.png)

---

## System Config

Use `System Config` to edit the central `system.json5`.

This is the highest-impact config page and should be handled carefully because it affects global runtime behavior. The system.json5 file contains:

- global runtime settings
- agent definitions (or references to them)
- all snapshot profiles
- all decision prompt profiles
- event routing rules
- module references

Editing system.json5 directly gives full control but requires careful JSON5 syntax. Validation errors here can prevent the system from starting.

**Best practice**: use the dedicated Config pages (Agent Config, Snapshot Config, Decision Prompt, Event Routing) for routine changes. Use System Config only when you need to make changes that are not exposed through the individual pages, or when importing/exporting the full configuration.

Suggested screenshot:
- [System Config editor](image/ui-20-system-config-editor.png)

---

## Helper Config

Use `Helper Config` to edit `config/snapshot_helpers.py`, which provides optional Python helper functions for snapshot transform scripts.

The editor is intentionally simple, but saving performs a final backend Python syntax check before the file is written.

Helper functions defined here are available as imports within all snapshot transform scripts. This allows common logic (e.g., formatting a number as pips, classifying a trend direction, formatting a time range) to be defined once and reused across multiple snapshot profiles.

Example helper function:

```python
def format_pips(price_diff, pip_size=0.0001):
    """Convert a price difference to pips."""
    return round(price_diff / pip_size, 1)

def classify_trend(ema_fast, ema_slow):
    """Return 'BULLISH', 'BEARISH', or 'NEUTRAL' based on EMA relationship."""
    if ema_fast > ema_slow * 1.001:
        return "BULLISH"
    elif ema_fast < ema_slow * 0.999:
        return "BEARISH"
    return "NEUTRAL"
```

See the snapshot reference: [Snapshot Config](ui.config.snapshot_config.en.md)

---

## Package Manager

Use `Package Manager` when you want to export or import selected parts of the runtime configuration.

Supported package areas currently include:

- agents
- snapshot profiles
- decision prompt profiles
- bridge tools
- event routing
- system config

### Typical Use Cases

**Moving config between environments**: export a tested configuration from a staging environment and import it into production.

**Backing up working settings**: before making significant changes, export the current configuration as a backup.

**Sharing configurations**: export a configuration package to share with another OpenForexAI installation.

**Version control**: export configs regularly and store them in a version control system alongside your code.

### Import Behaviour

When importing a package:
- existing profiles with the same name are overwritten (with confirmation)
- new profiles are added
- profiles not in the package are left unchanged

Always review the package content before importing into a live environment.

Suggested screenshot:
- [Package Manager export import workflow](image/ui-21-package-manager.png)

---

## Broker Modules

Use `Broker Modules` to edit raw broker module files directly.

These pages are intended for advanced operators who need to adjust adapter module settings rather than high-level agent behavior.

Each broker module file defines:
- connection type (MT5 / OANDA)
- server address and credentials
- account identifier
- connection parameters (timeout, retry policy, polling interval)

Changes to broker modules require a runtime restart to take effect.

**Security note**: broker module files contain API credentials. Never commit these files to public version control. Use environment variables for sensitive values where possible.

Suggested screenshot:
- [Broker Modules editor](image/ui-22-broker-modules-editor.png)

---

## LLM Modules

Use `LLM Modules` to edit raw LLM module files directly.

Each LLM module file defines:
- provider (azure_openai / anthropic)
- model name (gpt-4o, gpt-4o-mini, claude-sonnet-4-5, claude-haiku-3-5, etc.)
- API endpoint and credentials
- request parameters (temperature, max_tokens, timeout)
- retry policy

### Model Selection Guidelines

| Use Case | Recommended Model |
|----------|------------------|
| Production live trading | GPT-4o or Claude Sonnet |
| Strategy testing / validation | GPT-4o-mini or Claude Haiku |
| High-frequency M5 (cost-sensitive) | GPT-4o-mini or Claude Haiku |
| Complex multi-factor strategies | GPT-4o or Claude Sonnet |

**Temperature**: for trading signals, use a low temperature (0.1–0.3) to get more consistent, deterministic outputs. High temperature introduces unnecessary variance in signal direction.

**Max tokens**: set high enough to receive a complete analysis response. 500–1000 tokens is typical for a structured trading signal.

Suggested screenshot:
- [LLM Modules editor](image/ui-23-llm-modules-editor.png)

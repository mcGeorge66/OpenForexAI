[Back to Documentation Index](./README.md)

# openforexai/agents — Agent System

The runtime uses one single agent implementation:

- `openforexai/agents/agent.py`

All roles (`AA`, `BA`, `GA`) are config-driven variants of the same class.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public package export |
| `agent.py` | Single runtime `Agent` implementation |

## Design

Behavior is controlled by config, not subclasses:

1. `system_prompt`
2. `event_triggers`
3. `tool_config` (allowed tools, tiers, limits)
4. Timer settings
5. Optional broker/pair binding

## Agent Bootstrap

1. Agent sends `AGENT_CONFIG_REQUESTED`
2. ConfigService answers `AGENT_CONFIG_RESPONSE`
3. Agent initializes LLM, broker, dispatcher from payload
4. Agent starts message loop and optional timer loop

## Notes

Legacy subtype directories were removed. Domain logic should be implemented via tools/plugins and configuration.

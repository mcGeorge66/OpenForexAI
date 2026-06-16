[Back to Documentation Index](README.en.md)

# Backend Overview

This document is the technical overview of the OpenForexAI backend.

Use it when you need to understand how the runtime is composed, how data moves
through the system, and where to look when implementing or debugging backend
behavior. The user-facing operation flow is documented separately in
[UI Handbook](ui.en.md).

## Purpose

The backend is responsible for:

- loading configuration
- bootstrapping adapters and agents
- collecting and resampling market data
- building decision snapshots
- running LLM-backed agent cycles
- executing and synchronizing trading actions
- persisting domain data
- exposing the management API

## Main Runtime Components

The current runtime is built around these major parts:

- `bootstrap.py`
- `ConfigService`
- `EventBus`
- `RoutingTable`
- `DataContainer`
- configured broker adapters
- configured LLM adapters
- the Management API server
- one shared `Agent` class instantiated many times with different configs

## Architectural Principles

### Config-Driven Runtime

Agents, modules, routing, snapshot profiles, and decision prompt profiles are
defined by configuration rather than by separate subclasses.

### Single Agent Class

AA, BA, and GA are still cosmetic labels. Runtime behavior comes from agent
configuration, not from separate agent implementations.

### Tool Registry as Shared Extension Point

Tool plugins are the shared extension mechanism for:

- agent tool use
- snapshot tool blocks
- direct execution through the UI tool executor

This allows one tool implementation to be reused across multiple runtime
surfaces.

### Snapshot-Driven AA Decision Flow

The AA path is no longer centered on a long tool loop inside the LLM.
Instead, runtime code builds a prepared decision snapshot and the LLM is used
primarily as a decision engine over that snapshot.

### Broker-Confirmed Orderbook Data

The local orderbook is a local copy, but broker-confirmed timestamps and final
trade values are treated as the authoritative source wherever available.
Local UTC request timestamps remain useful as provisional process timestamps.

## Configuration Layers

The important configuration layers are:

- central runtime configuration in `config/system.json5`
- broker module configs in `config/modules/broker/`
- LLM module configs in `config/modules/llm/`
- event routing rules
- snapshot profiles
- decision prompt profiles

See also:

- [Configuration Guide](config.en.md)
- [Snapshot Config Guide](snapshot-config-guide.en.md)

## Agent Runtime Flow

At a high level, an agent runtime flow looks like this:

1. Agent requests its configuration.
2. ConfigService returns the resolved config.
3. Agent resolves its broker, LLM, and tool context.
4. The agent waits for messages or UI-driven execution input.
5. Depending on configuration and message type, it may:
   - build a snapshot
   - run an LLM decision
   - execute tools
   - publish a result or runtime event

For AA snapshot-driven cycles the normal flow is:

1. runtime collects required market data
2. runtime executes configured snapshot tool blocks
3. runtime derives semantic fields and validation flags
4. runtime builds the decision payload
5. the LLM returns the final structured decision

## Snapshot and Decision Pipeline

The snapshot system is currently one of the most important backend changes.

Its responsibilities are:

- load a named snapshot profile
- execute the configured tool blocks
- collect real market and indicator data
- derive semantic fields such as trend, RSI state, support/resistance, and
  entry gates
- build the final decision payload
- optionally expose richer preview data to the UI

Important split:

- preview/debug data can contain more structure
- the final decision payload sent to the LLM is intentionally reduced to the
  fields needed for the decision

## Management API

The management API is the integration surface for the web console.

It is used for:

- reading and writing configuration
- listing and editing agents
- editing snapshot and decision prompt profiles
- package import/export
- orderbook access
- monitor subscriptions
- execute-preview style helper calls

Technical API details are documented further in:

- [Management API](openforexai.management.en.md)

## Orderbook and Broker Synchronization

The orderbook backend currently distinguishes between:

- local UTC request timestamps
- broker-confirmed open/close timestamps
- provisional local records
- synchronized broker-confirmed records

This matters because:

- broker timestamps align with candle timing
- local timestamps are useful for tracing what the runtime attempted
- unconfirmed records can be reconciled later from the broker source

## UI Relationship

The UI is not a second backend. It is a consumer of backend state.

That means:

- the UI should display what the backend resolved
- the UI should not invent technical state
- inspection views such as Agent Chat or Orderbook should expose backend truth
  as clearly as possible

## Recommended Reading Order

If you are new to the project, read in this order:

1. [Configuration Guide](config.en.md)
2. [UI Handbook](ui.en.md)
3. [Agent System](openforexai.agents.en.md)
4. [Market Data Flow](openforexai.data.en.md)
5. [Management API](openforexai.management.en.md)
6. [Snapshot Config Guide](snapshot-config-guide.en.md)

## Related Technical Documents

- [Agent System](openforexai.agents.en.md)
- [Market Data Flow](openforexai.data.en.md)
- [Management API](openforexai.management.en.md)
- [Database Notes](database.en.md)
- [Tests Overview](tests.en.md)

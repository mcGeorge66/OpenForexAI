[Back to Documentation Index](README.en.md)

# openforexai/data — Market Data Flow

This package handles market data storage, retrieval, resampling, indicator
calculation, and tool-facing data access.

## Main Files

| File | Purpose |
|---|---|
| `container.py` | Runtime market-data hub |
| `resampler.py` | Builds higher timeframes from M5 |
| `indicators.py` | Pure indicator calculations |
| `indicator_tools.py` | Tool-facing indicator execution |
| `correlation.py` | Correlation analysis |
| `normalizer.py` | Data normalization helpers |

## Core Principle

M5 is still the primary stored timeframe.

The runtime stores M5 candles and derives higher timeframes such as:

- `M15`
- `M30`
- `H1`
- `H4`
- `D1`

This keeps data acquisition consistent and avoids separate broker calls for
every timeframe.

## Current Event Flow

The live runtime now works with an M5 update pipeline that separates data
updating from agent triggering.

Important event concepts include:

- `m5_candle_available`
- `m5_candle_update`
- `m5_agent_trigger`

The data container updates the candle store first. Analysis agents should only
run after valid runtime conditions are met for the corresponding trigger flow.

## DataContainer Responsibilities

`DataContainer` is responsible for:

- storing incoming candle data
- updating existing timestamps when a candle is finalized
- serving candle history
- resampling higher timeframes on demand
- detecting gaps
- assisting indicator and snapshot workflows

## Why This Matters for Snapshots

The snapshot builder does not fetch its own hidden market data source.

Instead it uses the same runtime data and tools that sit on top of:

- `DataContainer`
- `get_candles`
- `calculate_indicator`

This keeps:

- candle history
- indicator values
- snapshot content
- agent-visible tool results

internally consistent.

## Resampling

Higher timeframe requests are built from M5 candle history in memory at
request time.

Typical examples:

- last `12` M5 candles -> one H1 candle
- last `48` M5 candles -> one H4 candle

The resampler is therefore part of both:

- direct runtime data access
- snapshot generation

## Indicators

Indicators are pure calculations and are surfaced to the system through the
tool layer.

This means the same indicator logic can be used in two places:

1. the LLM tool loop
2. the snapshot builder

Examples:

- EMA
- RSI
- ATR
- SMA
- VWAP

## Snapshot-Centric Use

For the current AA decision path, the important data flow is:

1. tool blocks request candles and indicators
2. results are normalized into snapshot data
3. decision semantics add interpreted fields
4. the LLM sees only the reduced decision payload

This is the current replacement for the older repeated AA tool-call cycle.

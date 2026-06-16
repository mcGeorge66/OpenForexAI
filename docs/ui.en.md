[Back to Documentation Index](README.en.md)

# OpenForexAI — User Handbook

Welcome to the OpenForexAI User Handbook. This document is the master entry point for understanding, configuring, and operating the OpenForexAI automated trading system.

---

## Table of Contents

1. [What is OpenForexAI?](#what-is-openforexai)
2. [System Overview](#system-overview)
3. [Quick Start Guide](#quick-start-guide)
4. [Navigation Structure](#navigation-structure)
5. [System Architecture](#system-architecture)
6. [The Trading Workflow](#the-trading-workflow)
7. [Strategy Guidance](#strategy-guidance)
8. [Safety Guidelines](#safety-guidelines)
9. [Section Index](#section-index)

---

## What is OpenForexAI?

OpenForexAI is a fully automated Forex trading system that combines three major capabilities into a unified, event-driven pipeline:

**1. Broker Connectivity (MT5 / OANDA)**
OpenForexAI connects directly to MetaTrader 5 (MT5) or OANDA's REST API to receive live market data and execute trades. All order management — placing, modifying, and closing positions — happens through the broker adapter layer without manual intervention.

**2. AI-Powered Market Analysis (Azure OpenAI / Anthropic)**
At the heart of OpenForexAI is an AI agent system. Each configured Analysis Agent (AA Agent) receives a rich market snapshot — containing price data, technical indicators, swing levels, session context, macro news, and more — and asks a Large Language Model (LLM) to assess the current market condition and produce a trading signal.

**3. Event-Driven Execution**
The system is built around a central Event Bus. Every piece of information — a new candle, a completed analysis, a risk check result, an executed trade — is published as an event. Modules subscribe to the events they care about and react accordingly. This decoupled design means each component is independently configurable and testable.

OpenForexAI is designed for traders who want to automate disciplined, rules-based strategies while retaining full control over parameters, prompts, and risk settings. It is not a black-box signal service — every decision the AI makes is logged, explainable, and tunable.

---

## System Overview

The system operates as a continuous loop:

```
Market Data → Candle Event → Analysis Agent → Signal Event → Execution Agent → Broker
```

More precisely:

1. **Market Data Feed**: The broker adapter streams live candle data for each configured trading pair. When a candle closes (typically M5 — 5 minutes), a candle event is published to the Event Bus.

2. **Snapshot Assembly**: An AA Agent subscribed to candle close events builds a comprehensive market snapshot. This snapshot aggregates data from multiple sources: price history, ATR, swing highs/lows, trend detection, news events, session overlaps, and any custom indicators.

3. **LLM Analysis**: The assembled snapshot is sent to the configured LLM (Azure OpenAI GPT-4o or Anthropic Claude). The agent's Decision Prompt defines the system instructions. The LLM returns a structured analysis including signal direction, confidence, entry parameters, and reasoning.

4. **Signal Filtering**: The EC Relay (Event Coordinator Relay) applies rule-based filters to the raw signal. These may include time-of-day restrictions, news blackout windows, maximum concurrent trade limits, and risk budget checks.

5. **Trade Execution**: If the signal passes all filters, the BA Agent (Broker Adapter Agent) receives an execution event and places the trade through the broker API. Stop-loss and take-profit levels are calculated from ATR values embedded in the snapshot.

6. **Trade Management**: Open positions are monitored continuously. Trailing stops, partial close rules, and time-based exits are applied as further candles arrive.

7. **Logging and Monitoring**: Every event, every LLM response, every order action is written to the event log. The Monitor UI provides a real-time stream of all activity.

---

## Quick Start Guide

### Step 1: Verify the System is Running

Navigate to the **Monitor** section ([Event Stream](ui.monitor.en.md)). You should see a continuous stream of events appearing as new candles close. The key events to look for are:

- `candle_closed` — confirms market data is flowing
- `snapshot_built` — confirms the AA Agent is assembling snapshots
- `llm_response_received` — confirms the LLM is responding
- `signal_evaluated` — confirms the EC Relay has processed a signal

If any of these events are missing, check the System Config for connection issues.

### Step 2: Check Your Agent Configuration

Go to **Config → Agent Config** ([Agent Config](ui.config.agent_config.en.md)). Verify that at least one AA Agent is active, assigned to the correct trading pairs, and connected to a valid LLM module.

### Step 3: Read Your First Trade

When a trade is placed, you will see an `order_placed` event in the Monitor. Click on the event to expand it. You will see:

- **Symbol**: the trading pair (e.g., EURUSD)
- **Direction**: BUY or SELL
- **Entry Price**: the price at which the order was placed
- **Stop Loss**: ATR-derived stop level
- **Take Profit**: target level
- **Confidence**: the LLM's confidence score (0–100)
- **Reasoning**: a text summary from the LLM explaining why this trade was taken

### Step 4: Review Open Positions

Navigate to **Action → Orderbook** ([Orderbook](ui.action.orderbook.en.md)) to see all open positions with live P&L updates.

### Step 5: Tune if Needed

If you want to adjust how the AI analyses the market, go to **Config → Decision Prompt** ([Decision Prompt](ui.config.decision_prompt.en.md)) and review the system prompt. If you want to change risk parameters, go to **Config → Agent Config**.

---

## Navigation Structure

The OpenForexAI UI is organized into four primary sections:

### Action
The operational interface. Use these pages during live trading to monitor activity, review positions, inspect AI analysis, and interact with agents.

| Page | Purpose |
|------|---------|
| [Initial](ui.action.initial.en.md) | Dashboard overview and system status |
| [Agent Chat](ui.action.chat.en.md) | Direct conversation interface with AI agents |
| [Orderbook](ui.action.orderbook.en.md) | Live open positions and trade history |
| [Chart Analysis](ui.action.chart_analysis.en.md) | Visual chart with AI analysis overlay |

### Monitor
Real-time system observability. Use these pages to diagnose issues, verify the system is running correctly, and audit past decisions.

| Page | Purpose |
|------|---------|
| [Event Stream](ui.monitor.en.md) | Live feed of all system events |

### Config
Configuration management. Use these pages to define how the system behaves — which pairs to trade, how the AI reasons, how risk is managed, and how events are routed.

| Page | Purpose |
|------|---------|
| [Agent Config](ui.config.agent_config.en.md) | Agent definitions, pairs, LLM bindings, risk settings |
| [Entity Config](ui.config.entity_config.en.md) | Tradeable entity (symbol) configuration |
| [Snapshot Config](ui.config.snapshot_config.en.md) | What data is assembled into the market snapshot |
| [Decision Prompt](ui.config.decision_prompt.en.md) | System prompts used by AA agents |
| [Event Routing](ui.config.event_routing.en.md) | How events flow between modules |
| [System Config](ui.config.system_config.en.md) | Global system parameters |
| [LLM Modules](ui.config.llm_modules.en.md) | LLM provider connections (Azure OpenAI / Anthropic) |
| [Broker Modules](ui.config.broker_modules.en.md) | Broker connections (MT5 / OANDA) |

### Test
Tooling for validating configuration before going live.

| Page | Purpose |
|------|---------|
| [LLM Checker](ui.test.llm_checker.en.md) | Test LLM connectivity and prompt responses |
| [Tool Executor](ui.test.tool_executor.en.md) | Manually invoke system tools and inspect outputs |

---

## System Architecture

OpenForexAI is built around a central **Event Bus**. Every module in the system communicates exclusively through this bus — no module calls another module directly.

### Core Modules

**Event Bus**
The central nervous system. Receives published events and delivers them to all subscribers. Guarantees in-order delivery within a topic. All events are persisted to the event log.

**Broker Adapter**
Connects to MT5 or OANDA. Responsibilities:
- Streaming live candle data for configured pairs
- Executing market and limit orders
- Polling open position status
- Reporting fills, modifications, and closures as events

**AA Agent (Analysis Agent)**
The AI reasoning engine. For each subscribed pair and timeframe:
- Receives candle close events
- Requests snapshot assembly from the Snapshot Engine
- Calls the configured LLM with the assembled snapshot and Decision Prompt
- Publishes analysis results with signal, confidence, and reasoning

**Snapshot Engine**
Assembles the market snapshot from multiple data sources:
- Price and OHLCV data
- ATR and volatility metrics
- Swing highs/lows (detected algorithmically)
- Trend direction (EMA, structure analysis)
- Session context (London/New York/Tokyo overlaps)
- Economic calendar events
- Any custom calculation blocks defined in Snapshot Config

**EC Relay (Event Coordinator Relay)**
The rule engine between analysis and execution:
- Receives analysis complete events
- Applies time filters, news filters, correlation filters
- Checks risk budget (maximum open risk, maximum trades per pair)
- Forwards approved signals as execution approved events
- Publishes signal rejected with reason if blocked

**BA Agent (Broker Adapter Agent)**
The execution layer:
- Receives execution approved events
- Calculates precise entry, stop-loss, and take-profit levels
- Places orders through the Broker Adapter
- Manages position lifecycle (trailing stops, partial closes, time exits)

**LLM Adapter**
Abstracts the LLM provider:
- Supports Azure OpenAI (GPT-4o, GPT-4o-mini) and Anthropic (Claude Sonnet, Claude Haiku)
- Handles authentication, rate limiting, retry logic
- Formats requests in provider-specific schemas
- Returns normalized responses regardless of provider

**Monitor / Logger**
Persists all events and provides the UI with a queryable event stream. Supports filtering by event type, pair, agent, time range.

---

## The Trading Workflow

The complete trading workflow from candle close to executed trade:

```
[Broker] ── candle_closed ──► [Event Bus]
                                    │
                            [AA Agent subscribes]
                                    │
                            [Snapshot Engine]
                            assembles snapshot
                                    │
                            [LLM call with
                             Decision Prompt +
                             Snapshot as user msg]
                                    │
                            [LLM returns analysis]
                            signal + confidence +
                            entry + sl + tp +
                            reasoning
                                    │
                     analysis_complete ──► [Event Bus]
                                               │
                                       [EC Relay subscribes]
                                               │
                                       [Apply filters:
                                        time / news /
                                        risk budget /
                                        correlation]
                                               │
                              ┌────────────────┴──────────────────┐
                           REJECTED                            APPROVED
                              │                                    │
                    signal_rejected                   execution_approved
                    ──► [Event Bus]                   ──► [Event Bus]
                    (logged, no trade)                         │
                                                     [BA Agent subscribes]
                                                               │
                                                     [Calculate precise
                                                      entry / SL / TP]
                                                               │
                                                     [Broker Adapter
                                                      places order]
                                                               │
                                                     order_placed
                                                     ──► [Event Bus]
```

### Signal to Execution — Typical Timeline

On an M5 chart with typical LLM latency:

- T+0:00 — candle closes at broker
- T+0:01 — candle closed event published
- T+0:02 — snapshot assembly begins
- T+0:04 — snapshot complete, LLM call initiated
- T+0:08 — LLM response received (varies: 2–15 seconds)
- T+0:09 — EC Relay processes signal
- T+0:10 — order placed at broker (if approved)

Total latency from candle close to order: typically 8–20 seconds depending on LLM response time.

---

## Strategy Guidance

### What Settings Matter Most

**1. Decision Prompt** (highest impact)
The system prompt given to the LLM is the single most powerful lever for tuning trading behaviour. A well-crafted prompt that:
- Defines the strategy clearly (trend-following vs. mean-reversion vs. breakout)
- Specifies entry conditions precisely
- Instructs the LLM on how to weight conflicting indicators
- Defines what constitutes a high-confidence vs. low-confidence signal

...will dramatically outperform a generic prompt. See [Decision Prompt Config](ui.config.decision_prompt.en.md) for full guidance.

**2. Snapshot Config** (high impact)
The data the LLM receives shapes what it can reason about. Include too little and it lacks context. Include too much and it gets confused or expensive. Tune the snapshot to contain exactly what your strategy requires. See [Snapshot Config](ui.config.snapshot_config.en.md).

**3. EC Relay Filters** (medium impact)
Time-of-day filters and news blackout windows can significantly reduce false signals. Most trending strategies perform poorly during low-liquidity periods (e.g., 22:00–01:00 UTC). Configure event routing filters to match your strategy's preferred trading window. See [Event Routing](ui.config.event_routing.en.md).

**4. Risk Parameters** (critical for preservation)
The risk settings in Agent Config define position sizing. The ATR multiplier for stop-loss and the risk percentage per trade are the primary parameters. Conservative settings (0.5% risk, 1.5x ATR stop) produce smaller but more sustainable returns.

**5. LLM Model Selection** (cost vs. quality trade-off)
GPT-4o and Claude Sonnet produce the highest quality analysis but are more expensive and slower. GPT-4o-mini and Claude Haiku are faster and cheaper but may miss nuanced setups. For high-frequency M5 trading, consider the cost of LLM calls per day and select accordingly. See [LLM Modules](ui.config.llm_modules.en.md).

### Recommended Starting Configuration

For new users, the recommended starting configuration is:

- **Pairs**: EURUSD, GBPUSD (liquid, well-behaved)
- **Timeframe**: M5 (frequent signals, manageable LLM cost)
- **Risk per trade**: 1% of account
- **Stop loss**: 1.5x ATR
- **Take profit**: 2.0x ATR (1:1.33 R:R minimum)
- **LLM**: GPT-4o-mini or Claude Haiku for testing; upgrade to full model once strategy is validated
- **News filter**: block trading 30 minutes before and after high-impact news

### Validating a Strategy Before Going Live

Use the [LLM Checker](ui.test.llm_checker.en.md) to validate your Decision Prompt produces consistent, structured outputs. Use the [Tool Executor](ui.test.tool_executor.en.md) to verify snapshot assembly is working correctly. Review several days of event logs in the Monitor before enabling live execution.

---

## Safety Guidelines

### Risk Management Rules

**Never risk more than 3% of total account equity across all open positions.**
OpenForexAI enforces a configurable maximum total open risk. The default is 3%. This means if three trades are open at 1% risk each, no new trades will be entered until one closes. This limit is configurable in Agent Config but should not be increased beyond 5% under any circumstances for live trading.

**Stop-loss must always be set.**
Every trade placed by OpenForexAI includes a stop-loss level calculated from the ATR (Average True Range) of the instrument. The ATR stop ensures the stop distance is proportional to current volatility — wider during volatile sessions, tighter during quiet ones. The system will refuse to place a trade if no valid stop-loss can be calculated.

**Use ATR-based position sizing.**
Do not use fixed lot sizes. The position size calculator uses the formula:

```
Lots = (Account Equity × Risk%) / (Stop Distance in Pips × Pip Value)
```

This ensures that a stop being hit always results in the configured risk percentage, regardless of pair or volatility.

**News risk is real.**
Economic releases (NFP, CPI, interest rate decisions) cause rapid price movements that can gap through stop-losses. Use the news filter in Event Routing to block trading during these windows. The economic calendar data is included in the snapshot for the LLM's awareness, but the hard block in EC Relay is a separate, rule-based protection.

**Monitor the system during the first week.**
Even with all safety measures in place, automated systems can behave unexpectedly in unusual market conditions. Watch the Monitor event stream daily during the first week of live operation. Check that signals are reasonable, that no single pair is generating an excessive number of trades, and that P&L is in line with expectations.

**Keep broker API credentials secure.**
The Broker Module configuration contains API keys and account credentials. Never share your system.json5 or broker config files. Use environment variables for sensitive values rather than hardcoding them in config files.

### Emergency Stop

If the system is behaving unexpectedly:

1. Stop the OpenForexAI process immediately
2. Log into your broker directly and review all open positions
3. Close any positions you do not understand
4. Review the event log (Monitor) to understand what happened
5. Check system.json5 and Agent Config for misconfiguration before restarting

---

## Section Index

### Action Section

- [Action Overview](ui.action.en.md) — Introduction to all Action pages
- [Initial Dashboard](ui.action.initial.en.md) — System status and overview
- [Agent Chat](ui.action.chat.en.md) — Direct LLM agent interaction
- [Orderbook](ui.action.orderbook.en.md) — Open positions and trade history
- [Chart Analysis](ui.action.chart_analysis.en.md) — Visual chart with AI overlay

### Monitor Section

- [Event Stream](ui.monitor.en.md) — Real-time event feed

### Config Section

- [Config Overview](ui.config.en.md) — Introduction to all Config pages
- [Agent Config](ui.config.agent_config.en.md) — Agent definitions and risk settings
- [Entity Config](ui.config.entity_config.en.md) — Symbol and instrument configuration
- [Snapshot Config](ui.config.snapshot_config.en.md) — Market snapshot assembly
- [Decision Prompt](ui.config.decision_prompt.en.md) — LLM system prompts
- [Event Routing](ui.config.event_routing.en.md) — Signal filters and event flow
- [System Config](ui.config.system_config.en.md) — Global parameters
- [LLM Modules](ui.config.llm_modules.en.md) — LLM provider settings
- [Broker Modules](ui.config.broker_modules.en.md) — Broker connection settings

### Test Section

- [Test Overview](ui.test.en.md) — Introduction to test tools
- [LLM Checker](ui.test.llm_checker.en.md) — Test LLM connectivity and prompts
- [Tool Executor](ui.test.tool_executor.en.md) — Manual tool invocation

---

*OpenForexAI User Handbook — English Edition*
*For the German version of this handbook, see [Benutzerhandbuch](ui.de.md).*

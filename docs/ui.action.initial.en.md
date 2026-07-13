[Back to Action](ui.action.en.md)

# System Dashboard — Initial Page

The Initial page is the **system command center** for OpenForexAI. It loads automatically when you open the Action UI and gives you a full real-time overview of the system's health: version state, runtime controls, LLM connectivity, broker connectivity, and the complete agent roster. Every operational decision — whether to pause before making config changes, restart a degraded runtime, or simply confirm the system is healthy before a trading session — starts here.

---

## Table of Contents

1. [Page Layout Overview](#1-page-layout-overview)
2. [Version Section](#2-version-section)
3. [Runtime Controls](#3-runtime-controls)
4. [Update Status and Runtime Status](#4-update-status-and-runtime-status)
5. [LLM Interfaces Section](#5-llm-interfaces-section)
6. [Broker Interfaces Section](#6-broker-interfaces-section)
7. [Configured Agents Table](#7-configured-agents-table)
8. [Agent Types: AA, BA, GA](#8-agent-types-aa-ba-ga)
9. [Practical Workflows](#9-practical-workflows)
10. [Scenarios and Examples](#10-scenarios-and-examples)
11. [Quick Reference](#11-quick-reference)

---

## 1. Page Layout Overview

When the Initial page loads, the screen is organized into stacked sections from top to bottom:

```
┌─────────────────────────────────────────────────────┐
│  VERSION SECTION           │  RUNTIME CONTROLS       │
├─────────────────────────────────────────────────────┤
│  UPDATE STATUS             │  RUNTIME STATUS         │
├─────────────────────────────────────────────────────┤
│  LLM INTERFACES                                     │
├─────────────────────────────────────────────────────┤
│  BROKER INTERFACES                                  │
├─────────────────────────────────────────────────────┤
│  CONFIGURED AGENTS TABLE                            │
└─────────────────────────────────────────────────────┘
```

The page does **not** auto-refresh continuously. It reflects the state at the moment you navigated to it, or at the last manual refresh. Use the runtime status indicator and agent status badges to gauge whether the system is currently active.

---

## 2. Version Section

The version section sits at the top-left of the dashboard. It answers the fundamental question: **is the software up to date?**

### Local Version

Displays the version string of the OpenForexAI build currently running on this machine. Format follows semantic versioning, for example `1.4.2`. This version is read from the local package metadata at startup and does not change until you restart after an update.

**Why it matters:** If you are diagnosing unexpected behavior and corresponding with support, the local version is the first thing they will ask for. Always include it in bug reports.

### Internet Version

Displays the latest released version fetched from the GitHub release feed. This field shows `—` or a spinner until the fetch completes. If the machine has no internet access it will show an error or "Unable to check" state.

**Why it matters:** Comparing local vs. internet version tells you immediately whether an update is available without navigating anywhere else.

### Update Button

Fetches the latest release from GitHub and applies it to the local installation. The button is only active (not grayed out) when:
- The internet version has been successfully fetched.
- The internet version is newer than the local version.

**What happens when you click Update:**
1. The system downloads the release archive from GitHub.
2. Files are extracted and replaced in the installation directory.
3. The runtime is **not** automatically restarted — you must click **Restart Now** for the new version to take effect.
4. The Update Status field changes to reflect download progress and success/failure.

**Important:** The Update button does **not** stop active agents before updating. If agents are mid-cycle when files are replaced, the next cycle will pick up the new code. For a clean update, use the full sequence: Suspend → Update → Restart Now.

### Version Comparison Indicator

Below the version numbers a small indicator shows one of three states:
- **Up to date** — local version matches or exceeds internet version.
- **Update available** — internet version is newer; Update button is active.
- **Unable to check** — internet fetch failed; Update button is inactive.

---

## 3. Runtime Controls

The runtime controls are the most operationally critical buttons on the dashboard. They control the heartbeat of the entire system.

### Suspend Button

**Function:** Pauses all agent cycles without terminating the runtime process.

When you click Suspend:
- All scheduled agent timers are frozen. No new cycles will start.
- Any cycle **currently in progress** is allowed to complete before suspension takes full effect. The system does not hard-kill running cycles.
- The Suspend button becomes inactive and the Continue button becomes active.
- The Runtime Status indicator changes to reflect the suspended state.
- Broker connections remain open. LLM connections remain available. No market data or configuration is lost.

**When to use Suspend:**
- Before editing `system.json5` or any agent configuration file. Editing config while agents are cycling can cause partial reads or unexpected behavior.
- Before manually placing trades on the broker platform to avoid the agent attempting to open conflicting positions.
- Before a planned period of inattention when you want the system to remain ready but not trade.
- As the first step of the update sequence: Suspend → Update → Restart Now.

**What Suspend does NOT do:**
- It does not close open broker positions. Positions remain open on the broker and are managed again when you resume.
- It does not disconnect from brokers or LLMs.
- It does not save any cycle state — open trades remain open and will be picked up when you Continue or Restart.

### Continue Button

**Function:** Resumes all agent cycles from a suspended state.

When you click Continue:
- All agent timers are unfrozen using the current schedule.
- Agents will begin their next cycle at the next scheduled interval.
- The Continue button becomes inactive and the Suspend button becomes active.
- The Runtime Status indicator returns to the active state.

**Note:** Continue does not trigger an immediate cycle for all agents. Each agent waits for its next scheduled trigger. If you need an agent to run immediately after resuming, navigate to the Chat page and use the Execute button for that agent.

**When to use Continue:**
- After a temporary Suspend for manual trading or safe config reading.
- After any situation where you wanted to pause briefly and are now ready to resume.

**When NOT to use Continue:**
- After applying an update. Use Restart Now instead — Continue resumes the old code. Only a restart picks up the new files.
- After making changes to `system.json5`. Configuration is only re-read at startup; Continue resumes with the old configuration.

### Restart Now Button

**Function:** Performs a full runtime restart — tears down the current Node.js process and brings it back up from scratch.

When you click Restart Now:
1. All in-progress agent cycles receive a graceful shutdown signal.
2. Broker connections are closed cleanly (positions remain open on the broker side — they are not affected by a runtime restart).
3. LLM connections are terminated.
4. The Node.js process exits.
5. The process manager (PM2 or equivalent supervisor) detects the exit and relaunches the runtime automatically.
6. On startup, the system reconnects to all configured brokers and LLMs.
7. All agents re-initialize and resume their scheduled cycles.
8. Configuration is re-read from `system.json5` on startup.

**The full restart cycle typically takes 10–30 seconds** depending on how many broker and LLM connections need to be established and how quickly they respond.

**When to use Restart Now:**
- After applying an update (Update → Restart Now).
- When the Runtime Status shows a degraded or error state that Suspend/Continue cannot resolve.
- When a broker or LLM shows disconnected and reconnection attempts have failed — a restart clears all connection state and reconnects fresh.
- After making changes to `system.json5` — this is the only way for the new configuration to take effect.
- When memory usage has grown unexpectedly large after many days of continuous operation.

**When NOT to use Restart Now:**
- During active, time-sensitive market conditions when you cannot afford 10–30 seconds of downtime.
- As a first resort when only one agent is behaving oddly — try inspecting via Chat first.
- When you are only trying to resume a suspended system — use Continue instead.

---

## 4. Update Status and Runtime Status

These two status fields sit beneath the version and control sections and provide continuous state feedback.

### Update Status

Shows the result of the most recent update check or update operation.

| Status Text | Meaning |
|---|---|
| `Checking...` | Currently fetching the internet version from GitHub |
| `Up to date` | Local version matches the latest release |
| `Update available (v1.4.3)` | A newer version exists; Update button is active |
| `Downloading...` | Update in progress, download phase |
| `Installing...` | Update in progress, file replacement phase |
| `Update complete. Restart to apply.` | Files replaced; runtime restart required |
| `Update failed: [reason]` | Download or install error; check internet and disk space |
| `Unable to check` | Internet fetch failed (timeout, DNS, or no connection) |

### Runtime Status

Shows the current operational state of the runtime process.

| Status | Meaning |
|---|---|
| `Running` | System is active; agents are cycling normally |
| `Suspended` | System is paused via Suspend button; no cycles running |
| `Restarting` | Restart is in progress |
| `Error: [detail]` | A fatal error has been detected; restart likely required |
| `Starting up` | Initial startup sequence in progress (connecting brokers/LLMs) |
| `Degraded: [detail]` | Running but with issues (e.g., one broker disconnected) |

**Reading Runtime Status correctly:** A `Running` status means the scheduler is active. It does not guarantee that individual agents are healthy — an agent can be in a stuck or error state while the overall runtime shows `Running`. For per-agent health, look at the Configured Agents Table.

---

## 5. LLM Interfaces Section

This section lists every LLM (Large Language Model) module configured in `system.json5`. Each row represents one configured LLM connection and shows its current connectivity state.

### What is an LLM Interface?

An LLM interface in OpenForexAI is a configured connection to an AI model provider. A single OpenForexAI installation can have multiple LLM interfaces — for example, one using OpenAI GPT-4o, another using Anthropic Claude, and a third using a locally-hosted Ollama instance. Each interface is identified by its module name as defined in the configuration.

### Display Format

Each LLM interface entry shows:

```
[Module Name]       [Provider]       [Model]           [Badge]
openai-primary      OpenAI           gpt-4o            CONNECTED
anthropic-backup    Anthropic        claude-3-5         DISCONNECTED
ollama-local        Ollama (local)   llama3.1           CONNECTED
```

### Connected Badge

A green **CONNECTED** badge means the system successfully reached the LLM endpoint at startup (or at last connection check) and received a valid response. The interface is ready to process reasoning requests from agents.

### Disconnected Badge

A red **DISCONNECTED** badge means the system could not reach the LLM endpoint, or the endpoint returned an authentication or authorization error. When this occurs:

- Any agent configured to use this LLM interface will fail during its cycle at the reasoning step.
- The agent's status in the Configured Agents Table will typically show `ERROR` or `SKIPPED` for cycles attempted while the interface is disconnected.
- The system will not automatically retry a disconnected LLM during a cycle — the failure is logged and the cycle terminates cleanly.

**Common causes of LLM DISCONNECTED:**
1. API key expired, revoked, or incorrectly configured in `system.json5`.
2. Provider endpoint is experiencing an outage (check provider status page).
3. Network firewall or proxy blocking outbound HTTPS to the provider.
4. Billing limit reached on the provider account (quota exhausted).
5. Incorrect base URL configured for a custom or local endpoint.
6. Local model server (e.g., Ollama) is not running.

**What to do when an LLM shows DISCONNECTED:**
1. Check the provider's public status page (e.g., status.openai.com).
2. Verify the API key in `system.json5` is correct and active.
3. Test the connection manually: if it is a local model, confirm the server is running on the configured port.
4. If configuration was recently changed, use Restart Now to force a fresh connection attempt.
5. If the provider is confirmed down and you have a backup LLM, edit `system.json5` to redirect affected agents to the backup module, then Restart Now.

---

## 6. Broker Interfaces Section

This section lists every broker module configured in `system.json5`. Each row represents one broker connection.

### What is a Broker Interface?

A broker interface is a configured connection to a trading broker's API. OpenForexAI supports multiple broker adapters. Multiple broker interfaces can be configured simultaneously — for example, a live account and a demo account connected at the same time, or two different brokers for comparative execution.

### Display Format

Each broker interface entry shows:

```
[Module Name]       [Broker Type]    [Account]          [Badge]
oanda-demo          OANDA            101-001-123-001     CONNECTED
oanda-live          OANDA            101-001-456-002     DISCONNECTED
mt5-demo            MetaTrader 5     12345678            CONNECTED
```

### Connected Badge

A green **CONNECTED** badge means the broker API connection is alive. The system has successfully authenticated and can read prices, account state, and submit orders through this interface.

### Disconnected Badge

A red **DISCONNECTED** badge means the broker connection is not functioning. When this occurs:

- Any BA (Broker Agent) configured to use this broker will be unable to execute trades, read live positions, or sync account state.
- The agent's cycles may still run (the LLM reasoning portion completes), but the order execution and position sync steps will fail with an error.
- Open positions on this broker are **not closed automatically** — they remain open on the broker's servers. When the connection is restored they will resume being managed on the next sync cycle.

**Common causes of broker DISCONNECTED:**
1. API token or access credentials have expired.
2. Broker system maintenance window is in progress.
3. Network issue preventing outbound connection to the broker API endpoint.
4. Account suspended, restricted, or closed by the broker.
5. IP whitelist restrictions on the broker account blocking the server's IP address.
6. API rate limit exceeded, causing the broker to block further requests temporarily.

**What to do when a broker shows DISCONNECTED:**
1. Log into the broker's web platform directly to confirm the account is active and accessible.
2. Check if the API token has expired and regenerate if needed. Update `system.json5` and Restart Now.
3. Check broker status pages and maintenance announcements.
4. If the broker's API is temporarily down, Suspend to stop BA agents from generating streams of failed order attempts in logs.
5. When broker API recovers, Restart Now to force a fresh connection attempt.
6. After restart, verify open positions are correctly read by checking the Orderbook page.

---

## 7. Configured Agents Table

The Configured Agents Table is the most information-dense section of the Initial page. It lists every agent defined in the configuration and shows their current operational state.

### Table Columns

#### Agent ID

The unique identifier for the agent as defined in `system.json5`. This is a human-readable string that typically encodes the agent's purpose, pair, and role. Examples: `eurusd-aa-h1`, `gbpusd-ba-primary`, `global-monitor-1`.

This ID is used throughout the system to reference the agent — in logs, in the Chat page's agent selector dropdown, in the Orderbook's trade records, and in system events. When reporting a bug or analyzing logs, always identify agents by their ID.

#### Status

The current operational status of the agent. Possible values:

| Status | Meaning |
|---|---|
| `ACTIVE` | Agent is running cycles on schedule without errors |
| `IDLE` | Agent is between cycles, waiting for the next scheduled trigger |
| `RUNNING` | Agent is currently mid-cycle |
| `SUSPENDED` | All agents are suspended via the Suspend button |
| `ERROR` | Last cycle ended with an unhandled error; next cycle will retry |
| `DISABLED` | Agent is disabled in configuration (`enabled: false`) |
| `WAITING` | Agent is waiting for a dependency or prerequisite before cycling |

**Note on ERROR status:** An agent showing `ERROR` does not crash the runtime. The scheduler will attempt to run the agent again at the next scheduled interval. Persistent `ERROR` states should be investigated via the Chat page Inspector tabs — specifically the Runtime and LLM tabs — to find the root cause.

#### Type

One of three agent types: `AA`, `BA`, or `GA`. See [Section 8](#8-agent-types-aa-ba-ga) for full explanations.

#### Broker

The broker module name this agent is connected to, as configured. For AA agents, this field shows the broker used for price data even though the agent does not execute trades. For GA agents, this field is typically empty or shows `—`.

Correlating this column with the Broker Interfaces section above is how you quickly answer: "which agents are affected by this disconnected broker?"

#### LLM

The LLM module name this agent uses for its AI reasoning steps. This is the same module name shown in the LLM Interfaces section. If you see a `DISCONNECTED` badge for a module in the LLM Interfaces section, all agents showing that module name in the LLM column are affected and their reasoning steps will fail.

#### Pair

The currency pair or instrument this agent is focused on. Examples: `EUR_USD`, `GBP_USD`, `XAU_USD`. For GA agents, this field is typically `—` as they operate at the system level rather than on a specific instrument.

#### Task Description

A human-readable description of what this agent does, pulled directly from the configuration. This field is purely informational. Examples:
- `"Analyze H1 trend and generate hourly bias for EURUSD"`
- `"Execute EURUSD trades based on AA output, 2% risk per trade"`
- `"Monitor overall portfolio drawdown and alert on threshold breach"`

### Reading the Table at a Glance

**A healthy system shows:**
- All agents with `ACTIVE` or `IDLE` status
- No `ERROR` entries
- LLM column values matching modules with `CONNECTED` badges
- Broker column values matching modules with `CONNECTED` badges

**A problematic system might show:**
- One or more agents with `ERROR` status — investigate via Chat Inspector
- Agents where the LLM column points to a `DISCONNECTED` LLM — the AI reasoning steps are broken for those agents
- Agents where the Broker column points to a `DISCONNECTED` broker — price data and order execution are broken for those agents
- `DISABLED` entries that should be active — check `enabled` flag in `system.json5`

---

## 8. Agent Types: AA, BA, GA

Understanding the three agent types is essential for interpreting the Initial page correctly and making sound operational decisions.

### AA — Analysis Agent

**Role:** Market analysis only. No trading whatsoever.

An Analysis Agent observes the market, processes price data, technical indicators, and contextual information, and produces a structured market assessment. Its output typically includes:
- A directional bias (`BIAS_LONG`, `BIAS_SHORT`, or `NEUTRAL`)
- A confidence score
- Supporting reasoning and context
- An `order_start_signal` flag indicating whether conditions currently favor trade entry

**Key characteristics of AA agents:**
- They connect to a broker **for price data only** — they never submit, modify, or cancel orders.
- They run on a defined schedule (e.g., every 15 minutes, every hour at the start of a new candle).
- Their output is stored in the database and made available to BA agents that are configured to read it.
- On the Chart Analysis page, their decisions appear as D/N markers: D = decision with `order_start_signal=YES`, N = neutral or signal not triggered.
- Multiple AA agents can cover the same pair on different timeframes simultaneously (e.g., one M15 AA and one H1 AA for EURUSD).

**Example AA agent row:**
```
eurusd-h1-analyst | IDLE | AA | oanda-demo | openai-primary | EUR_USD | H1 trend analysis and hourly bias generation
```

### BA — Broker Agent / Execution Agent

**Role:** Trade execution. Reads analysis output, decides to act, places and manages live orders.

A Broker Agent reads the output of one or more AA agents, applies its own execution logic (entry quality checks, risk sizing, timing filters, spread checks), and submits orders to the broker when conditions are met. It also manages the full lifecycle of open trades: monitoring stops, syncing position state with the broker, and handling closures.

**Key characteristics of BA agents:**
- They both read prices (from broker) and submit orders (to broker) — they have full read-write access to the trading account.
- They typically reference one or more AA agents' output as part of their decision process.
- They require a working broker connection to function — if the broker shows `DISCONNECTED`, the BA agent's execution steps will fail even if the LLM reasoning succeeds.
- All their actions (trade opens, closes, modifications, rejections) are recorded in the Orderbook with full context.
- A single BA agent typically manages one instrument on one broker account.

**Example BA agent row:**
```
eurusd-executor | ACTIVE | BA | oanda-live | anthropic-backup | EUR_USD | Execute EURUSD trades, 2% risk, manage SL/TP
```

### GA — Global / System Agent

**Role:** Infrastructure, monitoring, alerting, coordination. Not instrument-specific.

A Global Agent operates at the system level rather than focusing on a specific trading instrument. Common uses include:
- Monitoring overall portfolio risk and drawdown across all open BA agent positions
- Sending notifications (Telegram, email) when defined conditions are triggered
- Performing housekeeping tasks (log cleanup, database maintenance)
- Coordinating between multiple AA/BA agents — for example, a session filter that gates all BA agents during low-liquidity hours

**Key characteristics of GA agents:**
- They typically have no instrument pair assigned.
- They may or may not use an LLM — some GA agents are pure rule-based logic without AI reasoning.
- They run on their own schedule, often more frequently than analysis or execution agents.
- They do not appear in the Orderbook (they do not place trades).

**Example GA agent row:**
```
portfolio-monitor | ACTIVE | GA | — | — | — | Monitor portfolio risk, send alert if drawdown > 5%
```

---

## 9. Practical Workflows

### Workflow 1: Daily Pre-Session Health Check

Before the market opens for your primary trading session, run through this checklist on the Initial page:

1. **Check Runtime Status** — confirm it shows `Running`. If it shows `Suspended`, click Continue to resume.
2. **Check LLM Interfaces** — all configured LLMs should show `CONNECTED`. Resolve any disconnections before the session begins.
3. **Check Broker Interfaces** — all active brokers should show `CONNECTED`. A disconnected live broker means no trades can execute regardless of what the agents decide.
4. **Scan Agents Table for errors** — look for any `ERROR` statuses. If found, navigate to Chat → select that agent → review the Runtime inspector tab for the most recent error details.
5. **Check version state** — if `Update available` is shown and you want to apply it before the session: Suspend → Update → Restart Now → re-verify all connections.

Typical time when everything is healthy: 60–90 seconds.

### Workflow 2: Safe Configuration Change Procedure

When you need to edit `system.json5` or any agent configuration:

1. Navigate to the Initial page.
2. Click **Suspend** and wait for the Runtime Status to confirm suspension (all agent timers are now frozen).
3. Make your configuration edits using your text editor.
4. Click **Restart Now** — not Continue. Configuration changes require a full restart to take effect.
5. Wait for the runtime to come back up (10–30 seconds). The page will transition through `Restarting` and `Starting up` states.
6. Verify all LLM and Broker interfaces show `CONNECTED`.
7. Verify the Configured Agents Table reflects your changes (new agents appear, removed agents are gone, modified descriptions are updated).
8. The system resumes automatically after a restart — there is no need to click Continue.

**Critical:** Never click Continue after a configuration change expecting the new config to take effect. Continue resumes using the already-loaded configuration. Only Restart Now triggers a fresh read of `system.json5`.

### Workflow 3: Applying an Update Safely

1. Navigate to the Initial page and confirm `Update available` is shown.
2. Click **Suspend** and wait for suspension confirmation in the Runtime Status.
3. Click **Update** and watch the Update Status field. Wait for `Update complete. Restart to apply.`
4. Click **Restart Now**.
5. After the restart completes, verify that:
   - The Local Version matches the Internet Version.
   - All LLM and Broker interfaces show `CONNECTED`.
   - The Configured Agents Table looks as expected.
6. If something is broken after the update, check the release notes for breaking changes in the `system.json5` schema before making changes.

### Workflow 4: Responding to a Disconnected LLM

1. On the Initial page, note which LLM module shows `DISCONNECTED` (e.g., `openai-primary`).
2. In the Configured Agents Table, identify all agents where the LLM column shows `openai-primary` — those agents are affected and will fail their reasoning steps.
3. Check the provider's status page to determine if it is a provider-side outage.
4. Verify the API key in `system.json5` is correct and has not expired or hit a billing limit.
5. If configuration was not recently changed and the provider appears healthy, click **Restart Now** to force a fresh connection attempt.
6. If the provider is confirmed down, click **Suspend** to stop error-spam in logs while you wait for recovery.
7. When the provider recovers, click **Restart Now** to reconnect. The CONNECTED badge should appear within 30 seconds of startup.

### Workflow 5: Responding to a Disconnected Broker

1. Note which broker module shows `DISCONNECTED` (e.g., `oanda-live`).
2. In the Configured Agents Table, note which agents use that broker — they are the affected set.
3. Log into the broker's web platform directly to verify the account is active and the API is accessible.
4. Check for scheduled maintenance announcements on the broker's status page.
5. If credentials are confirmed invalid, update `system.json5` (after Suspend) and Restart Now.
6. If the broker API is temporarily down, Suspend to prevent repeated failed connection attempts being logged.
7. When the API recovers, Restart Now. After reconnection, verify the Orderbook page shows current open positions correctly — this confirms the sync was successful.

### Workflow 6: Handling a Persistent Agent ERROR

1. Identify the agent showing `ERROR` status in the Configured Agents Table.
2. Navigate to the Chat page and select that agent from the dropdown.
3. Click **Execute** to run a fresh cycle in inspect mode.
4. Read the **Runtime** inspector tab — it shows all monitoring events from the cycle including the specific error message and stack trace.
5. Read the **LLM** inspector tab — if the error occurred during AI reasoning, you will see the failed request here.
6. Read the **Tools** inspector tab — if the error occurred during a tool call (e.g., price data fetch), you will see which tool failed and with what arguments.
7. Based on the error, determine whether the fix is:
   - A broker/LLM connectivity issue (fix the interface, Restart Now)
   - A configuration issue in the agent's prompt or parameters (fix `system.json5`, Restart Now)
   - A transient error that resolved itself (re-run Execute to confirm)

---

## 10. Scenarios and Examples

### Scenario A: System Healthy But No Trades for Hours

**Symptom:** Runtime shows `Running`, all badges show `CONNECTED`, but no new trades appear in the Orderbook for the past 4 hours.

**Investigation on Initial page:**
1. Check BA agent status — does it show `ACTIVE` or `IDLE`? If so, it is running fine but simply not finding valid signals.
2. Check the AA agent that feeds the BA — is it `ACTIVE`? Is it using the expected LLM?
3. If everything looks green, navigate to Chat, select the AA agent, and run Execute. Read the Overview inspector — what is the decision output? Is it `NEUTRAL` or `BIAS_LONG/SHORT` with `order_start_signal=NO`?

**Most common resolution:** The AA agent is correctly generating `NEUTRAL` or `order_start_signal=NO` based on current market conditions. This is the system working as designed. The system does not force trades — it waits for genuinely favorable conditions.

### Scenario B: One LLM Disconnected, One Connected

**Setup:** You have `openai-primary` (DISCONNECTED) and `anthropic-backup` (CONNECTED).

**Impact assessment on Initial page:**
1. Check the LLM column in the Configured Agents Table.
2. Agents using `openai-primary` are broken for reasoning.
3. Agents using `anthropic-backup` are fully functional.
4. You have two options: wait for `openai-primary` to recover and Restart Now, or temporarily redirect affected agents to `anthropic-backup` in `system.json5`, then Suspend → save → Restart Now.

### Scenario C: Runtime Shows ERROR After Long Uptime

**Symptom:** After 3 weeks of continuous operation, Runtime Status shows `Error: JavaScript heap out of memory`.

**Resolution:**
This is a Node.js memory accumulation issue common to long-running processes. Click **Restart Now**. The process manager relaunches the runtime cleanly. Memory is reclaimed on restart. All configuration, database records (trades, analyses), and broker positions are fully preserved — nothing is lost in a restart.

### Scenario D: Manual Trade Needed Without Agent Interference

**Situation:** You want to manually place a large position on the broker that conflicts with the agent's current open positions or intended entries.

**Procedure:**
1. Click **Suspend** on the Initial page.
2. Place your manual trade on the broker platform.
3. Monitor your trade manually.
4. When your manual trade is closed, click **Continue** to resume agent cycles.

**Why Suspend?** BA agents perform position sync during each cycle. If a BA agent is active and encounters an unexpected open position during sync, it may attempt to close or modify it depending on its sync configuration. Suspending prevents this interference entirely.

### Scenario E: Update Applied But Agents Table Shows Wrong Configuration

**Symptom:** After updating and restarting, the Configured Agents Table shows agents that no longer exist in `system.json5`, or new agents are missing.

**Investigation:**
1. The update may have introduced a new `system.json5` schema version.
2. Check the release notes for migration instructions.
3. Open `system.json5` in a text editor and verify the structure matches the new expected format.
4. Apply any required schema migrations to `system.json5`, then Suspend → save → Restart Now.
5. After the second restart, verify the table reflects the correct agent configuration.

### Scenario F: System Shows Degraded After Market Holiday

**Symptom:** The morning after a market holiday, Runtime Status shows `Degraded: broker connection pool timeout`.

**Resolution:**
Some broker APIs drop persistent connections during market closures. This is expected behavior. Click **Restart Now** to re-establish all connections fresh. The system will reconnect within 30 seconds and return to full `Running` status.

---

## 11. Quick Reference

### Button Summary

| Button | Effect | Requires Restart? | Loses State? |
|---|---|---|---|
| Update | Downloads and installs the latest release | No (restart separately) | No |
| Suspend | Freezes all agent cycles | No | No |
| Continue | Resumes frozen cycles | No | No |
| Restart Now | Full process restart, re-reads config | N/A (IS the restart) | No* |

*Broker positions remain open. Database records are preserved. In-flight cycle state may be incomplete.

### Status at a Glance

| What You See | What It Means | Recommended Action |
|---|---|---|
| All green badges, Running | System fully healthy | None required |
| LLM DISCONNECTED | AI reasoning will fail for affected agents | Check API key and provider status |
| Broker DISCONNECTED | Trades and data reads will fail for affected agents | Check broker credentials and status |
| Agent ERROR | That agent's last cycle failed | Inspect via Chat → Runtime tab |
| Update available | Newer version on GitHub | Suspend → Update → Restart Now |
| Runtime Suspended | No cycles running | Click Continue to resume |
| Runtime Error | Fatal runtime issue | Click Restart Now |
| Runtime Degraded | Running with partial issues | Investigate specifics; usually Restart Now |

### Suspend vs. Restart Decision Guide

**Suspend when:**
- About to edit configuration files (then follow with Restart)
- About to manually trade on the broker
- Taking a planned break and wanting the system ready but not trading
- Applying an update (then follow with Restart)

**Restart Now when:**
- Configuration changes need to take effect
- LLM or broker won't reconnect despite the service being healthy
- An update has been applied and needs to be loaded
- Runtime shows Error or Degraded state
- Memory usage is unexpectedly high after long uptime
- After a market holiday where broker connections dropped silently

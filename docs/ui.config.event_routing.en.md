[Back to Config](ui.config.en.md)

# Event Routing

Event Routing is the central nervous system of OpenForexAI. It governs how every event produced by any component reaches its intended recipients. Rather than hard-coding communication paths into agent code, the system uses a declarative routing table: a list of rules that the Event Bus evaluates at runtime whenever a message is published. This design makes it possible to add, remove, or reroute data flows without restarting the system or touching any agent source code.

The configuration is stored in `config/RunTime/event_routing.json5` and is hot-reloaded whenever a rule is saved or deleted.

---

## Table of Contents

1. [What the Event Bus Does](#what-the-event-bus-does)
2. [The Routing Table](#the-routing-table)
3. [Rule Editor](#rule-editor)
4. [Event Type Reference](#event-type-reference)
5. [From Pattern Syntax](#from-pattern-syntax)
6. [To Target Syntax](#to-target-syntax)
7. [Priority](#priority)
8. [Disabling Rules](#disabling-rules)
9. [Live Rule Explanation Panel](#live-rule-explanation-panel)
10. [Buttons and Actions](#buttons-and-actions)
11. [The Complete Routing Chain](#the-complete-routing-chain)
12. [Practical Examples](#practical-examples)
13. [Troubleshooting Routing Issues](#troubleshooting-routing-issues)
14. [Design Principles](#design-principles)

---

## What the Event Bus Does

The Event Bus is a publish-subscribe message broker that runs inside the OpenForexAI process. Every component — agents, data gateways, broker adapters, LLM services, the repository — registers itself as a bus member with a unique Agent-ID. When a component wants to communicate, it publishes an event to the bus. The bus then evaluates all routing rules in priority order and delivers the event to every target matched by a rule.

Key properties:

- **Decoupled**: Publishers do not know who receives their events.
- **Configurable at runtime**: Rules can be added, changed, or deleted while the system is running.
- **Prioritized**: When multiple rules match, lower priority numbers are processed first.
- **Filtered**: Each rule specifies which event types and which senders it applies to.
- **Hot-reload**: Clicking Update or Delete triggers an instant reload of routing configuration — no restart required.

The bus does not buffer undelivered events. If a target is not registered when delivery is attempted, the event is dropped with a warning log entry. This means agents must be running before events intended for them are generated.

---

## The Routing Table

The routing table is displayed as a sortable, filterable grid. Each row represents one routing rule.

### Columns

| # | Column | Description |
|---|--------|-------------|
| 1 | **#** | Row number (display only) |
| 2 | **Id** | Unique snake_case rule identifier |
| 3 | **Event** | The event type this rule matches |
| 4 | **From** | Sender pattern (Agent-ID format or wildcard) |
| 5 | **To** | Target expression (literal, wildcard, or template) |
| 6 | **Prio** | Priority number (1 = highest, 200 = low) |
| 7 | **Off** | Orange `●` shown when rule is disabled |

### Sorting

Click any column header to sort ascending. Click again to sort descending. The sort indicator (▲ or ▼) appears in the active header. Sorting does not affect rule evaluation order — that is always determined by the Priority field regardless of display order.

### Filtering

Four filter input fields sit above the table:

- **Id filter**: Substring match on the rule ID
- **Event filter**: Substring match on the event type
- **From filter**: Substring match on the From pattern
- **To filter**: Substring match on the To expression

All filters are applied simultaneously (AND logic). Clear a filter by deleting its text. Filters are case-insensitive. The row count shown in the table footer updates live as filters are applied.

### Row Selection

Click any row to select it. The selected row is highlighted and its values are loaded into the Rule Editor below the table. Editing fields in the Rule Editor does not change the rule until you click **Update** or **Save As New**.

---

## Rule Editor

The Rule Editor is located in the bottom-left section of the Event Routing screen. It contains the following fields:

### ID

A unique snake_case identifier for this rule. Examples: `aa_to_ec_relay`, `ec_to_ba`, `candles_request_to_data`, `order_request_to_broker`.

Rules:
- Must be unique across all routing rules
- Use only lowercase letters, digits, and underscores
- Should be descriptive of the route's purpose
- Cannot be changed for an existing rule via Update — use Delete followed by Save As New to rename

### Event

A dropdown listing all known event types, grouped by category. Select the event this rule should match. The special value `*` means the rule matches all event types regardless of content.

See the full Event Type Reference section below for descriptions of each event.

### Description

An optional free-text field for human-readable notes. This text appears in the Live Rule Explanation panel as the "What" description of the event. Useful for documenting why a rule exists, especially for complex routing setups.

### From

The sender pattern. Controls which publishing component(s) this rule applies to. Uses Agent-ID segment syntax. See the From Pattern Syntax section for details.

### To

The target expression. Controls where matched events are delivered. Supports literal IDs, wildcards, and templates. See the To Target Syntax section for details.

### Priority

An integer between 1 and 200. Lower numbers are processed first when multiple rules match the same event. Use priority to control sequencing when order of delivery matters.

### Disable

A checkbox or toggle. When enabled, the rule is retained in the configuration but is skipped during routing evaluation. The row shows an orange `●` in the Off column. Use this to temporarily suspend a route without losing its configuration.

---

## Event Type Reference

Events are grouped by functional category. The dropdown in the Rule Editor shows these same groups.

### Market Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `m5_agent_trigger` | Fires every M5 candle close; signals AA agents to begin analysis | AD agent (AgentDispatcher) |
| `m5_candle_update` | Real-time tick-level candle update (not yet closed) | Broker adapter |
| `m5_candle_saved` | Confirmation that a closed M5 candle has been persisted to the database | Data Gateway |
| `candle_gap_detected` | Notifies that a gap in candle history was found during sync | Data Gateway |

### Indicator Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `candles_request` | Request for historical candles for a given pair/timeframe/count | AA agent or other requester |
| `candles_response` | Fulfillment of a candles_request with OHLCV data | GA-DATA (data gateway) |
| `indicator_request` | Request to calculate a technical indicator (EMA, RSI, ATR, etc.) | AA agent |
| `indicator_response` | Calculated indicator values, ready for snapshot assembly | GA-DATA |
| `swing_levels_request` | Request for swing high/low levels for a pair/timeframe/lookback | AA agent |
| `swing_levels_response` | Calculated swing levels with price and timestamp | GA-DATA |

### Account Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `account_status_request` | Request for current account balance, equity, margin | BA agent or UI |
| `account_status_response` | Current account financial state | Broker adapter |
| `account_status_updated` | Proactive push when account state changes significantly | Broker adapter |
| `positions_request` | Request for list of currently open positions | BA agent |
| `positions_response` | Open positions with symbol, direction, size, P&L | Broker adapter |

### Trading Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `order_request` | Instruction to place a new market or pending order | BA agent |
| `order_result` | Outcome of an order_request (success/failure, ticket ID) | Broker adapter |
| `position_close_request` | Instruction to close a specific open position | BA agent |
| `position_close_result` | Outcome of a close request | Broker adapter |
| `order_modify_request` | Request to change SL/TP of an existing position | BA agent |
| `order_modify_result` | Outcome of modify request | Broker adapter |
| `signal_generated` | AA agent has produced a trading signal recommendation | AA agent |
| `signal_approved` | EC entity has approved a signal for execution | EC entity |
| `signal_rejected` | EC entity has rejected a signal | EC entity |
| `order_placed` | Confirmation that an order has been submitted to the broker | BA agent |
| `position_opened` | A new position is now live in the broker account | Broker adapter |
| `position_closed` | A position has been fully closed | Broker adapter |

### Analysis Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `analysis_requested` | Manual or scheduled request for an AA agent to run analysis | UI or scheduler |
| `analysis_result` | Output from AA agent analysis including signal and snapshot | AA agent |

### Agent Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `agent_query` | General-purpose query directed at a specific agent | Any component |
| `agent_response` | Response to an agent_query | Target agent |
| `agent_config_requested` | Request for an agent's current configuration | UI Config panel |
| `agent_config_response` | Agent returns its current configuration JSON | Agent |
| `agent_trigger_received` | Agent acknowledges receipt of a trigger | AA agent |
| `agent_trigger_skipped` | Agent skipped a trigger (outside session, no positions, etc.) | AA agent |

### EC Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `ec_config_requested` | Request for an EC entity's current configuration | UI Config panel |
| `ec_config_response` | EC entity returns its configuration | EC entity |
| `ec_output` | EC entity's decision output (approve/reject signal + sizing) | EC entity |

### LLM Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `llm_request` | Request to call an LLM with a system prompt and user message | AA agent |
| `llm_response` | LLM's reply, including raw text and parsed decision | LLM service module |

### Repository Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `repo_request` | Request to read or write data to the repository (decisions, snapshots) | Any component |
| `repo_response` | Result of a repo_request | GA-REPO (repository gateway) |

### System Events

| Event | Description | Sent by |
|-------|-------------|---------|
| `routing_reload_requested` | Triggers an immediate re-read of the routing configuration | Config UI |
| `prompt_updated` | Signals that a prompt template has been changed | Prompt Config UI |
| `system_info` | General informational system message | Any component |
| `system_error` | System-level error notification | Any component |
| `*` | Wildcard — matches every event type | (used in rules only) |

---

## From Pattern Syntax

The From field uses the Agent-ID segment format. An Agent-ID has four segments separated by hyphens:

```
{BROKER}-{PAIR}-{TYPE}-{ROLE}
```

Examples of actual Agent-IDs:
- `OXS_T-EURUSD-AA-ANLYS` — the Analysis agent for EURUSD on broker OXS_T
- `SYSTM-ALL___-GA-DATA` — the global Data Gateway
- `OXS_T-ALL___-BA-ANLYS` — the BA agent for broker OXS_T
- `OXS_T-EURUSD-EC-RELAY` — the EC entity for EURUSD on OXS_T
- `OXS_T-ALL___-AD-DISP` — the AgentDispatcher for OXS_T

### Wildcard Segments

Use `*` to match any value in a segment:

| Pattern | Matches |
|---------|---------|
| `*` | Any sender (all components) |
| `*-*-AA-*` | All AA agents, any broker, any pair, any role |
| `*-*-EC-*` | All EC entities, any broker, any pair |
| `*-*-AD-*` | All AgentDispatcher agents |
| `*-*-BA-*` | All BA agents, any broker |
| `OXS_T-*-AA-*` | All AA agents on broker OXS_T |
| `OXS_T-EURUSD-AA-ANLYS` | Exact match — only this one agent |
| `*-*-GA-*` | All gateway agents |

Wildcard matching is segment-by-segment. A `*` in one segment does not match across hyphens.

### Special Broker/Pair Values

- `SYSTM` — system-level components (gateways, config service, repository)
- `ALL___` — used when a component is not pair-specific (6 characters with trailing underscores to maintain consistent ID length). Example: `OXS_T-ALL___-BA-ANLYS` is the BA agent for the entire OXS_T broker, not tied to a single pair.

### Exact vs. Wildcard Performance

Exact patterns (`OXS_T-EURUSD-AA-ANLYS`) are slightly faster to evaluate than wildcards. For high-frequency events like `m5_agent_trigger`, prefer template-based To targets over wildcard To targets to reduce broadcast overhead.

---

## To Target Syntax

The To field determines where matched events are delivered. Three forms are supported:

### 1. Literal ID

Deliver to exactly one registered bus member.

```
OXS_T-ALL___-BA-ANLYS
SYSTM-ALL___-GA-DATA
SYSTM-ALL___-GA-REPO
SYSTM-ALL___-GA-CFGSV
```

The target must be a currently registered bus member. If the member is not registered (e.g., the agent has not started yet), the event is silently dropped with a warning in the log.

### 2. Wildcard

Deliver to all registered bus members whose IDs match the pattern.

```
*-*-EC-*         → all EC entities
*-*-AA-*         → all AA agents
*                → broadcast to every registered bus member
```

Wildcard delivery sends one copy to each matched member. The set of matched members is evaluated at the time of delivery, so if new members register after the rule was created, they are automatically included.

### 3. Template

Derive the target ID dynamically from the sender's ID. Uses `{sender.segment}` placeholders:

| Placeholder | Value |
|-------------|-------|
| `{sender.broker}` | First segment of the sender's ID (e.g. `OXS_T`) |
| `{sender.pair}` | Second segment of the sender's ID (e.g. `EURUSD`) |
| `{sender.type}` | Third segment of the sender's ID (e.g. `AA`) |
| `{sender.role}` | Fourth segment of the sender's ID (e.g. `ANLYS`) |

Template examples and how they resolve:

```
{sender.broker}-{sender.pair}-EC-RELAY
```
Sender `OXS_T-EURUSD-AA-ANLYS` → resolves to `OXS_T-EURUSD-EC-RELAY`

```
{sender.broker}-ALL___-BA-ANLYS
```
Sender `OXS_T-EURUSD-EC-RELAY` → resolves to `OXS_T-ALL___-BA-ANLYS`

```
{sender.broker}-{sender.pair}-AA-ANLYS
```
Sender `OXS_T-EURUSD-AD-DISP` → resolves to `OXS_T-EURUSD-AA-ANLYS`

Templates allow a single rule to correctly route events from any number of broker/pair combinations without requiring one rule per pair. This is the recommended approach for all cross-component routing.

---

## Priority

Priority is an integer from 1 to 200. When the Event Bus evaluates which rules apply to a given event, it processes matching rules in ascending priority order (1 first, 200 last).

Priority affects:
- **Order of delivery** when multiple rules match the same event and the order of processing matters
- **System resource allocation** — critical routes get processed before optional ones

Recommended priority ranges:

| Range | Use |
|-------|-----|
| 1–10 | Critical system routes (config requests, error handling, system events) |
| 11–30 | Core data flow (candle requests, indicator requests, repo requests) |
| 31–60 | Agent trigger routing and analysis flow |
| 61–100 | EC and BA routing, order handling |
| 101–150 | Monitoring, logging, UI notification routes |
| 151–200 | Optional, low-urgency, or experimental routes |

When two rules have the same priority and both match, delivery order between them is implementation-defined. Use distinct priorities if order matters.

---

## Disabling Rules

Rules can be disabled without deleting them. A disabled rule:
- Is stored in the configuration file
- Is shown in the routing table with an orange `●` in the Off column
- Is completely skipped during routing evaluation
- Can be re-enabled at any time by editing the rule and unchecking Disable, then clicking Update

Use cases for disabling:
- Temporarily stopping a data flow during debugging
- Suspending a pair's analysis without removing its configuration
- A/B testing alternative routing configurations
- Preparing a new rule set before activating it
- Reducing bus load during off-hours

---

## Live Rule Explanation Panel

The Live Rule Explanation panel is located in the bottom-right section of the Event Routing screen. It updates in real time as you edit the Rule Editor fields.

### Natural Language Summary

At the top of the panel: a plain-English sentence describing what the current rule does.

Example:
> "When `analysis_result` is sent from any AA agent, deliver to the EC-RELAY entity for the same broker and pair with priority 40."

### EVENT Section

- **Type**: The event name displayed with its category color coding
- **What**: The description field value, or an auto-generated description if the field is empty
- **Sent by**: Which type of component normally generates this event

### FROM Section

- **Pattern**: The raw From value
- **Explanation**: Human-readable interpretation of the pattern

Examples of FROM explanations:
- `*` → "Wildcard — matches events from any sender"
- `*-*-AA-*` → "Wildcard pattern — matches all AA agents regardless of broker or pair"
- `*-*-EC-*` → "Wildcard pattern — matches all EC entities"
- `OXS_T-EURUSD-AA-ANLYS` → "Exact match — only the EURUSD Analysis agent on OXS_T broker"
- `OXS_T-*-BA-*` → "Partial wildcard — matches all BA agents for broker OXS_T"

### TO Section

- **Target**: The raw To value
- **Explanation**: Human-readable interpretation with a resolved example

Examples of TO explanations:
- `SYSTM-ALL___-GA-DATA` → "Literal target — delivers to the global Data Gateway"
- `*-*-EC-*` → "Wildcard target — broadcasts to all currently registered EC entities"
- `{sender.broker}-{sender.pair}-EC-RELAY` → "Template target — derives broker and pair from sender. Example: sender OXS_T-EURUSD-AA-ANLYS → OXS_T-EURUSD-EC-RELAY"
- `*` → "Broadcast — delivers to every registered bus member (use with caution)"

### VALIDATION Section

The validation section lists any problems found with the current rule values:

| Issue | Severity |
|-------|----------|
| Duplicate ID | Error — blocks save |
| Empty ID | Error — blocks save |
| Invalid ID format (spaces, uppercase) | Error — blocks save |
| Empty Event | Error — blocks save |
| Empty From | Error — blocks save |
| Empty To | Error — blocks save |
| Priority not a number 1–200 | Error — blocks save |
| Unknown event type | Warning — save allowed, shown in amber |
| Template placeholder unrecognized | Warning — save allowed |

---

## Buttons and Actions

| Button | Color | Action |
|--------|-------|--------|
| **New Empty Rule** | Amber | Clear all form fields to prepare for entering a new rule from scratch |
| **Update** | Green | Save changes to the currently selected rule and trigger hot-reload |
| **Save As New** | Blue | Create a new rule using the current form values (ID must be unique) |
| **Delete** | Red | Remove the currently selected rule and trigger hot-reload |

Hot-reload means the Event Bus immediately applies the updated routing configuration. No restart is required and no interruption occurs for running agents. In-flight events (already in the delivery queue) continue under the old rules; new events use the updated rules instantly.

---

## The Complete Routing Chain

Below is a full description of every standard routing rule in a default OpenForexAI installation. Rules are listed in logical flow order (not necessarily priority order).

---

### Rule 1: `agent_config_request_to_cfgsv`

| Field | Value |
|-------|-------|
| Event | `agent_config_requested` |
| From | `*` |
| To | `SYSTM-ALL___-GA-CFGSV` |
| Priority | 5 |

**Purpose**: When any component requests agent configuration data (typically the UI Config panel), the request is routed to the Configuration Service gateway. The Config Service reads the current configuration from disk and returns an `agent_config_response` directly to the requester.

**Why priority 5**: Configuration requests are system-critical. They must be routed before any other potentially competing rules.

---

### Rule 2: `ec_config_request_to_cfgsv`

| Field | Value |
|-------|-------|
| Event | `ec_config_requested` |
| From | `*-*-EC-*` |
| To | `SYSTM-ALL___-GA-CFGSV` |
| Priority | 5 |

**Purpose**: EC entities requesting their own configuration are routed to the Config Service. This enables EC entities to reload their rules, thresholds, and gate parameters at runtime when configuration is updated via the Entity Config panel.

---

### Rule 3: `ad_trigger_to_aa`

| Field | Value |
|-------|-------|
| Event | `m5_agent_trigger` |
| From | `*-*-AD-*` |
| To | `{sender.broker}-{sender.pair}-AA-ANLYS` |
| Priority | 20 |

**Purpose**: The AgentDispatcher fires an `m5_agent_trigger` for each active pair at every M5 close. The template routes each trigger to the AA Analysis agent for the same broker and pair. If the AD fires for `OXS_T-EURUSD-AD-DISP`, the event goes to `OXS_T-EURUSD-AA-ANLYS`.

**Template benefit**: Covers all pairs automatically. Adding a new pair to the AD does not require a new routing rule.

---

### Rule 4: `aa_result_to_ec`

| Field | Value |
|-------|-------|
| Event | `analysis_result` |
| From | `*-*-AA-*` |
| To | `{sender.broker}-{sender.pair}-EC-RELAY` |
| Priority | 40 |

**Purpose**: After the AA agent completes analysis and produces an `analysis_result`, the result is routed to the Event Composer (EC) for that broker/pair. The EC evaluates gate conditions, enriches the result with risk sizing, and decides whether to approve or reject the signal.

---

### Rule 5: `ec_output_to_ba`

| Field | Value |
|-------|-------|
| Event | `ec_output` |
| From | `*-*-EC-*` |
| To | `{sender.broker}-ALL___-BA-ANLYS` |
| Priority | 50 |

**Purpose**: The EC entity's decision (approved/rejected signal with position sizing) is routed to the Broker Agent for the same broker. Note the `ALL___` in the To target — BA agents are not pair-specific; one BA agent handles all pairs for a given broker. The BA agent then decides whether to place the order based on account state and risk rules.

---

### Rule 6: `candles_request_to_data`

| Field | Value |
|-------|-------|
| Event | `candles_request` |
| From | `*` |
| To | `SYSTM-ALL___-GA-DATA` |
| Priority | 30 |

**Purpose**: Any component requesting historical candle data is routed to the Data Gateway. The Data Gateway queries the database or requests from the broker adapter as needed, then returns a `candles_response` to the original requester (using the requester's ID preserved in the request payload).

---

### Rule 7: `indicator_request_to_data`

| Field | Value |
|-------|-------|
| Event | `indicator_request` |
| From | `*` |
| To | `SYSTM-ALL___-GA-DATA` |
| Priority | 30 |

**Purpose**: Indicator calculation requests (EMA, RSI, ATR) are routed to the Data Gateway, which performs the calculation using the stored candle data and returns an `indicator_response`.

---

### Rule 8: `swing_levels_request_to_data`

| Field | Value |
|-------|-------|
| Event | `swing_levels_request` |
| From | `*` |
| To | `SYSTM-ALL___-GA-DATA` |
| Priority | 30 |

**Purpose**: Swing level requests are routed to the Data Gateway. Returns `swing_levels_response` with detected pivot high/low levels and their timestamps.

---

### Rule 9: `repo_request_to_repo`

| Field | Value |
|-------|-------|
| Event | `repo_request` |
| From | `*` |
| To | `SYSTM-ALL___-GA-REPO` |
| Priority | 25 |

**Purpose**: All repository read/write requests (decisions, snapshots, trade history) are routed to the Repository Gateway. The REPO gateway handles database persistence and returns `repo_response`.

---

### Rule 10: `order_request_to_broker`

| Field | Value |
|-------|-------|
| Event | `order_request` |
| From | `*-*-BA-*` |
| To | `{sender.broker}-ALL___-BK-CONN` |
| Priority | 60 |

**Purpose**: Order placement requests from BA agents are routed to the broker connector for the same broker. Template resolution ensures OXS_T requests go to the OXS_T broker adapter and not another broker's connector.

---

### Rule 11: `account_status_request_to_broker`

| Field | Value |
|-------|-------|
| Event | `account_status_request` |
| From | `*` |
| To | `{sender.broker}-ALL___-BK-CONN` |
| Priority | 35 |

**Purpose**: Account status requests are routed to the appropriate broker connector, which queries the live account and returns `account_status_response` to the requesting component.

---

## Practical Examples

### Example A: Routing a New Pair

You are adding GBPUSD trading on broker OXS_T. The AD agent already lists GBPUSD in its active pairs. You want to confirm routing covers it automatically.

Check these three rules exist and use templates (not hardcoded pairs):

1. `ad_trigger_to_aa` — From: `*-*-AD-*`, To: `{sender.broker}-{sender.pair}-AA-ANLYS`
2. `aa_result_to_ec` — From: `*-*-AA-*`, To: `{sender.broker}-{sender.pair}-EC-RELAY`
3. `ec_output_to_ba` — From: `*-*-EC-*`, To: `{sender.broker}-ALL___-BA-ANLYS`

If all three use templates, GBPUSD is automatically supported. No new routing rules needed.

---

### Example B: Adding a Monitoring Route

You want to send every `analysis_result` to a monitoring agent registered as `SYSTM-ALL___-MN-LOG`.

Create a new rule:

| Field | Value |
|-------|-------|
| ID | `analysis_result_to_monitor` |
| Event | `analysis_result` |
| From | `*` |
| To | `SYSTM-ALL___-MN-LOG` |
| Priority | 150 |
| Description | Send all analysis results to monitoring logger |

Priority 150 ensures it runs after all critical routing has already delivered the event to the EC entity.

---

### Example C: Routing LLM Requests

LLM requests from agents need to reach the correct LLM service. If you have a module `azure_azmin` registered as `llm:azure_azmin`:

| Field | Value |
|-------|-------|
| ID | `llm_request_to_azure` |
| Event | `llm_request` |
| From | `*` |
| To | `llm:azure_azmin` |
| Priority | 20 |

If you have multiple LLM modules and want specific agents to use specific LLMs, use exact From patterns instead of `*`:

| Field | Value |
|-------|-------|
| ID | `eurusd_llm_to_premium` |
| Event | `llm_request` |
| From | `OXS_T-EURUSD-AA-ANLYS` |
| To | `llm:azure_premium` |
| Priority | 15 |

This rule fires before the catch-all at priority 20, so EURUSD uses the premium LLM while all other agents use azure_azmin.

---

### Example D: Debugging a Missing Signal

Signals from EURUSD AA agent are not reaching the BA agent. Systematic checklist:

**Step 1**: Open Event Routing. Filter `Event = analysis_result`. Verify rule `aa_result_to_ec` exists and is not disabled (no orange `●`).

**Step 2**: Check the To template is `{sender.broker}-{sender.pair}-EC-RELAY`. Open System Monitor and verify that `OXS_T-EURUSD-EC-RELAY` appears in the registered members list. If missing, the EC entity for EURUSD has not started.

**Step 3**: Filter `Event = ec_output`. Verify rule `ec_output_to_ba` exists. Check it uses the correct template.

**Step 4**: Check priority. Filter by `analysis_result` — are there any other rules with a lower priority number that could be interfering?

**Step 5**: Check the system log for:
- `[BUS] No rule matched for event analysis_result from OXS_T-EURUSD-AA-ANLYS`
- `[BUS] Target OXS_T-EURUSD-EC-RELAY not registered`
- `[EC] Signal rejected by gate: ...` (signal reached EC but was rejected)

---

### Example E: Temporarily Suspending a Pair

To pause USDJPY signals without changing Agent Config:

1. Disable the `ad_trigger_to_aa` rule (this affects all pairs, so not ideal)
2. Better: Go to Agent Config → USDJPY AA agent → set `enabled: false`
3. The agent will receive triggers but log `agent_trigger_skipped` — clean and reversible

For routing-only suspension (advanced): Create a low-priority rule that routes `m5_agent_trigger` from the USDJPY AD to a null target, effectively intercepting but not delivering. This is complex and not recommended for standard use.

---

## Troubleshooting Routing Issues

### Symptom: Events published but never received

1. Check rule is not disabled (Off column)
2. Verify target ID in To field matches a registered bus member exactly
3. Check From pattern: does it actually match the sender's full Agent-ID? Enable DEBUG logging and check the sender ID in the log
4. Verify no higher-priority rule is intercepting the event before this rule

### Symptom: Event received by wrong component

1. Two rules may match the same event/from combination with overlapping To patterns
2. Template resolved to unexpected value — enable DEBUG logging and trace the sender ID
3. Wildcard in To is broader than intended (e.g. `*-*-BA-*` matches all BA agents including those for other brokers)

### Symptom: Routing change has no effect

1. Verify you clicked Update (not Save As New — that creates a duplicate)
2. Check Validation panel for errors that prevented saving
3. Check system log for hot-reload failure messages: `[BUS] Routing reload failed`
4. Refresh the page to confirm the saved state

### Symptom: System performance degraded after routing change

1. Wildcard `*` in To broadcasts to every registered component — even idle ones
2. A feedback loop: Component A's output routes back to Component A's input. Check for circular paths
3. Very low priority rules on high-frequency events (like `m5_candle_update`) cause many evaluations

### Log Messages for Routing

| Log Message | Meaning |
|-------------|---------|
| `[BUS] No rule matched for event X from Y` | No routing rule applies — event dropped |
| `[BUS] Target Z not registered` | Rule matched but target not on bus |
| `[BUS] Routing reloaded (N rules)` | Hot-reload completed successfully |
| `[BUS] Routing reload failed: <error>` | Syntax or validation error in config |
| `[BUS] Delivered X from Y to Z` | Debug-level confirmation of successful delivery |
| `[BUS] Template resolved: X → Y` | Debug-level template resolution trace |

---

## Design Principles

### Why a Routing Table Instead of Hard-Coded Paths

Hard-coded routing couples components tightly. Adding a new pair would require code changes in the AgentDispatcher, the AA agent, the EC entity, and the BA agent. With routing tables, adding a pair is purely a configuration task — zero code changes.

### Why Templates

Templates prevent combinatorial explosion of rules. Without templates, supporting 5 brokers with 20 pairs each = 100 rules just for the AA→EC link. With the template `{sender.broker}-{sender.pair}-EC-RELAY`, one rule covers all 100 combinations automatically and any future pairs added.

### Why Priority Numbers Instead of Rule Order

Rule order in a file is fragile — inserting a rule changes all subsequent indices. Priority numbers decouple logical importance from physical position. You can insert a priority-5 rule anywhere in the table and it always evaluates first.

### Why Hot-Reload

Markets do not stop. Being able to fix or adjust routing without restarting the entire system is essential in a live trading environment. Hot-reload provides zero-downtime configuration changes, meaning you can correct a routing mistake during active trading without losing any agent state.

### Why Explicit Disable Instead of Delete

Deleting a rule is permanent unless you remember its exact configuration. Disabling preserves the rule for quick re-activation and provides an audit trail of what routing was active at any given time.

---

*This document covers Event Routing as implemented in OpenForexAI v0.7+. For agent-level trigger configuration, see [Agent Config](ui.config.agent_config.en.md). For EC entity configuration, see [Entity Config](ui.config.entity_config.en.md).*

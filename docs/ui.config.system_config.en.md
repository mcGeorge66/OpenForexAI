[Back to Config](ui.config.en.md)

# System Config

System Config is a direct editor for the central configuration file `config/system.json5`. This file controls the global runtime behavior of the entire system — log level, broker timezone offset, management API settings, LLM module references, broker module references, snapshot profiles, decision prompt profiles, agents, and event composers.

> **Caution:** This is the highest-impact configuration page. Errors in `system.json5` can prevent the system from starting or cause incorrect behavior across all agents simultaneously. Use the specialized wizard pages (Agent Config, Entity Config) for per-agent changes, and reserve System Config for global settings that have no dedicated UI.

---

## Table of Contents

1. [Interface Overview](#interface-overview)
2. [Save Behavior and Validation](#save-behavior-and-validation)
3. [JSON5 Syntax Primer](#json5-syntax-primer)
4. [Key Sections of system.json5](#key-sections-of-systemjson5)
5. [The `system` Section](#the-system-section)
6. [broker_candle_utc_offset_hours — Critical Setting](#broker_candle_utc_offset_hours--critical-setting)
7. [The `modules` Section](#the-modules-section)
8. [The `snapshot_profiles` Section](#the-snapshot_profiles-section)
9. [The `decision_prompt_profiles` Section](#the-decision_prompt_profiles-section)
10. [The `agents` Section](#the-agents-section)
11. [The `event_composers` Section](#the-event_composers-section)
12. [Typical Workflow](#typical-workflow)
13. [When to Use System Config vs. Dedicated Pages](#when-to-use-system-config-vs-dedicated-pages)
14. [Recovering from a Broken system.json5](#recovering-from-a-broken-systemjson5)

---

## Interface Overview

The System Config screen consists of four elements:

### Header Bar

| Element | Function |
|---------|----------|
| **File path** | Displays the full path to `config/system.json5` |
| **Refresh** | Reloads the current file from disk, discarding any unsaved edits |
| **Save** | Validates the JSON5 content and writes it to disk |
| **Position** | Shows the current cursor position as line:column |

### Line Numbers

Displayed on the left side of the editor, scrolling in sync with the text. Use the position indicator in the header bar to jump to a specific line.

### Editor Textarea

Free-text editing area for `system.json5`. Syntax highlighting is applied (read-only visual aid only — the textarea remains fully editable):

| Color | Applied to |
|-------|-----------|
| Cyan | Object keys |
| Green | String values |
| Amber | Boolean values (`true`, `false`) |
| Gray | `null` values |
| Purple | Numeric values |

JSON5 comments (`//` and `/* */`) are displayed in a muted tone and are preserved on save.

### Status Messages

- **"Saved."** — File was written successfully
- **Error message** — Displayed inline when validation fails; the file is not written

---

## Save Behavior and Validation

When you click Save, the system:

1. Parses the editor content as JSON5 (supports comments, trailing commas, unquoted keys)
2. Verifies the top-level result is a JSON object (not an array, not a primitive)
3. If parsing fails: shows an error message with the line/column of the syntax error; does not write the file
4. If parsing succeeds: writes the file to disk and shows "Saved."

**Important**: A running system does not automatically re-read `system.json5`. Changes take effect at the next system start or when the affected module is reloaded. If you change only a module reference path, restart the system. If you change agent configuration, the dedicated Agent Config page offers hot-reload without a full restart.

---

## JSON5 Syntax Primer

`system.json5` uses JSON5 format, which is a superset of JSON with quality-of-life additions:

```json5
{
  // Single-line comments are allowed
  /* Block comments too */
  
  system: {
    log_level: "INFO",            // Unquoted keys are valid
    broker_candle_utc_offset_hours: 3,
    trailing_comma_ok: true,      // Trailing commas on last items allowed
  },
  
  modules: {
    llm: ["config/llm/azure_azmin.json5"],
    broker: ["config/broker/oxs_mt5.json5"],
  }
}
```

Keys do not require quotes unless they contain special characters. Trailing commas on the last item in an object or array are allowed. Single-line and block comments are preserved.

---

## Key Sections of system.json5

The file is organized into these top-level sections:

| Section | Purpose |
|---------|---------|
| `system` | Global runtime parameters (log level, timezone offset, API settings) |
| `modules` | File paths to LLM and broker module config files |
| `snapshot_profiles` | Snapshot profile definitions (or paths to profile files) |
| `decision_prompt_profiles` | Decision prompt profile definitions |
| `agents` | All agent definitions |
| `event_composers` | All EC entity definitions |

---

## The `system` Section

```json5
{
  system: {
    log_level: "INFO",
    broker_candle_utc_offset_hours: 3,
    management_api: {
      host: "0.0.0.0",
      port: 8765,
    },
    ui: {
      dev_server: {
        enabled: false,
        port: 5173,
      }
    }
  }
}
```

### `log_level`

Controls the verbosity of system logging.

| Value | Behavior |
|-------|---------|
| `DEBUG` | All messages including bus delivery traces, template resolutions, per-tool timing |
| `INFO` | Normal operational messages: agent cycles, decisions, order placements |
| `WARNING` | Only issues that may need attention but don't stop operation |
| `ERROR` | Only errors that prevented an action from completing |

Use `DEBUG` when investigating routing or snapshot problems. Switch back to `INFO` for normal operation — DEBUG produces very high log volume.

### `management_api`

The HTTP API server used by the UI.

| Field | Default | Description |
|-------|---------|-------------|
| `host` | `"0.0.0.0"` | Bind address. Use `"127.0.0.1"` to restrict to localhost only. |
| `port` | `8765` | Port number. Change if port is occupied. |

### `ui.dev_server`

For development only. When `enabled: true`, the backend serves the UI on the dev server port instead of the production build.

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `false` | Enable dev server mode |
| `port` | `5173` | Vite dev server port |

Keep `enabled: false` in production.

---

## broker_candle_utc_offset_hours — Critical Setting

This single value has a large impact on trading session accuracy. Read this section carefully before changing it.

### What It Is

`broker_candle_utc_offset_hours` is the UTC offset of the broker's server time. For example:
- A broker running on UTC+3 (common for MT5 brokers following EEST): `3`
- A broker running on UTC+0: `0`
- A broker running on UTC+2 (standard EET): `2`

### Why It Matters

Candle timestamps returned by MT5 are in broker server local time — not UTC. The candle for `2024-03-15 12:00:00` on a UTC+3 broker actually represents `2024-03-15 09:00:00 UTC`.

The session filter in the system needs to compare this broker-local candle timestamp to configured session boundaries (e.g. London Open at 08:00 UTC, New York Close at 21:00 UTC). To make this comparison work:

1. The system converts session boundaries from UTC to broker local time using `broker_candle_utc_offset_hours`
2. The converted boundary is compared against the candle's timestamp

### Session Boundary Conversion Example

**Scenario**: You want the session to end 30 minutes before New York close.

- New York closes at 17:00 EDT = 21:00 UTC
- Broker is UTC+3: 21:00 UTC → 00:00 broker time (midnight)
- Post-session buffer: -30 min → session ends at 23:30 broker time
- The system computes: `session_end_broker_time = 23:30`
- A candle with timestamp `23:15` (broker) is inside session
- A candle with timestamp `23:45` (broker) is outside session → trigger skipped

### If the Value Is Wrong

If `broker_candle_utc_offset_hours` does not match your broker's actual server UTC offset:

- Session filter triggers at incorrect times (offset by the UTC offset error)
- Example: Broker is UTC+3 but you set `2` → session boundaries are 1 hour off
- This can cause missed signals during valid trading hours, or signals during prohibited hours

### How to Find Your Broker's UTC Offset

1. Open MT5
2. Note the server time displayed in the top-right
3. Compare to your local time and calculate the offset to UTC
4. Common values: OXS_T uses UTC+3 (EEST/EET depending on DST)

### DST Note

MT5 brokers typically adjust their server UTC offset twice per year for daylight saving time:
- Summer (late March to late October): UTC+3 (EEST)
- Winter (late October to late March): UTC+2 (EET)

If your broker follows this pattern, update `broker_candle_utc_offset_hours` at each DST transition. Add a calendar reminder.

---

## The `modules` Section

```json5
{
  modules: {
    llm: [
      "config/llm/azure_azmin.json5"
    ],
    broker: [
      "config/broker/oxs_mt5.json5"
    ]
  }
}
```

Each entry is a file path relative to the project root. The referenced file contains the full configuration for that module. See [LLM Modules](ui.config.llm_modules.en.md) and [Broker Modules](ui.config.broker_modules.en.md) for details on the content of these files.

Adding a new LLM or broker adapter: add its config file path to the appropriate array and restart the system.

---

## The `snapshot_profiles` Section

Snapshot profiles can be defined inline in `system.json5` or referenced by path. In most installations, profiles are stored in `system.json5` directly for single-file simplicity. The Snapshot Config UI page reads from and writes to these definitions.

The profile structure is documented fully in [Snapshot Config](ui.config.snapshot_config.en.md).

---

## The `decision_prompt_profiles` Section

Similar to snapshot profiles. Each profile contains a system prompt for the LLM and a user message template. The Decision Prompt Config page manages these. Direct editing in System Config is possible but the dedicated page is safer.

---

## The `agents` Section

Contains all agent definitions. Each agent has:
- `id`: the full Agent-ID string
- `type`: agent implementation class
- `enabled`: whether to start this agent
- `snapshot_profile`: which snapshot profile to use
- `decision_prompt_profile`: which prompt profile to use
- `llm`: which LLM module to use

For individual agent changes, the Agent Config page is strongly preferred over editing this section directly — it provides validation, hot-reload, and prevents accidental corruption of other agents.

---

## The `event_composers` Section

Contains all EC entity definitions. Each EC entity has gate thresholds, position sizing parameters, and risk rules. For individual EC entity changes, the Entity Config page is strongly preferred.

---

## Typical Workflow

For global system settings (log level, timezone offset, API port):

1. Click **Refresh** to load the current version
2. Locate the `system` section at the top of the file
3. Edit the target field
4. Click **Save**
5. Check for error messages
6. Restart the system if required (most global settings require restart)

For module path changes:

1. Create the new module config file (e.g. `config/llm/new_llm.json5`)
2. Open System Config
3. Add the file path to `modules.llm` or `modules.broker`
4. Save
5. Restart

---

## When to Use System Config vs. Dedicated Pages

| Task | Recommended Tool |
|------|-----------------|
| Change log level | System Config |
| Change broker server UTC offset | System Config |
| Change management API port | System Config |
| Add a new LLM module | System Config (add path) + LLM Modules (edit content) |
| Add a new broker module | System Config (add path) + Broker Modules (edit content) |
| Edit an agent's snapshot profile | Agent Config |
| Edit an agent's prompt | Decision Prompt Config |
| Add or modify a routing rule | Event Routing |
| Edit EC gate thresholds | Entity Config |
| Edit snapshot tool/calculation blocks | Snapshot Config |
| Bulk-rename a field across all agents | System Config (with care) |

---

## Recovering from a Broken system.json5

If you save a `system.json5` with a syntax error and the system fails to start:

**Option 1 — Fix via UI** (if the UI still loads)
1. Open System Config
2. The editor will show the broken content
3. Fix the syntax error (look at the error message for line/column)
4. Save again

**Option 2 — Fix via file editor**
1. Open `config/system.json5` in any text editor
2. Find and fix the syntax error
3. Restart the system

**Option 3 — Restore from backup**
The system writes a backup before each save to `config/system.json5.bak`. If the current file is corrupt:
1. Rename `config/system.json5` to `config/system.json5.broken`
2. Rename `config/system.json5.bak` to `config/system.json5`
3. Restart

**Common syntax errors:**
- Missing closing `}` or `]`
- Comma after the last item in strict JSON mode (not an error in JSON5, but check anyway)
- Unmatched string quotes
- Invalid escape sequences in strings

---

*This document covers System Config as implemented in OpenForexAI v0.7+. For agent-level configuration, see [Agent Config](ui.config.agent_config.en.md). For LLM adapter settings, see [LLM Modules](ui.config.llm_modules.en.md). For broker adapter settings, see [Broker Modules](ui.config.broker_modules.en.md).*

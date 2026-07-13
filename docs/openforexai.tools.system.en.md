[Back to Documentation Index](README.md)

# tools/system — System Tools

Administrative tools for system operations: raising alarms and triggering synchronisation.

## Tools

### `raise_alarm` — RaiseAlarmTool

Emits a system alarm event. Used by agents to signal critical conditions that require human attention or automated response.

**Input:**
```json
{
  "severity": "HIGH",
  "message": "Drawdown exceeded 4% threshold — all positions at risk",
  "context": "Account equity dropped from 10000 to 9590 in 2 hours"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `severity` | string | ✓ | `"LOW"`, `"MEDIUM"`, `"HIGH"`, `"CRITICAL"` |
| `message` | string | ✓ | Human-readable alarm description |
| `context` | string | — | Additional context or data |

**Returns:**
```json
{
  "alarm_raised": true,
  "severity": "HIGH",
  "alarm_id": "ALARM_20260302_123456",
  "timestamp": "2026-03-02T12:34:56Z"
}
```

**What happens when an alarm is raised:**
1. A `SYSTEM_ERROR` monitoring event is emitted (visible in `monitor.py`)
2. The alarm is logged at the appropriate log level
3. If severity is HIGH or CRITICAL, a `RISK_BREACH` event is published to the EventBus, waking the BA agent

**Approval mode:** `direct` — alarms must never be blocked

**Always available:** `raise_alarm` is included in the `"safety"` tier (the last resort tier when the context budget is nearly exhausted). This means agents can always raise an alarm even when running out of tokens.

---

### `trigger_sync` — TriggerSyncTool

Triggers an immediate order book synchronisation between the local database and the broker's live state.

**Input:**
```json
{
  "pair": "EURUSD",
  "reason": "Detected discrepancy in position count"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pair` | string | — | Specific pair to sync (omit for all pairs) |
| `reason` | string | — | Reason for triggering sync |

**Returns:**
```json
{
  "sync_triggered": true,
  "pair": "EURUSD",
  "timestamp": "2026-03-02T12:34:56Z"
}
```

**What happens:** Publishes an `ORDER_BOOK_SYNC_DISCREPANCY` event which causes the broker adapter to re-verify open positions and reconcile any differences.

**Approval mode:** `direct`

---

## Context Tier Placement

If you choose to enable optional context tiers, system tools are the ones that should remain available last:

| Tier | Tools included |
|---|---|
| `all` (0–84%) | All tools |
| `safety` (85–100%) | `raise_alarm`, `close_position` |

This ensures that even when the agent is running out of context window, it can still:
- Raise a critical alarm
- Close a dangerous position

Other trading tools such as `place_order`, `auto_place_order`, and `modify_order`
should normally remain outside the final safety tier.

This design prevents scenarios where a nearly-full context causes the agent to be unable to respond to emergencies.

In the current default project configuration, context-tier gating is not enabled, so tool visibility is controlled by `allowed_tools`.


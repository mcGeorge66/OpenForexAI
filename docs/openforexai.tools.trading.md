[Back to Documentation Index](./README.md)

# tools/trading — Trading Execution Tools

Tools in `openforexai/tools/trading/` interact directly with the broker layer. They are the most sensitive tools in the system because they can open, modify, or close live positions.

## Tools

### `place_order` — PlaceOrderTool

Submits an order for the current pair with explicit order parameters.

**Typical input:**
```json
{
  "pair": "EURUSD",
  "direction": "buy",
  "order_type": "MARKET",
  "risk_pct": 0.5,
  "stop_loss": 1.079,
  "take_profit": 1.086,
  "reasoning": "H1 trend aligned with M15 continuation setup",
  "confidence": 0.78
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `broker` | string | — | Broker short name or module name for UI/tool-executor context |
| `pair` | string | — | Currency pair such as `EURUSD` |
| `direction` | string | ✓ | `buy` or `sell` |
| `order_type` | string | ✓ | `MARKET`, `LIMIT`, `STOP`, `STOP_LIMIT`, `TRAILING_STOP` |
| `units` | integer | — | Explicit size in broker units |
| `lots` | number | — | Explicit size in lots, converted to units |
| `entry_price` | number | — | Reference/entry price, especially for pending orders |
| `risk_pct` | number | — | Risk-based sizing input (0.1–5.0) |
| `stop_loss` | number | — | Stop-loss price |
| `take_profit` | number | — | Take-profit price |
| `limit_price` | number | — | Limit price for `LIMIT` and `STOP_LIMIT` |
| `stop_price` | number | — | Stop trigger price for `STOP` and `STOP_LIMIT` |
| `trailing_stop_distance` | number | — | Distance for `TRAILING_STOP` |
| `reasoning` | string | — | Audit note stored with the order |
| `confidence` | number | — | Documentation score from `0.0` to `1.0` |

Notes:
- Sizing is typically provided by `units`, `lots`, or `risk_pct`.
- The actual execution logic is shared in `order_execution.py`.

---

### `auto_place_order` — AutoPlaceOrderTool

Places an order using centrally defined defaults from `order_execution.AUTO_ORDER_DEFAULTS`. Only the trade direction is mandatory; other fields are optional overrides.

**Typical input:**
```json
{
  "direction": "buy",
  "stop_loss": 1.079,
  "take_profit": 1.086,
  "reasoning": "Default-managed continuation entry"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `broker` | string | — | Broker short name or module name for UI/tool-executor context |
| `pair` | string | — | Currency pair such as `EURUSD` |
| `direction` | string | ✓ | `buy` or `sell` |
| `order_type` | string | — | Optional override of the default order type |
| `units` | integer | — | Explicit size in broker units |
| `lots` | number | — | Explicit size in lots |
| `entry_price` | number | — | Optional entry price override |
| `risk_pct` | number | — | Override for default risk-based sizing |
| `stop_loss` | number | — | Override for stop-loss |
| `take_profit` | number | — | Override for take-profit |
| `limit_price` | number | — | Optional limit price override |
| `stop_price` | number | — | Optional stop trigger price override |
| `trailing_stop_distance` | number | — | Optional trailing stop override |
| `reasoning` | string | — | Audit note |
| `confidence` | number | — | Override for default confidence |

Use `auto_place_order` when your agent should follow standard execution defaults without repeating the full order template every time.

---

### `modify_order` — ModifyOrderTool

Adjusts stop-loss and/or take-profit on an existing open position.

**Typical input:**
```json
{
  "position_id": "12345678",
  "stop_loss": 1.0815,
  "take_profit": 1.089,
  "reasoning": "Trail protection after favorable move"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `broker` | string | — | Broker short name or module name for UI/tool-executor context |
| `pair` | string | — | Optional pair context |
| `position_id` | string | ✓ | Broker-assigned position ID |
| `stop_loss` | number | — | New stop-loss price |
| `take_profit` | number | — | New take-profit price |
| `reasoning` | string | — | Audit note for the change |

Notes:
- At least one of `stop_loss` or `take_profit` must be provided.
- On success, the tool also updates the local order-book entry when a matching open entry exists.

---

### `close_position` — ClosePositionTool

Closes an existing open position by broker position ID. Partial closes are supported via `units` or `lots`.

**Typical input:**
```json
{
  "position_id": "12345678",
  "units": 5000,
  "reasoning": "Reduce exposure ahead of event risk"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `broker` | string | — | Broker short name or module name for UI/tool-executor context |
| `pair` | string | — | Optional pair context; used to narrow batch-close operations |
| `position_id` | string | ✓ | Broker-assigned position ID. Special value `"0"` closes all open positions in scope |
| `units` | integer | — | Partial-close size in broker units |
| `lots` | number | — | Partial-close size in lots |
| `reasoning` | string | — | Audit note explaining the exit |

Notes:
- If `position_id == "0"`, the tool batches over all open positions, optionally restricted by `context.pair`.
- The tool updates the local order book for full and partial closes.

---

## Approval & Risk Gating

Trading tools can be restricted in three layers:

### Layer 1: Agent allow-list

The agent must expose the tool in `tool_config.allowed_tools`.

### Layer 2: Optional approval

`ToolDispatcher` can enforce `direct`, `supervisor`, or future `human` approval per tool.

### Layer 3: Context budget tiers

This layer is optional. If you enable it, the dispatcher can reduce visible tools as context usage rises. A typical Broker Agent policy is:

- `all`: `get_candles`, `calculate_indicator`, `get_account_status`, `get_open_positions`, `get_order_book`, `place_order`, `close_position`, `raise_alarm`, `trigger_sync`
- `decision`: `place_order`, `close_position`, `raise_alarm`
- `safety`: `close_position`, `raise_alarm`

This guarantees that a nearly full context can still exit dangerous positions.

In the current default project configuration, this layer is not enabled.

---

## Which Agents Use These Tools

Trading execution tools are primarily intended for Broker Agents (`BA`). Analysis Agents (`AA`) should remain analysis-only and must not be configured to submit, modify, or close trades directly unless you intentionally break that separation.

---

## Audit Trail

Execution tools write operational details into broker results and local order-book records:

- `place_order` / `auto_place_order`: create or update the order-book entry through shared execution helpers
- `modify_order`: updates local stop-loss / take-profit fields when a matching open entry exists
- `close_position`: writes close status, realized P&L, close reasoning, and partial-close state

This is the basis for later supervision, analytics, and prompt optimization.

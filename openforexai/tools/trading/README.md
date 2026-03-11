# tools/trading — Trading Execution Tools

Tools that execute live trades. These are the most sensitive tools in the system — they interact directly with the broker API to place and close orders with real financial consequences.

## Tools

### `place_order` — PlaceOrderTool

Submits a new trade order to the broker.

**Input:**
```json
{
  "pair": "EURUSD",
  "direction": "LONG",
  "order_type": "MARKET",
  "size": 1000,
  "stop_loss": 1.07900,
  "take_profit": 1.08600,
  "reasoning": "H1 EMA50 above EMA200, RSI 61, bullish structure"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pair` | string | ✓ | Currency pair (e.g. `"EURUSD"`) |
| `direction` | string | ✓ | `"LONG"` or `"SHORT"` |
| `order_type` | string | ✓ | `"MARKET"`, `"LIMIT"`, or `"STOP"` |
| `size` | number | ✓ | Order size in units |
| `price` | number | — | Entry price (LIMIT/STOP orders only) |
| `stop_loss` | number | — | Stop-loss price level |
| `take_profit` | number | — | Take-profit price level |
| `reasoning` | string | — | LLM's rationale (stored in DB) |

**Returns:**
```json
{
  "success": true,
  "entry_id": "ORDER_12345",
  "pair": "EURUSD",
  "direction": "LONG",
  "size": 1000,
  "entry_price": 1.08217,
  "stop_loss": 1.07900,
  "take_profit": 1.08600,
  "order_type": "MARKET",
  "timestamp": "2026-03-02T12:34:56Z"
}
```

**Approval mode:** Configurable (typically `"supervisor"` or `"direct"` depending on deployment)

---

### `close_position` — ClosePositionTool

Closes an existing open position.

**Input:**
```json
{
  "entry_id": "ORDER_12345",
  "close_reason": "MANUAL",
  "reasoning": "Momentum weakening after 4h in trade, exit recommended"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `entry_id` | string | ✓ | The order/position ID to close |
| `close_reason` | string | ✓ | `"MANUAL"`, `"TAKE_PROFIT"`, `"STOP_LOSS"`, `"TIMEOUT"`, `"RISK_BREACH"` |
| `reasoning` | string | — | LLM's explanation for closing |

**Returns:**
```json
{
  "success": true,
  "entry_id": "ORDER_12345",
  "pair": "EURUSD",
  "close_price": 1.08350,
  "realized_pnl": 13.30,
  "close_reason": "MANUAL",
  "close_time": "2026-03-02T14:15:00Z"
}
```

**Approval mode:** Configurable (typically `"supervisor"` or `"direct"`)

---

## Approval & Risk Gating

Trading tools go through multiple layers of safety checks before execution:

### Layer 1: Supervisor Approval (optional)
If `approval_mode = "supervisor"` is configured, the dispatcher publishes a `SIGNAL_GENERATED` event and waits (up to 15s) for `SIGNAL_APPROVED` or `SIGNAL_REJECTED`. The supervisor agent validates:
- Drawdown limits
- Maximum position count
- Pair correlation constraints
- Position sizing vs. risk parameters

### Layer 2: Context Budget Tiers
As the LLM's context fills up:
- At **80%** budget: `"decision"` tier — `place_order`, `close_position`, `raise_alarm` still available
- At **95%** budget: `"safety"` tier — only `close_position` and `raise_alarm` remain

This ensures that even when the context is nearly full, the agent can still exit dangerous positions.

### Layer 3: Broker Validation
The broker adapter performs its own validation (margin check, lot size limits, max position limits) before submitting to the exchange.

---

## Which Agents Use These Tools

Trading tools are **exclusively** in the Broker Agent's (BA) `allowed_tools` list. Analysis Agents (AA) are explicitly prohibited from calling these tools:

```
AA system prompt:
  "You do NOT execute trades.
   You must not call any broker execution tools.
   You are analysis-only."
```

This separation of concerns ensures that:
- AA agents cannot accidentally place trades
- All trade execution is centralised in the BA agent
- Risk checks are always applied before any order goes to the broker

---

## Reasoning Capture

The `reasoning` parameter is stored in the `order_book` database table alongside the trade. This creates an audit trail of **why** each trade was placed or closed, enabling post-mortem analysis, pattern detection, and prompt optimization.


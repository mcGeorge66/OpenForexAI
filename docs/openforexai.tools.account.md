[Back to Documentation Index](./README.md)

# tools/account — Account Tools

Tools that give agents visibility into the live account state: balance, equity, margin, and open positions.

## Tools

### `get_account_status` — GetAccountStatusTool

Returns the current account financial snapshot.

**Input:** *(no arguments required)*

**Returns:**
```json
{
  "broker": "OAPR1",
  "balance": 10000.00,
  "equity": 10034.21,
  "margin_used": 400.00,
  "margin_available": 9634.21,
  "nav": 10034.21,
  "open_positions": 1,
  "timestamp": "2026-03-02T12:34:56Z"
}
```

**Typical use:** Broker Agent (BA) calls this before placing an order to verify available margin and account health. Also used by the risk engine to assess drawdown.

**Approval mode:** `direct` — no supervisor check needed for read-only operations.

---

### `get_open_positions` — GetOpenPositionsTool

Returns a list of all currently open positions with full detail.

**Input:** *(no arguments required)*

**Returns:**
```json
[
  {
    "entry_id": "ORDER_12345",
    "pair": "EURUSD",
    "direction": "LONG",
    "size": 1000,
    "entry_price": 1.08210,
    "current_price": 1.08350,
    "unrealized_pnl": 14.00,
    "open_time": "2026-03-02T10:15:00Z",
    "broker": "OAPR1"
  }
]
```

**Typical use:** Broker Agent queries this to assess current exposure before opening new positions, and to identify positions that may need active management.

**Approval mode:** `direct`

---

## Which Agents Use These Tools

Both tools are in the default `allowed_tools` list for **Broker Agents** (BA):

```json
"allowed_tools": [
  "place_order",
  "close_position",
  "get_account_status",
  "get_open_positions",
  "get_order_book",
  "raise_alarm"
]
```

**Analysis Agents** (AA) do not need account visibility — they focus on market analysis only.

---

## Implementation Notes

Both tools delegate to the `AbstractBroker` interface (via `context.broker`). The live account data is fetched from the broker API, not from the local database. This ensures the information is always current, not stale.

The `BrokerBase._account_poll_loop()` runs in the background and publishes `ACCOUNT_STATUS_UPDATED` events every N seconds. These events are separate from the direct tool call — the tool always fetches fresh data on demand.


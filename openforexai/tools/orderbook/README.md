# tools/orderbook — Order Book Tools

Tools for accessing the order book state — pending orders and their positions relative to current price.

## Tools

### `get_order_book` — GetOrderBookTool

Returns the current order book entries for the agent's pair.

**Input:**
```json
{
  "pair": "EURUSD"
}
```

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `pair` | string | — | agent default | Currency pair |

**Returns:**
```json
[
  {
    "entry_id": "ORDER_12345",
    "pair": "EURUSD",
    "direction": "LONG",
    "size": 1000,
    "entry_price": 1.08210,
    "status": "OPEN",
    "stop_loss": 1.07900,
    "take_profit": 1.08600,
    "open_time": "2026-03-02T10:15:00Z"
  }
]
```

**Approval mode:** `direct`

---

## Order Book Synchronisation

The order book serves a dual purpose in OpenForexAI:

1. **Agent context**: The AA agent can query the order book to understand what positions are currently open when forming its analysis and trade management recommendations.

2. **Sync verification**: The system periodically cross-checks the local order book (stored in DB) against the broker's live state. Discrepancies trigger `ORDER_BOOK_SYNC_DISCREPANCY` events.

### Sync Discrepancy Flow

```
BrokerBase._sync_loop()
    │ compares DB order book with broker API
    │
    ├── Match: no action
    │
    └── Discrepancy detected:
          └── publishes ORDER_BOOK_SYNC_DISCREPANCY
                │
                ▼
          BA Agent (event_triggers includes "order_book_sync_discrepancy")
                │
                ▼
          Agent LLM decides: update DB record, reconcile position, raise alarm
```

The BA agent also handles `ORDER_BOOK_CLOSE_REASONING` events — when a position is closed externally (e.g., stop-loss hit at broker), the system asks the AA agent to provide a post-mortem analysis of why the position closed.

---

## Which Agents Use This Tool

`get_order_book` is available to both AA and BA agents:

- **AA agents**: Use it to understand active trade context when formulating bias and trade management recommendations
- **BA agents**: Use it to reconcile positions, detect sync discrepancies, and manage active trades

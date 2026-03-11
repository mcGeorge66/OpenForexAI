# adapters/brokers — Broker Adapters

Concrete implementations of `AbstractBroker` for supported forex brokers. Each adapter handles live market connectivity: candle streaming, order execution, account monitoring.

## Files

| File | Broker | Requirements |
|---|---|---|
| `__init__.py` | — | Self-registration |
| `base.py` | — | Shared background tasks |
| `oanda.py` | OANDA v20 REST | `oandapyV20` package |
| `mt5.py` | MetaTrader 5 | `MetaTrader5` package (Windows only) |

---

## `base.py` — BrokerBase

Abstract base class all broker adapters extend. Provides the background task infrastructure.

### Background Tasks

**`_m5_loop(pair)`**
Runs as an asyncio task. Every 5 minutes:
1. Calls `get_candles(pair, "M5", count=1)` for the latest bar
2. Publishes `M5_CANDLE_AVAILABLE` event to the EventBus
3. Sleeps until the next 5-minute boundary

Error handling:
- **Transient errors** (502/503/504, connection timeout): logged as `WARNING` without traceback, retried next cycle
- **Persistent errors**: logged as `ERROR` with full traceback

**`_account_poll_loop()`**
Runs as an asyncio task. Every N seconds (configurable):
1. Calls `get_account_status()`
2. Publishes `ACCOUNT_STATUS_UPDATED` event

### Candle Normalisation

`_normalize_candle(raw, pair, timeframe)` converts broker-specific raw data to the canonical `Candle` model. Each adapter overrides this for its own raw format.

---

## `oanda.py` — OANDA Adapter

Full implementation for the OANDA v20 REST API. Supports both **practice** (demo) and **live** accounts.

### Features

| Feature | API Endpoint |
|---|---|
| Candle fetching | `GET /instruments/{pair}/candles` |
| Market order | `POST /accounts/{id}/orders` |
| Limit/stop order | `POST /accounts/{id}/orders` |
| Close position | `PUT /accounts/{id}/trades/{id}/close` |
| Account status | `GET /accounts/{id}/summary` |
| Open positions | `GET /accounts/{id}/openTrades` |
| Order book | `GET /instruments/{pair}/orderBook` |

### Candle Timestamps

OANDA provides candle timestamps as the **open time** of the bar (e.g., an M5 candle at `12:05` covers `12:05–12:10`). The resampler in `data/resampler.py` is designed around this convention.

### Practice vs Live

Controlled by the `practice` config flag:
```json
{"practice": "true"}   # https://api-fxtrade.oanda.com → practice API
{"practice": "false"}  # https://api-fxtrade.oanda.com → live API
```

### Config Keys

```json
{
  "adapter": "oanda",
  "api_key": "${OANDA_API_KEY}",
  "account_id": "${OANDA_ACCOUNT_ID}",
  "practice": "${OANDA_PRACTICE:-true}",
  "short_name": "OAPR1",
  "pairs": ["EUR_USD", "GBP_USD", "USD_JPY"],
  "background_tasks": {
    "account_poll_interval_seconds": 60,
    "sync_interval_seconds": 60,
    "request_agent_reasoning": false
  }
}
```

OANDA uses underscore notation (`EUR_USD`). The adapter normalises to slash-free notation (`EURUSD`) internally.

### Rate Limiting

The OANDA API has rate limits (120 requests/minute for practice, 30/second for live). The adapter respects these with appropriate delays between M5 candle fetches.

### Shared background task keys

All broker modules can define:

```json
"background_tasks": {
  "account_poll_interval_seconds": 60,
  "sync_interval_seconds": 60,
  "request_agent_reasoning": false
}
```

These values are consumed in bootstrap and passed to `BrokerBase.start_background_tasks(...)`.

---

## `mt5.py` — MetaTrader 5 Adapter

Windows-only adapter using the `MetaTrader5` Python package (requires MT5 terminal installed and running).

### Limitations

- Windows only (the MT5 Python package does not support Linux/macOS)
- MT5 terminal must be running and logged in
- Latency depends on the MT5 terminal's connection to its broker

### Config Keys

```json
{
  "adapter": "mt5",
  "login": "${MT5_LOGIN}",
  "password": "${MT5_PASSWORD}",
  "server": "${MT5_SERVER}",
  "short_name": "MT5B1",
  "background_tasks": {
    "account_poll_interval_seconds": 60,
    "sync_interval_seconds": 60,
    "request_agent_reasoning": false
  }
}
```

---

## Adding a New Broker

1. Create `adapters/brokers/mybroker.py` subclassing `BrokerBase`:

```python
from openforexai.adapters.brokers.base import BrokerBase

class MyBroker(BrokerBase):

    @classmethod
    def from_config(cls, cfg: dict) -> "MyBroker":
        return cls(api_key=cfg["api_key"], short_name=cfg["short_name"])

    @property
    def short_name(self) -> str:
        return self._short_name

    async def get_candles(self, pair, timeframe, count) -> list[Candle]:
        # Call your broker's candle API
        ...

    async def place_order(self, order: TradeOrder) -> TradeResult:
        ...

    # Implement all other AbstractBroker methods
```

2. Register in `adapters/brokers/__init__.py`:
```python
PluginRegistry.register_broker("mybroker", MyBroker)
```

3. Create `config/modules/broker/mybroker.json5` and reference in `config/system.json5`.


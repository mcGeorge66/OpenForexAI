# Broker Adapter Templates

This folder contains templates and helper scripts for broker adapter development.

## Files

- `demo_broker_adapter.py`: Minimal broker adapter implementation example.
- `demo_broker_test.py`: Basic test patterns.
- `broker_adapter_manager.py`: Register/deregister/list broker adapters in the system.

## Adapter Contract

A broker adapter must implement `AbstractBroker` methods:
- `short_name` property
- `connect()`, `disconnect()`
- `fetch_latest_m5_candle()`, `get_historical_m5_candles()`
- `get_account_status()`
- `place_order()`, `close_position()`, `get_open_positions()`

Most adapters also expose `from_config(cfg)` for bootstrap instantiation.

## Where Information Comes From

1. Module config file under `config/modules/broker/*.json`
2. Runtime calls from the system loops (market data, account polling, sync, execution)
3. Trade/order models passed into adapter methods

## Where Information Goes

1. Returned `Candle`, `AccountStatus`, `TradeResult`, `Position` objects
2. EventBus messages via BrokerBase loop behavior (if using `BrokerBase`)
3. Monitoring events emitted by base loop or custom logic

## Adapter Manager Script

### Help (no parameters)
```bash
python template/broker/broker_adapter_manager.py
```

### List current registered broker adapters
```bash
python template/broker/broker_adapter_manager.py --list
```

### Register adapter
```bash
python template/broker/broker_adapter_manager.py \
  --register \
  --name mybroker \
  --source-file template/broker/demo_broker_adapter.py \
  --class-name DemoBrokerAdapter
```

Effects:
- Copies file into `openforexai/adapters/brokers/`
- Adds import line in `openforexai/adapters/brokers/__init__.py`
- Adds `PluginRegistry.register_broker("<name>", <Class>)`

### Deregister adapter
```bash
python template/broker/broker_adapter_manager.py --deregister --name mybroker
```

Effects:
- Removes registration lines from `openforexai/adapters/brokers/__init__.py`
- Moves adapter file back into `template/broker/`

## Development Workflow (Idea -> Production)

1. Define scope:
- Broker API capabilities, supported order types, rate limits, auth model.

2. Design:
- Map broker payloads to canonical models (`Candle`, `TradeOrder`, `TradeResult`, `Position`).
- Define error strategy and reconnect behavior.

3. Implement:
- Start from `demo_broker_adapter.py`.
- Add `from_config` and strict config validation.

4. Test locally:
```bash
pytest template/broker/demo_broker_test.py -q
```
- Add tests for order placement, close flow, and error handling.

5. Register in system:
- Use `broker_adapter_manager.py`.
- Add module config in `config/modules/broker/`.
- Reference module in `config/system.json -> modules.broker`.

6. Safe rollout:
- Run in test/practice mode first.
- Observe monitoring stream for errors/disconnects.
- Validate order-book sync and reconciliation behavior.

7. Production monitoring:
- Track connection stability, candle timeliness, fill success, and sync discrepancies.
- Keep rollback simple by switching broker module config back.


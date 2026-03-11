# Data Adapter Templates

This folder contains templates and helper scripts for data container adapter development.

## Files

- `demo_data_adapter.py`: Example adapter extending `SQLiteDataContainer`.
- `demo_data_test.py`: Basic startup test pattern.
- `data_adapter_manager.py`: Register/deregister/list data adapters in the system.

## Adapter Contract

Data adapters are concrete implementations of `AbstractDataContainer` and are
registered in `PluginRegistry` under the database backend key.

In this codebase, data adapters are located under `openforexai/adapters/data/`.

## Information Flow

Inputs:
1. Backend settings from `config/system.json -> database`
2. Repository/data-container method calls from agents, tools, and orchestration
3. Domain models (candles, trades, decisions, conversations, metrics)

Outputs:
1. Persistent storage writes/reads
2. Full historical retrieval for analysis and optimization
3. Restart-safe recovery state

## Data Adapter Manager Script

### Help (no parameters)
```bash
python template/data/data_adapter_manager.py
```

### List registered data adapters
```bash
python template/data/data_adapter_manager.py --list
```

### Register data adapter
```bash
python template/data/data_adapter_manager.py \
  --register \
  --name demo_data \
  --source-file template/data/demo_data_adapter.py \
  --class-name DemoDataContainer
```

Effects:
- Copies file to `openforexai/adapters/data/`
- Adds import to `openforexai/adapters/data/__init__.py`
- Adds both:
  - `PluginRegistry.register_data_container(...)`
  - `PluginRegistry.register_repository(...)` (backward compatibility)

### Deregister data adapter
```bash
python template/data/data_adapter_manager.py --deregister --name demo_data
```

Effects:
- Removes import and both registry lines from `openforexai/adapters/data/__init__.py`
- Moves adapter file back into `template/data/`

## Development Workflow (Idea -> Production)

1. Define requirements:
- data volume, durability, query patterns, recovery expectations.

2. Design:
- choose extension strategy (extend existing adapter vs full new backend).
- define transaction/commit semantics and migration approach.

3. Implement:
- start with `demo_data_adapter.py`.
- keep writes restart-safe and preserve full reasoning/conversation payloads.

4. Test:
```bash
pytest template/data/demo_data_test.py -q
```
- add tests for CRUD, migration compatibility, and performance-critical queries.

5. Register and configure:
- register adapter via manager script.
- set backend key in `config/system.json -> database.backend`.

6. Controlled rollout:
- run on staging or paper mode first.
- validate data consistency and restart recovery.

7. Monitored production:
- track write/read latency, DB growth, integrity errors, and migration health.
- keep rollback path available (switch backend key + stable migration state).


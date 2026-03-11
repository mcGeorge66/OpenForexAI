[Back to README](./README.md)

# Setup

This document contains environment configuration, installation, startup, and module-level smoke tests.

## Configuration

### `config/system.json5` — central config

One file contains everything: all agents, their tools, prompts, timers, and module
references. The system reads only this file at startup.

```json
{
  "system": {
    "log_level": "INFO",
    "management_api": {"host": "127.0.0.1", "port": 8765}
  },
  "database": {
    "backend": "sqlite",
    "sqlite_path": "${OPENFOREXAI_DB_PATH:-./data/openforexai.db}"
  },
  "modules": {
    "llm":    {"anthropic_claude": "config/modules/llm/anthropic_claude.json5"},
    "broker": {"oanda": "config/modules/broker/oanda.json5"}
  },
  "agents": {
    "OANDA_EURUSD_AA_ANLYS": {
      "type": "AA",
      "llm": "anthropic_claude",
      "broker": "oanda",
      "pair": "EURUSD",
      "timer": {"enabled": true, "interval_seconds": 300},
      "event_triggers": ["m5_candle_available", "prompt_updated"],
      "system_prompt": "You are a professional Forex analysis agent for EURUSD...",
      "tool_config": { ... }
    }
  }
}
```

All string values support `${VAR_NAME}` and `${VAR_NAME:-default}` env-var substitution.

### Module configs

```
config/
├── system.json5                      ← main config
├── modules/
│   ├── llm/
│   │   └── anthropic_claude.json5    ← LLM credentials + settings
│   └── broker/
│       ├── oanda.json5               ← OANDA credentials
│       └── mt5.json5                 ← MT5 credentials
└── event_routing.json5               ← routing rules (hot-reloadable)
```

### Environment variables

Set credentials in a `.env` file or export directly:
(These are examples, the environment variables depends on your broker and LLM provider.)

```bash
ANTHROPIC_API_KEY=sk-ant-...
OANDA_API_KEY=...
OANDA_ACCOUNT_ID=101-001-...
OPENFOREXAI_LOG_LEVEL=INFO         # optional
OPENFOREXAI_DB_PATH=./data/db.sqlite  # optional
MANAGEMENT_API_KEY=secret          # optional, enables API auth
```

---

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/GeorgGebert/OpenForexAI.git
cd OpenForexAI

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[api]"     # core + FastAPI management server

# Optional extras:
pip install -e ".[mt5]"     # MetaTrader 5 (Windows only)
pip install -e ".[dev]"     # pytest, ruff, mypy
pip install -e ".[all]"     # everything
```

---

## Quick start

```bash
# 1. Set credentials
export ANTHROPIC_API_KEY=sk-ant-...
export OANDA_API_KEY=...
export OANDA_ACCOUNT_ID=101-001-...

# 2. Run database migrations
python scripts/db_migrate.py

# 3. Start the system
openforexai
# or: python -m openforexai.main
```

The system will:
- Load `config/system.json5`
- Start all configured agents (they each request their own config via the EventBus)
- Start broker background tasks (M5 streaming, account poll, sync)
- Start the Management API on `localhost:8765`
- Start the ConfigService

In a second terminal, open the live monitor:

```bash
python tools/monitor.py
```

---

## Module tests

Test an LLM or broker module independently — no full system startup needed:

```bash
-> in the tools folder

# Test LLM connectivity and tool-use
python test_llm.py anthropic_claude

# Test broker connectivity, account status, and candle fetching
python test_broker.py oanda
```

Both scripts exit with code `0` on success, `1` on failure.

---

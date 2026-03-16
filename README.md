# OpenForexAI

**Autonomous multi-agent LLM-based forex trading system**

OpenForexAI uses configurable AI agents for market analysis, risk-aware trade execution, and strategy optimization.

> [!NOTE]
> Here some interesting [`Screenshots`](Screenshots.md) 


![Status](https://img.shields.io/badge/status-beta-orange)
![Safety](https://img.shields.io/badge/trading-practice%20only-red)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Architecture](https://img.shields.io/badge/architecture-multi--agent-teal)

## Project Status

> [!WARNING]
> This project is in **beta**.  
> Do not run with unattended real-money trading.

- The system is not yet considered production-ready.
- LLMs can make mistakes; autonomous execution can cause significant losses.
- Use practice/demo environments first.

## Documentation Map

**Getting Started**
- Setup, configuration, installation, quick start: [`setup.md`](./setup.md)
- Detailed package/module documentation: [`docs/README.md`](./docs/README.md)

**Project Internals**
- Architecture and runtime design: [`architecture.md`](./architecture.md)
- Developer-oriented reference (tests, layout, stack): [`developer.md`](./developer.md)

**Contributing**
- Contribution baseline and process template: [`CONTRIBUTING.md`](./CONTRIBUTING.md)

## Quick Start (Part 1)

Release packages and tags are available here: [https://github.com/mcGeorge66/OpenForexAI/releases](https://github.com/mcGeorge66/OpenForexAI/releases)

```bash
# You have to be in the install folder for preperation.

python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -e ".[all]"

# Prepare the frontend
cd ui
npm install
npm run build
cd ..
```

### First-Time Configuration and Validation

1. Configure at least one broker module in `config/modules/broker/*.json5` and reference it in `config/system.json5` under `modules.broker`.
2. Configure at least one LLM module in `config/modules/llm/*.json5` and reference it in `config/system.json5` under `modules.llm`.
3. Set required credentials via environment variables or `.env`.
4. Validate broker connectivity:

```bash
python tools/test_broker.py <broker_module_name> <PAIR>
# example
python tools/test_broker.py oanda EURUSD
```

5. Validate LLM connectivity:

```bash
python tools/test_llm.py <llm_module_name>
# example
python tools/test_llm.py azure_openai
```

6. Start the app:

```bash
python tools/openforexai-wrapper.py
```

Notes:
- SQLite is created automatically on startup (default setup).
- If you use broker/LLM modules, ensure required credentials are set in your environment or `.env`.
- For the UI button `Restart now`, start via `tools/openforexai-wrapper.py`.
- If you run under an external supervisor (e.g. `systemd`/service manager), start directly without wrapper; in that mode the UI `Restart now` option is hidden and restart is managed by the supervisor.

## Quick Start (Part 2)

```bash
# You have to be in the install folder for starting the system

# Recommended start mode (enables controlled restart from UI)
python tools/openforexai-wrapper.py

# Alternative direct start (without wrapper supervision)
# python -m openforexai.main
```

## Why This Project Exists

This project started from a simple observation: in Forex trading, discipline and risk management are often harder than analysis itself.  
The core idea was to let an LLM-based system apply rules consistently without emotional pressure, then expand it into a modular multi-agent platform.

OpenForexAI is designed to be highly configurable:
- flexible agent behavior via config
- adapter/plugin architecture for brokers, LLMs, and tools
- support for users with and without direct broker API access (including MT5 integration)

## Help Wanted

To move the project from beta to a robust production-grade platform, contributions are welcome in:
- prompt engineering and evaluation workflows
- testing (especially end-to-end reliability)
- adapters/plugins and interoperability
- bug fixing and documentation

> **Disclaimer:** This software is provided for educational and research purposes.
> Forex trading involves substantial risk of loss. Always test with a practice
> account before connecting real funds. The authors are not responsible for any
> financial losses incurred through the use of this software.

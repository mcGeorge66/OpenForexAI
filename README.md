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


## Installation

Release packages and tags are available here: [https://github.com/mcGeorge66/OpenForexAI/releases](https://github.com/mcGeorge66/OpenForexAI/releases)

Setup Instruction: [`SETUP`](./setup.md)

## Quick Start

Release packages and tags are available here: [https://github.com/mcGeorge66/OpenForexAI/releases](https://github.com/mcGeorge66/OpenForexAI/releases)

Recommended first-time setup:

Windows:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
```

Linux:
```bash
bash scripts/setup_linux.sh
```

The setup script will:
- install backend and UI dependencies
- discover broker/LLM adapters dynamically and create module files as `<adapter>.<name>.json5`
- create `config/system.json5` with selected broker/LLM module references
- scan selected module config files for `${...}` placeholders
- collect required environment values into `.env`
- create startup scripts
- optionally run broker/LLM smoke tests

Detailed guide (automated + manual): [`setup.md`](./setup.md)

Regular start after setup:

Windows:
```powershell
./start_openforexai.ps1
```

Linux:
```bash
./start_openforexai.sh
```

Notes:
- SQLite is created automatically on startup (default setup).
- For the UI button `Restart now`, start via wrapper-based scripts above.
- If you run under an external supervisor (e.g. `systemd`/service manager), start directly without wrapper; in that mode the UI `Restart now` option is hidden and restart is managed by the supervisor.

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




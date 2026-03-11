# OpenForexAI

**Autonomous multi-agent LLM-based forex trading system**

OpenForexAI uses configurable AI agents for market analysis, risk-aware trade execution, and strategy optimization.

## Documentation Map

- Architecture and runtime design: [`architecture.md`](./architecture.md)
- Setup, configuration, installation, quick start: [`setup.md`](./setup.md)
- Developer-oriented reference (tests, layout, stack): [`developer.md`](./developer.md)
- Contribution baseline and process template: [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- Detailed package/module documentation: [`docs/README.md`](./docs/README.md)

## Quick Start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -e ".[all]"
python -m openforexai.main
```

> **Disclaimer:** This software is provided for educational and research purposes.
> Forex trading involves substantial risk of loss. Always test with a practice
> account before connecting real funds. The authors are not responsible for any
> financial losses incurred through the use of this software.

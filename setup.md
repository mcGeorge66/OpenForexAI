[Back to README](./README.md)

# SETUP

This guide is for first-time users and production-like installs.

It has two parts:
- **Part A (recommended):** run setup scripts (`setup_windows` / `setup_linux`).
- **Part B (manual):** do the same steps by hand (and understand what the scripts do internally).

## Before You Start

Collect this information first:
- Which broker adapter(s) you need (for example `oanda`, `mt5`).
- Which LLM adapter(s) you need (for example `anthropic`, `azure`, `openai`, `lmstudio`, `ollama`).
- Credentials and account information for selected providers.
- One test pair (for example `EURUSD`) for connectivity checks.

Minimum startup requirement:
- At least one entry in `modules.llm` and one entry in `modules.broker` in `config/system.json5`.

---

## Part A: Automated Setup (Recommended)

### 1. Prerequisites

Windows:
- Python 3.11+
- Node.js + npm
- Git
- PowerShell

Linux:
- Python 3.11+
- Node.js + npm
- Git
- bash

### 2. Run the setup script

Windows:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
```

Linux:
```bash
bash scripts/setup_linux.sh
```

### 3. What the setup script does

The script performs these steps (interactive terminal wizard via rich + questionary):
1. Checks required tools (`python`, `git`, `npm`).
2. Creates/updates virtual environment and installs Python dependencies.
3. Builds the UI (`npm install`, `npm run build`).
4. Discovers supported adapters dynamically from code:
   - `openforexai/adapters/brokers/`
   - `openforexai/adapters/llm/`
5. Reads adapter metadata from:
   - `config/modules/broker/<adapter>.meta.json5`
   - `config/modules/llm/<adapter>.meta.json5`
6. For each selected adapter, asks for a config name and creates module config from sample:
   - source: `config/modules/<kind>/<adapter>.sample.json5`
   - target: `config/modules/<kind>/<adapter>.<config_name>.json5`
7. Writes selected module references into `config/system.json5` under:
   - `modules.llm`
   - `modules.broker`
8. Scans selected module config files for `${...}` placeholders.
9. Prompts missing values and writes them to local `.env`.
10. Creates start scripts:
   - Windows: `start_openforexai.ps1` and `start_openforexai.cmd`
   - Linux: `start_openforexai.sh`
11. Optionally runs smoke tests:
   - `python tools/test_broker.py <broker_module_name> <PAIR>`
   - `python tools/test_llm.py <llm_module_name>`
12. Optionally starts OpenForexAI.

### 4. After automated setup

Start command:
- Windows: `./start_openforexai.ps1`
- Linux: `./start_openforexai.sh`

If startup is blocked, verify:
- `config/system.json5` contains at least one broker and one LLM module reference.
- `.env` contains all required credentials for selected modules.

---

## Part B: Manual Setup (Same Steps by Hand)

Use this if you want full control or to debug setup issues.

### 1. Create environment and install dependencies

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -e ".[all]"
```

### 2. Build UI

```bash
cd ui
npm install
npm run build
cd ..
```

### 3. Choose adapters and create module config files

For each selected adapter:
1. Start from `<adapter>.sample.json5`.
2. Copy to `<adapter>.<config_name>.json5`.

Examples:
- `config/modules/broker/mt5.sample.json5` -> `config/modules/broker/mt5.oxs_t.json5`
- `config/modules/llm/azure.sample.json5` -> `config/modules/llm/azure.main.json5`

### 4. Create custom config `config/system.json5`

Do **not** modify `config/config.default.json5`.

Create `config/system.json5` and reference your created module files:

```json5
{
  modules: {
    llm: {
      azure_main: "config/modules/llm/azure.main.json5"
    },
    broker: {
      mt5_oxs_t: "config/modules/broker/mt5.oxs_t.json5"
    }
  }
}
```

### 5. Configure secrets in `.env`

Read each selected module file and set all required `${...}` values in `.env`.

### 6. Validate selected modules

```bash
python tools/test_broker.py <broker_module_name> <PAIR>
python tools/test_llm.py <llm_module_name>
```

Example:

```bash
python tools/test_broker.py mt5_oxs_t EURUSD
python tools/test_llm.py azure_main
```

### 7. Start the app

```bash
python tools/openforexai-start.py
```

or platform script:
- Windows: `./start_openforexai.ps1`
- Linux: `./start_openforexai.sh`

---

## Troubleshooting

### Startup says broker/LLM missing
- Check `config/system.json5` -> `modules.llm` and `modules.broker` are both non-empty.

### Adapter not shown in setup
- Verify adapter is registered in:
  - `openforexai/adapters/brokers/__init__.py` or
  - `openforexai/adapters/llm/__init__.py`
- Verify sample file exists as `<adapter>.sample.json5` in matching config module folder.

### LLM test fails
- Verify endpoint/model/deployment values in selected LLM module config.
- Check all required API key env vars in `.env`.

### Broker test fails
- Verify broker credentials and account parameters.
- For MT5, confirm terminal installation and account connectivity.





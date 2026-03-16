[Back to Documentation Index](./README.md)

# UI (Web Console)

The web console is the operational frontend for OpenForexAI. It connects to the Management API (`http://127.0.0.1:8765`) and is used to operate agents, monitor runtime behavior, test tools/LLMs, and manage configuration.

## Main Navigation

- `Action` — agent interaction and system startup overview
- `Test` — `Tool Executor` and `LLM Checker`
- `Config` — system/config/module editors and wizards
- `Monitor` — event streams (`All`, `LLM`, `Tool`, `Bus`, `Data`, `Broker`)

## Initial Page (Action)

The **Initial** page shows:

- startup logo
- local and internet version
- broker/LLM connectivity status
- configured/enabled agents overview
- updater/runtime status log

### Runtime Controls

Buttons in the Version box:

- `Update` — starts release update (`POST /system/update/start`)
- `Suspend` / `Continue` — pauses/resumes runtime loops (`POST /system/runtime/pause`, `POST /system/runtime/resume`)
- `Restart now` — immediate application restart (`POST /system/restart-now`)

Update progress is shown via `GET /system/update/status` and the update log panel.

## Restart Behavior

There are two restart paths:

1. Wrapper mode (recommended): `tools/openforexai-wrapper.py`
   - API writes a restart signal file.
   - Wrapper terminates and relaunches the child process.

2. Fallback mode (no wrapper):
   - API performs a best-effort self-spawn restart path.

For controlled restarts, start OpenForexAI via the wrapper.

## Related API Endpoints

- `GET /console/initial`
- `GET /system/update/status`
- `POST /system/update/start`
- `POST /system/runtime/pause`
- `POST /system/runtime/resume`
- `POST /system/restart-now`

## Operational Notes

- `Suspend` pauses broker polling/M5 loops and agent timer/event processing without exiting the app.
- `Continue` resumes normal runtime processing.
- `Restart now` interrupts active processing and performs a fresh startup cycle.
- For verification, use `Monitor > All Events` and the Initial page status cards/log panel.

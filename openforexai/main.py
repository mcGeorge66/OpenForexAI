from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openforexai.agents.agent import Agent
from openforexai.bootstrap import bootstrap
from openforexai.config.json_loader import load_json_config
from openforexai.management.server import ManagementServer
from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.monitoring.bus import MonitoringBus
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.utils.logging import configure_logging, get_logger

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "system.json5"
_log = get_logger("main")

class StartupConfigurationError(RuntimeError):
    """Raised when mandatory runtime configuration is missing."""


_BANNER = r"""
+-------------------------------------------------------------+
|   ___                   _____                    _    ___   |
|  / _ \ _ __   ___ _ __ |  ___|__  _ __ _____  _ / \  |_ _|  |
| | | | | '_ \ / _ \ '_ \| |_ / _ \| '__/ _ \ \/ / _ \  | |   |
| | |_| | |_) |  __/ | | |  _| (_) | | |  __/>  < ___ \ | |   |
|  \___/| .__/ \___|_| |_|_|  \___/|_|  \___/_/\_\_/ \_\___|  |
|       |_|                                                   |
+-------------------------------------------------------------+
"""


def _print_start_banner() -> None:
    print(_BANNER)
    print("Starting OpenForexAI...")


def _module_names(cfg: dict[str, Any], section: str) -> list[str]:
    modules = cfg.get("modules", {})
    section_cfg = modules.get(section, {}) if isinstance(modules, dict) else {}
    if not isinstance(section_cfg, dict):
        return []
    return sorted(str(name) for name in section_cfg.keys())


def _log_preflight(cfg: dict[str, Any]) -> None:
    llm_names = _module_names(cfg, "llm")
    broker_names = _module_names(cfg, "broker")
    _log.info(
        "Preflight configuration",
        config=str(_CONFIG_PATH),
        llm_modules=len(llm_names),
        llm_names=llm_names,
        broker_modules=len(broker_names),
        broker_names=broker_names,
    )


def _log_runtime_ready(agents: list[Agent], connected_brokers: dict[str, Any]) -> None:
    broker_labels: list[str] = []
    for name, broker in connected_brokers.items():
        short_name = str(getattr(broker, "short_name", "")).strip() or "(no short_name)"
        broker_labels.append(f"{name}:{short_name}")
    broker_labels.sort()

    _log.info(
        "Preflight OK. Entering runtime mode",
        connected_brokers=len(connected_brokers),
        brokers=broker_labels,
        agents_enabled=len(agents),
    )


def _ensure_required_modules(cfg: dict) -> None:
    """Fail fast if mandatory module groups are not configured."""
    modules = cfg.get("modules", {})
    llm_modules = modules.get("llm", {}) if isinstance(modules, dict) else {}
    broker_modules = modules.get("broker", {}) if isinstance(modules, dict) else {}

    has_llm = isinstance(llm_modules, dict) and len(llm_modules) > 0
    has_broker = isinstance(broker_modules, dict) and len(broker_modules) > 0
    if has_llm and has_broker:
        return

    raise StartupConfigurationError(
        "Startup blocked: Please configure at least one LLM and one Broker module before starting OpenForexAI.\n"
        "Required config paths:\n"
        "- modules.llm\n"
        "- modules.broker\n\n"
        "Then test them with:\n"
        "- python tools/test_broker.py <broker_module_name> <PAIR>\n"
        "- python tools/test_llm.py <llm_module_name>"
    )


def _install_windows_asyncio_workarounds() -> None:
    """Avoid noisy Proactor transport resets on Windows (WinError 10054)."""
    if sys.platform != "win32":
        return

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def _run_agent_safe(agent: Agent, monitoring_bus: MonitoringBus) -> None:
    """Run agent.start(), catching all exceptions."""
    try:
        await agent.start()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log.exception("Agent task crashed", agent_id=agent.agent_id, error=str(exc))
        try:
            monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{agent.agent_id}",
                event_type=MonitoringEventType.SYSTEM_ERROR,
                payload={
                    "agent_id": agent.agent_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            ))
        except Exception:
            pass


async def main() -> None:
    cfg = load_json_config(_CONFIG_PATH)
    _ensure_required_modules(cfg)
    sys_cfg = cfg.get("system", {})
    configure_logging(sys_cfg.get("log_level", "INFO"))

    _log.info("Starting OpenForexAI", config=str(_CONFIG_PATH))
    _log_preflight(cfg)

    monitoring_bus = MonitoringBus()

    agents, config_service, bus, data_container, repository, connected_brokers = await bootstrap(
        cfg, monitoring_bus=monitoring_bus
    )
    _log_runtime_ready(agents, connected_brokers)

    api_cfg = sys_cfg.get("management_api", {})
    mgmt_server = ManagementServer(
        bus=bus,
        routing_table=bus._routing,
        tool_registry=DEFAULT_REGISTRY,
        monitoring_bus=monitoring_bus,
        system_config=cfg,
        data_container=data_container,
        repository=repository,
        connected_brokers=connected_brokers,
        config_service=config_service,
        host=api_cfg.get("host", "127.0.0.1"),
        port=api_cfg.get("port", 8765),
    )

    async with asyncio.TaskGroup() as tg:
        tg.create_task(bus.start_dispatch_loop(), name="event-bus")
        tg.create_task(config_service.run(), name="config-service")
        tg.create_task(mgmt_server.serve(), name="mgmt-api")
        for agent in agents:
            tg.create_task(
                _run_agent_safe(agent, monitoring_bus),
                name=agent.agent_id,
            )


def run() -> None:
    """Entry point for the ``openforexai`` console script."""
    _install_windows_asyncio_workarounds()
    _print_start_banner()
    try:
        asyncio.run(main())
    except StartupConfigurationError as exc:
        print(str(exc))
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("\nOpenForexAI stopped.")
        os._exit(0)


if __name__ == "__main__":
    run()

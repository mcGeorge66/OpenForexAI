from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import json5
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
SYSTEM_CFG = CONFIG_DIR / "system.json5"
ENV_FILE = ROOT / ".env"

BROKER_MODULE_DIR = ROOT / "config" / "modules" / "broker"
LLM_MODULE_DIR = ROOT / "config" / "modules" / "llm"

BROKER_REGISTRY_FILE = ROOT / "openforexai" / "adapters" / "brokers" / "__init__.py"
LLM_REGISTRY_FILE = ROOT / "openforexai" / "adapters" / "llm" / "__init__.py"

PLACEHOLDER_RE = re.compile(r"\$\{\s*([A-Za-z0-9_.\-]+)\s*(?::-\s*([^}]*?)\s*)?\}")
BROKER_REG_RE = re.compile(r'register_broker\("([^\"]+)"\s*,')
LLM_REG_RE = re.compile(r'register_llm_provider\("([^\"]+)"\s*,')

console = Console()


@dataclass
class AdapterInfo:
    key: str
    kind: str
    sample_path: Path
    meta_path: Path
    display_name: str
    description: str
    notes: str
    placeholders: list[str]
    placeholder_debug: str

def _clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _step(title: str, idx: int, total: int) -> None:
    _clear_screen()
    console.rule(f"[bold cyan]Step {idx}/{total}[/bold cyan] {title}")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _discover_adapters(kind: str) -> list[str]:
    if kind == "broker":
        text = _read_text(BROKER_REGISTRY_FILE)
        return sorted(set(BROKER_REG_RE.findall(text)))
    text = _read_text(LLM_REGISTRY_FILE)
    return sorted(set(LLM_REG_RE.findall(text)))


def _module_dir_for(kind: str) -> Path:
    return BROKER_MODULE_DIR if kind == "broker" else LLM_MODULE_DIR


def _ensure_sample(kind: str, adapter: str) -> Path:
    module_dir = _module_dir_for(kind)
    canonical = module_dir / f"{adapter}.sample.json5"
    legacy_dash = module_dir / f"{adapter}-sample.json5"
    if canonical.exists():
        return canonical
    if legacy_dash.exists():
        shutil.copyfile(legacy_dash, canonical)
        return canonical
    return canonical


def _meta_path(kind: str, adapter: str) -> Path:
    return _module_dir_for(kind) / f"{adapter}.meta.json5"


def _extract_placeholders(path: Path) -> dict[str, str | None]:
    if not path.exists():
        return {}

    placeholders: dict[str, str | None] = {}
    text = path.read_text(encoding="utf-8")
    for match in PLACEHOLDER_RE.finditer(text):
        name = match.group(1).strip()
        default_raw = match.group(2)
        default = default_raw.strip() if default_raw is not None else None
        if name not in placeholders:
            placeholders[name] = default
    return placeholders


def _parse_placeholders(path: Path) -> tuple[list[str], str]:
    placeholders = _extract_placeholders(path)
    if not placeholders:
        return [], f"searched_file={path}\nregex={PLACEHOLDER_RE.pattern}\nmatch_count=0\nraw_matches=[]"

    entries: dict[str, str] = {}
    for name, default in placeholders.items():
        default_text = "" if default is None else default
        entries[name] = f"{name} (default: {default_text})" if default is not None else name

    debug = (
        f"searched_file={path}\n"
        f"regex={PLACEHOLDER_RE.pattern}\n"
        f"match_count={len(placeholders)}\n"
        f"raw_matches={list(placeholders.items())[:12]}"
    )
    return [entries[k] for k in sorted(entries.keys())], debug

def _load_meta(path: Path, adapter: str) -> dict[str, str]:
    # Meta-only mode: no hardcoded adapter-specific defaults.
    default = {"display_name": adapter, "description": "", "notes": ""}

    if not path.exists():
        return default

    try:
        raw = json5.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            console.print(f"[yellow]Warning:[/yellow] invalid meta format: {path}")
            return default

        out = dict(default)
        for key in ("display_name", "description", "notes"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                out[key] = value.strip()
        return out
    except Exception:
        console.print(f"[yellow]Warning:[/yellow] failed to parse meta file: {path}")
        return default


def _collect_adapter_infos(kind: str) -> list[AdapterInfo]:
    out: list[AdapterInfo] = []
    for adapter in _discover_adapters(kind):
        sample = _ensure_sample(kind, adapter)
        if not sample.exists():
            console.print(f"[yellow]Warning:[/yellow] missing sample for {kind} adapter '{adapter}': {sample}")
            continue

        meta = _meta_path(kind, adapter)
        meta_cfg = _load_meta(meta, adapter)

        placeholders, placeholder_debug = _parse_placeholders(sample)
        out.append(
            AdapterInfo(
                key=adapter,
                kind=kind,
                sample_path=sample,
                meta_path=meta,
                display_name=meta_cfg["display_name"],
                description=meta_cfg["description"],
                notes=meta_cfg["notes"],
                placeholders=placeholders,
                placeholder_debug=placeholder_debug,
            )
        )
    return out


def _render_adapter_table(kind: str, infos: list[AdapterInfo]) -> None:
    table = Table(title=f"Available {kind} adapters", show_lines=True, expand=True)
    table.add_column("Key", style="cyan", no_wrap=True, width=8)
    table.add_column("Display", width=22)
    table.add_column("Description", overflow="fold", min_width=30, max_width=50)
    table.add_column("Required placeholders", style="white", overflow="fold", min_width=34)

    for info in infos:
        placeholders = (
            "\n".join(info.placeholders)
            if info.placeholders
            else f"(none)\n{info.placeholder_debug}"
        )
        table.add_row(info.key, info.display_name, info.description or "-", placeholders)

    console.print(table)


def _select_adapters(kind: str, infos: list[AdapterInfo]) -> list[AdapterInfo]:
    if not infos:
        return []

    _render_adapter_table(kind, infos)
    choices = [questionary.Choice(title=i.key, value=i.key) for i in infos]
    selected = questionary.checkbox(
        f"Select one or more {kind} adapters",
        choices=choices,
        validate=lambda a: True if a else f"Select at least one {kind} adapter",
    ).ask()

    if not selected:
        return []

    mapping = {i.key: i for i in infos}
    return [mapping[k] for k in selected if k in mapping]


def _load_existing_modules() -> tuple[dict[str, str], dict[str, str]]:
    if not SYSTEM_CFG.exists():
        return {}, {}
    try:
        raw = json5.loads(SYSTEM_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}
    modules = raw.get("modules", {}) if isinstance(raw, dict) else {}
    if not isinstance(modules, dict):
        return {}, {}
    llm = modules.get("llm", {}) if isinstance(modules.get("llm", {}), dict) else {}
    broker = modules.get("broker", {}) if isinstance(modules.get("broker", {}), dict) else {}
    llm_out = {str(k): str(v) for k, v in llm.items()}
    broker_out = {str(k): str(v) for k, v in broker.items()}
    return broker_out, llm_out


def _read_adapter_from_module_file(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = json5.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    adapter = data.get("adapter")
    return str(adapter).strip() if isinstance(adapter, str) and adapter.strip() else None


def _ask_existing_actions(kind: str, existing: dict[str, str]) -> tuple[bool, bool]:
    if not existing:
        return False, True
    existing_list = ", ".join(sorted(existing.keys()))
    console.print(f"\n[cyan]Found existing {kind} modules in system.json5:[/cyan] {existing_list}")
    reconfigure = Confirm.ask(f"Reconfigure existing {kind} modules?", default=False)
    add_additional = Confirm.ask(f"Add additional {kind} modules?", default=not reconfigure)
    return reconfigure, add_additional


def _select_existing_module_keys(kind: str, existing: dict[str, str]) -> list[str]:
    if not existing:
        return []
    choices = [questionary.Choice(title=f"{k} -> {v}", value=k) for k, v in sorted(existing.items())]
    selected = questionary.checkbox(
        f"Select existing {kind} modules to reconfigure",
        choices=choices,
        validate=lambda a: True if a else f"Select at least one existing {kind} module",
    ).ask()
    return selected or []


def _materialize_existing_modules(
    kind: str,
    existing_module_map: dict[str, str],
    selected_keys: list[str],
    adapter_infos_by_key: dict[str, AdapterInfo],
    non_secret_values: dict[str, str],
) -> list[Path]:
    touched_paths: list[Path] = []
    for module_key in selected_keys:
        rel = existing_module_map.get(module_key)
        if not rel:
            continue
        target = ROOT / rel
        adapter_key = _read_adapter_from_module_file(target)
        if not adapter_key:
            console.print(f"[yellow]Skip[/yellow] {module_key}: adapter not readable from {target}")
            continue
        info = adapter_infos_by_key.get(adapter_key)
        if info is None:
            console.print(f"[yellow]Skip[/yellow] {module_key}: adapter {adapter_key!r} not discovered")
            continue

        placeholders = _extract_placeholders(info.sample_path)
        static_values: dict[str, str] = {}
        non_secret_items = [(n, d) for n, d in sorted(placeholders.items()) if not _is_secret_key(n)]
        if non_secret_items:
            console.print(f"\n[cyan]Static values for {kind} config: {module_key}[/cyan]")
        for name, default in non_secret_items:
            static_values[name] = _ask_non_secret_value(name, default, non_secret_values)

        rendered = _render_module_config_from_sample(info.sample_path, static_values)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        console.print(f"[green]Written[/green] {target}")
        touched_paths.append(target)
    return touched_paths


def _ask_config_suffix(kind: str, adapter: str) -> str:
    while True:
        value = questionary.text(
            f"Config name for {kind} '{adapter}' (example: prod, demo, oxs_t)",
            validate=lambda t: bool(t.strip()) and bool(re.fullmatch(r"[A-Za-z0-9_\-]+", t.strip())),
        ).ask()
        if value:
            return value.strip()


def _ask_non_secret_value(name: str, default: str | None, cache: dict[str, str]) -> str:
    existing = cache.get(name)
    if existing is not None and existing != "":
        if Confirm.ask(f"Reuse existing value for {name}:", default=True):
            return existing

    default_value = "" if default is None else default
    while True:
        value = questionary.text(f"{name}:", default=default_value).ask()
        value = (value or "").strip()
        if value or default is not None:
            final = value if value else default_value
            cache[name] = final
            return final
        console.print(f"[red]{name} requires a value.[/red]")


def _render_module_config_from_sample(sample_path: Path, static_values: dict[str, str]) -> str:
    text = sample_path.read_text(encoding="utf-8")

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if _is_secret_key(name):
            return match.group(0)
        return static_values.get(name, match.group(0))

    return PLACEHOLDER_RE.sub(_replace, text)


def _materialize_configs(
    kind: str,
    selected: list[AdapterInfo],
    non_secret_values: dict[str, str],
) -> tuple[dict[str, str], list[Path]]:
    module_dir = _module_dir_for(kind)
    result: dict[str, str] = {}
    created_paths: list[Path] = []

    for info in selected:
        suffix = _ask_config_suffix(kind, info.key)
        target_filename = f"{info.key}.{suffix}.json5"
        target = module_dir / target_filename

        placeholders = _extract_placeholders(info.sample_path)
        static_values: dict[str, str] = {}
        non_secret_items = [(n, d) for n, d in sorted(placeholders.items()) if not _is_secret_key(n)]
        if non_secret_items:
            console.print(f"\n[cyan]Static values for {kind} config: {info.key}.{suffix}[/cyan]")
        for name, default in non_secret_items:
            static_values[name] = _ask_non_secret_value(name, default, non_secret_values)


        rendered = _render_module_config_from_sample(info.sample_path, static_values)
        target.write_text(rendered, encoding="utf-8")
        if target.exists():
            console.print(f"[green]Written[/green] {target}")

        module_key = f"{info.key}_{suffix}".lower().replace("-", "_")
        rel_path = str(target.relative_to(ROOT)).replace("\\", "/")
        result[module_key] = rel_path
        created_paths.append(target)

    return result, created_paths

def _write_system_config(selected_llm: dict[str, str], selected_broker: dict[str, str]) -> None:
    lines = ["{", "  modules: {", "    llm: {"]

    llm_items = list(selected_llm.items())
    for i, (k, v) in enumerate(llm_items):
        lines.append(f'      {k}: "{v}"{"," if i < len(llm_items) - 1 else ""}')

    lines.extend(["    },", "    broker: {"])

    broker_items = list(selected_broker.items())
    for i, (k, v) in enumerate(broker_items):
        lines.append(f'      {k}: "{v}"{"," if i < len(broker_items) - 1 else ""}')

    lines.extend(["    }", "  }", "}", ""])

    SYSTEM_CFG.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {SYSTEM_CFG}")


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip().strip('"').strip("'")

    return values


def _module_context_label(path: Path) -> str:
    module_type = path.parent.name if path.parent is not None else "module"
    module_name = path.stem
    return f"{module_type}:{module_name}"


def _collect_secret_placeholders(config_paths: list[Path]) -> dict[str, tuple[str | None, list[str]]]:
    placeholders: dict[str, tuple[str | None, set[str]]] = {}

    for path in config_paths:
        if not path.exists():
            console.print(f"[yellow]Warning:[/yellow] referenced module not found: {path}")
            continue

        context_label = _module_context_label(path)
        for name, default in _extract_placeholders(path).items():
            if not _is_secret_key(name):
                continue
            if name not in placeholders:
                placeholders[name] = (default, {context_label})
                continue
            existing_default, contexts = placeholders[name]
            if existing_default in (None, "") and default not in (None, ""):
                existing_default = default
            contexts.add(context_label)
            placeholders[name] = (existing_default, contexts)

    out: dict[str, tuple[str | None, list[str]]] = {}
    for key, (default, contexts) in placeholders.items():
        out[key] = (default, sorted(contexts))
    return out


def _is_secret_key(name: str) -> bool:
    upper = name.upper()
    return any(token in upper for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS"))


def _ask_for_env_values(
    required: dict[str, tuple[str | None, list[str]]],
    current: dict[str, str],
) -> dict[str, str]:
    merged = dict(current)
    if not required:
        return merged

    console.print("\n[cyan]Secret values for .env[/cyan]")
    for key in sorted(required.keys()):
        default, contexts = required.get(key, (None, []))
        context_text = ", ".join(contexts) if contexts else "unknown-module"
        existing = merged.get(key)

        if existing and Confirm.ask(
            f"[{context_text}] {key} already set. Keep current value?",
            default=True,
        ):
            continue

        msg = f"[{context_text}] {key}:"
        if default not in (None, ""):
            msg += f" (default: {default})"

        value = questionary.password(msg).ask() if _is_secret_key(key) else questionary.text(msg).ask()
        value = (value or "").strip()

        if value:
            merged[key] = value
        elif default not in (None, ""):
            merged[key] = str(default)
        elif existing:
            merged[key] = existing
        else:
            merged[key] = ""

    return merged


def _write_env_file(values: dict[str, str]) -> None:
    lines = ["# Generated by scripts/initial_setup.py", ""]
    for key in sorted(values.keys()):
        lines.append(f"{key}={values[key]}")
    lines.append("")

    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {ENV_FILE}")


def _create_start_scripts(platform_name: str) -> None:
    if platform_name == "windows":
        ps1_path = ROOT / "start_openforexai.ps1"
        cmd_path = ROOT / "start_openforexai.cmd"

        ps1_path.write_text(
            "\n".join(
                [
                    "$ErrorActionPreference = 'Stop'",
                    "Set-Location $PSScriptRoot",
                    "if (-Not (Test-Path '.\\.venv\\Scripts\\python.exe')) {",
                    "  Write-Host 'Missing .venv. Run scripts/setup_windows.ps1 first.' -ForegroundColor Red",
                    "  exit 1",
                    "}",
                    "& .\\.venv\\Scripts\\python.exe tools\\openforexai-start.py",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        cmd_path.write_text(
            "\n".join(
                [
                    "@echo off",
                    "setlocal",
                    "powershell -ExecutionPolicy Bypass -File \"%~dp0start_openforexai.ps1\"",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        console.print(f"[green]Created[/green] {ps1_path}")
        console.print(f"[green]Created[/green] {cmd_path}")
        return

    sh_path = ROOT / "start_openforexai.sh"
    sh_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "cd \"$(dirname \"$0\")\"",
                "if [[ ! -f .venv/bin/python ]]; then",
                "  echo \"Missing .venv. Run scripts/setup_linux.sh first.\"",
                "  exit 1",
                "fi",
                ".venv/bin/python tools/openforexai-start.py",
                "",
            ]
        ),
        encoding="utf-8",
    )

    os.chmod(sh_path, 0o755)
    console.print(f"[green]Created[/green] {sh_path}")


def _build_test_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(_parse_env_file(ENV_FILE))
    return env


def _run_optional_tests(selected_llm: dict[str, str], selected_broker: dict[str, str]) -> None:
    if not Confirm.ask("Run broker and LLM smoke tests now?", default=False):
        return

    broker_choices = [questionary.Choice(title=k, value=Path(v).stem) for k, v in selected_broker.items()]
    llm_choices = [questionary.Choice(title=k, value=Path(v).stem) for k, v in selected_llm.items()]

    broker_module = questionary.select("Select broker module to test", choices=broker_choices).ask()
    llm_module = questionary.select("Select LLM module to test", choices=llm_choices).ask()
    test_pair = questionary.text("Test pair for broker test", default="EURUSD").ask() or "EURUSD"

    env = _build_test_env()

    console.print(f"\n[cyan]Running broker test:[/cyan] {broker_module} {test_pair}")
    subprocess.run(
        [sys.executable, "tools/test_broker.py", broker_module, test_pair, "--skip-live-test"],
        cwd=ROOT,
        check=False,
        env=env,
    )

    console.print(f"\n[cyan]Running LLM test:[/cyan] {llm_module}")
    subprocess.run(
        [sys.executable, "tools/test_llm.py", llm_module],
        cwd=ROOT,
        check=False,
        env=env,
    )

def _start_now() -> None:
    if Confirm.ask("Start OpenForexAI now via wrapper?", default=False):
        subprocess.run([sys.executable, "tools/openforexai-start.py"], cwd=ROOT, check=False)


def _summary(selected_broker: dict[str, str], selected_llm: dict[str, str]) -> None:
    table = Table(title="Setup Summary")
    table.add_column("Type", style="cyan")
    table.add_column("Module Key", style="green")
    table.add_column("Config Path", style="magenta")

    for k, v in selected_broker.items():
        table.add_row("broker", k, v)
    for k, v in selected_llm.items():
        table.add_row("llm", k, v)

    console.print(table)


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenForexAI setup wizard")
    parser.add_argument("--platform", choices=["windows", "linux"], default="windows")
    args = parser.parse_args()

    _clear_screen()
    console.print(Panel.fit("[bold cyan]OpenForexAI Setup Wizard[/bold cyan]\nModern guided setup"))
    console.print(f"[dim]Repository root: {ROOT}[/dim]")

    total_steps = 7

    _step("Discover adapters", 1, total_steps)
    broker_infos = _collect_adapter_infos("broker")
    llm_infos = _collect_adapter_infos("llm")
    if not broker_infos:
        console.print("[red]No broker adapters discovered. Abort.[/red]")
        return 1
    if not llm_infos:
        console.print("[red]No LLM adapters discovered. Abort.[/red]")
        return 1

    broker_info_map = {info.key: info for info in broker_infos}
    llm_info_map = {info.key: info for info in llm_infos}
    existing_broker, existing_llm = _load_existing_modules()

    _step("Select broker adapters", 2, total_steps)
    broker_reconfigure, broker_additional = _ask_existing_actions("broker", existing_broker)
    selected_existing_broker_keys: list[str] = []
    if broker_reconfigure:
        selected_existing_broker_keys = _select_existing_module_keys("broker", existing_broker)
    selected_broker_infos: list[AdapterInfo] = []
    if broker_additional:
        selected_broker_infos = _select_adapters("broker", broker_infos)

    _step("Select LLM adapters", 3, total_steps)
    llm_reconfigure, llm_additional = _ask_existing_actions("llm", existing_llm)
    selected_existing_llm_keys: list[str] = []
    if llm_reconfigure:
        selected_existing_llm_keys = _select_existing_module_keys("llm", existing_llm)
    selected_llm_infos: list[AdapterInfo] = []
    if llm_additional:
        selected_llm_infos = _select_adapters("llm", llm_infos)

    if not existing_broker and not selected_broker_infos and not selected_existing_broker_keys:
        console.print("[red]No broker adapter selected. Abort.[/red]")
        return 1
    if not existing_llm and not selected_llm_infos and not selected_existing_llm_keys:
        console.print("[red]No LLM adapter selected. Abort.[/red]")
        return 1

    _step("Create module config files", 4, total_steps)
    non_secret_values: dict[str, str] = {}
    selected_broker: dict[str, str] = dict(existing_broker)
    selected_llm: dict[str, str] = dict(existing_llm)
    broker_paths: list[Path] = []
    llm_paths: list[Path] = []

    if selected_existing_broker_keys:
        broker_paths.extend(
            _materialize_existing_modules(
                "broker",
                existing_broker,
                selected_existing_broker_keys,
                broker_info_map,
                non_secret_values,
            )
        )
    if selected_existing_llm_keys:
        llm_paths.extend(
            _materialize_existing_modules(
                "llm",
                existing_llm,
                selected_existing_llm_keys,
                llm_info_map,
                non_secret_values,
            )
        )

    if selected_broker_infos:
        new_broker, new_broker_paths = _materialize_configs("broker", selected_broker_infos, non_secret_values)
        selected_broker.update(new_broker)
        broker_paths.extend(new_broker_paths)
    if selected_llm_infos:
        new_llm, new_llm_paths = _materialize_configs("llm", selected_llm_infos, non_secret_values)
        selected_llm.update(new_llm)
        llm_paths.extend(new_llm_paths)
    _step("Write system config", 5, total_steps)
    _write_system_config(selected_llm=selected_llm, selected_broker=selected_broker)

    _step("Collect environment values", 6, total_steps)
    selected_paths = [*broker_paths, *llm_paths]
    required_vars = _collect_secret_placeholders(selected_paths)
    current_env = _parse_env_file(ENV_FILE)
    merged_env = _ask_for_env_values(required_vars, current_env)
    _write_env_file(merged_env)

    _step("Create start scripts and validate", 7, total_steps)
    _create_start_scripts(args.platform)
    _summary(selected_broker, selected_llm)
    _run_optional_tests(selected_llm, selected_broker)
    _start_now()

    console.print("\n[bold green]Setup finished.[/bold green]")
    console.print("Use the generated start script for next runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())












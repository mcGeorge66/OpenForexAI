"""Register/deregister/list broker adapters.

Without parameters this script prints detailed help.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = Path(__file__).resolve().parent
TARGET_DIR = REPO_ROOT / "openforexai" / "adapters" / "brokers"
INIT_FILE = TARGET_DIR / "__init__.py"

IMPORT_RE = re.compile(r"^from\s+openforexai\.adapters\.brokers\.(?P<module>\w+)\s+import\s+(?P<class_name>\w+)\s*$")
REGISTER_RE = re.compile(r'^PluginRegistry\.register_broker\("(?P<name>[^"]+)",\s*(?P<class_name>\w+)\)\s*$')
CLASS_RE = re.compile(r"^class\s+(?P<class_name>\w+)\(", re.MULTILINE)


@dataclass
class RegisteredAdapter:
    name: str
    class_name: str
    module: str
    file_path: Path


def _read_lines() -> list[str]:
    return INIT_FILE.read_text(encoding="utf-8").splitlines()


def _write_lines(lines: list[str]) -> None:
    INIT_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _parse() -> list[RegisteredAdapter]:
    lines = _read_lines()
    imports: dict[str, str] = {}
    regs: list[tuple[str, str]] = []
    for line in lines:
        i = IMPORT_RE.match(line.strip())
        if i:
            imports[i.group("class_name")] = i.group("module")
            continue
        r = REGISTER_RE.match(line.strip())
        if r:
            regs.append((r.group("name"), r.group("class_name")))
    out: list[RegisteredAdapter] = []
    for name, class_name in regs:
        module = imports.get(class_name)
        if not module:
            continue
        out.append(
            RegisteredAdapter(
                name=name,
                class_name=class_name,
                module=module,
                file_path=TARGET_DIR / f"{module}.py",
            )
        )
    return out


def _detect_class_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    matches = CLASS_RE.findall(text)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("No class found. Provide --class-name.")
    raise ValueError("Multiple classes found. Provide --class-name.")


def _insert_after_last(lines: list[str], pattern: re.Pattern[str], new_line: str) -> list[str]:
    idx = [i for i, line in enumerate(lines) if pattern.match(line.strip())]
    if not idx:
        return lines + [new_line]
    p = idx[-1] + 1
    return lines[:p] + [new_line] + lines[p:]


def _print_list() -> int:
    adapters = _parse()
    print("Registered broker adapters:")
    for a in adapters:
        print(f"- {a.name}: class={a.class_name}, module={a.module}, file={a.file_path}")
    return 0


def _register(args: argparse.Namespace) -> int:
    name = args.name.strip()
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError("--name must match [a-z0-9_]+")
    source = Path(args.source_file).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    module = args.module_name.strip() if args.module_name else name
    if not re.fullmatch(r"[a-z0-9_]+", module):
        raise ValueError("--module-name must match [a-z0-9_]+")
    class_name = args.class_name.strip() if args.class_name else _detect_class_name(source)

    dest = TARGET_DIR / f"{module}.py"
    shutil.copy2(source, dest)

    import_line = f"from openforexai.adapters.brokers.{module} import {class_name}"
    register_line = f'PluginRegistry.register_broker("{name}", {class_name})'
    lines = _read_lines()
    if import_line not in [line.strip() for line in lines]:
        lines = _insert_after_last(lines, IMPORT_RE, import_line)
    if register_line not in [line.strip() for line in lines]:
        lines = _insert_after_last(lines, REGISTER_RE, register_line)
    _write_lines(lines)

    print(f"Registered broker adapter '{name}'")
    print(f"- copied to: {dest}")
    print(f"- class: {class_name}")
    return 0


def _find_for_deregister(name_or_class: str) -> RegisteredAdapter:
    items = _parse()
    for a in items:
        if a.name.lower() == name_or_class.lower() or a.class_name.lower() == name_or_class.lower():
            return a
    raise ValueError(f"No adapter matched {name_or_class!r}. Use --list.")


def _safe_move_back(src: Path) -> Path:
    dst = TEMPLATE_DIR / src.name
    if not dst.exists():
        shutil.move(str(src), str(dst))
        return dst
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    alt = TEMPLATE_DIR / f"{src.stem}_{stamp}{src.suffix}"
    shutil.move(str(src), str(alt))
    return alt


def _deregister(args: argparse.Namespace) -> int:
    target = _find_for_deregister(args.name.strip())
    import_line = f"from openforexai.adapters.brokers.{target.module} import {target.class_name}"
    register_line = f'PluginRegistry.register_broker("{target.name}", {target.class_name})'
    lines = _read_lines()
    lines = [line for line in lines if line.strip() not in {import_line, register_line}]
    _write_lines(lines)

    if target.file_path.exists():
        moved = _safe_move_back(target.file_path)
        print(f"Deregistered and moved file to: {moved}")
    else:
        print("Deregistered adapter. Source file not found.")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="broker_adapter_manager.py", add_help=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true")
    g.add_argument("--register", action="store_true")
    g.add_argument("--deregister", action="store_true")
    p.add_argument("--name", default="", help="Registry key (e.g. oanda)")
    p.add_argument("--source-file", default="", help="Path to adapter source file")
    p.add_argument("--module-name", default="", help="Target python module file name (optional)")
    p.add_argument("--class-name", default="", help="Adapter class name (optional auto-detect)")
    return p


def _help(p: argparse.ArgumentParser) -> None:
    p.print_help()
    print()
    print("Examples:")
    print("  python template/broker/broker_adapter_manager.py --list")
    print(
        "  python template/broker/broker_adapter_manager.py --register "
        "--name demo --source-file template/broker/demo_broker_adapter.py "
        "--class-name DemoBrokerAdapter"
    )
    print("  python template/broker/broker_adapter_manager.py --deregister --name demo")


def main(argv: list[str]) -> int:
    p = _parser()
    if len(argv) == 1:
        _help(p)
        return 0
    a = p.parse_args(argv[1:])
    if a.list:
        return _print_list()
    if a.register:
        if not a.name or not a.source_file:
            raise ValueError("--name and --source-file are required for --register")
        return _register(a)
    if a.deregister:
        if not a.name:
            raise ValueError("--name is required for --deregister")
        return _deregister(a)
    _help(p)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)


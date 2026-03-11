"""Register/deregister/list LLM providers."""
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
TARGET_DIR = REPO_ROOT / "openforexai" / "adapters" / "llm"
INIT_FILE = TARGET_DIR / "__init__.py"

IMPORT_RE = re.compile(r"^from\s+openforexai\.adapters\.llm\.(?P<module>\w+)\s+import\s+(?P<class_name>[\w,\s]+)\s*$")
REGISTER_RE = re.compile(r'^PluginRegistry\.register_llm_provider\("(?P<name>[^"]+)",\s*(?P<class_name>\w+)\)\s*$')
CLASS_RE = re.compile(r"^class\s+(?P<class_name>\w+)\(", re.MULTILINE)


@dataclass
class RegisteredProvider:
    name: str
    class_name: str
    module: str
    file_path: Path


def _read_lines() -> list[str]:
    return INIT_FILE.read_text(encoding="utf-8").splitlines()


def _write_lines(lines: list[str]) -> None:
    INIT_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _parse() -> list[RegisteredProvider]:
    lines = _read_lines()
    imports: dict[str, str] = {}
    regs: list[tuple[str, str]] = []
    for line in lines:
        i = IMPORT_RE.match(line.strip())
        if i:
            module = i.group("module")
            for cname in [x.strip() for x in i.group("class_name").split(",")]:
                if cname:
                    imports[cname] = module
            continue
        r = REGISTER_RE.match(line.strip())
        if r:
            regs.append((r.group("name"), r.group("class_name")))
    out: list[RegisteredProvider] = []
    for name, class_name in regs:
        module = imports.get(class_name)
        if not module:
            continue
        out.append(RegisteredProvider(name, class_name, module, TARGET_DIR / f"{module}.py"))
    return out


def _detect_class_name(path: Path) -> str:
    matches = CLASS_RE.findall(path.read_text(encoding="utf-8"))
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


def _list() -> int:
    print("Registered LLM providers:")
    for r in _parse():
        print(f"- {r.name}: class={r.class_name}, module={r.module}, file={r.file_path}")
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

    import_line = f"from openforexai.adapters.llm.{module} import {class_name}"
    register_line = f'PluginRegistry.register_llm_provider("{name}", {class_name})'
    lines = _read_lines()
    if import_line not in [l.strip() for l in lines]:
        lines = _insert_after_last(lines, IMPORT_RE, import_line)
    if register_line not in [l.strip() for l in lines]:
        lines = _insert_after_last(lines, REGISTER_RE, register_line)
    _write_lines(lines)
    print(f"Registered LLM provider '{name}'")
    print(f"- copied to: {dest}")
    return 0


def _find_for_deregister(name_or_class: str) -> RegisteredProvider:
    for r in _parse():
        if r.name.lower() == name_or_class.lower() or r.class_name.lower() == name_or_class.lower():
            return r
    raise ValueError(f"No provider matched {name_or_class!r}. Use --list.")


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
    t = _find_for_deregister(args.name.strip())
    import_line = f"from openforexai.adapters.llm.{t.module} import {t.class_name}"
    register_line = f'PluginRegistry.register_llm_provider("{t.name}", {t.class_name})'
    lines = [l for l in _read_lines() if l.strip() not in {import_line, register_line}]
    _write_lines(lines)
    if t.file_path.exists():
        moved = _safe_move_back(t.file_path)
        print(f"Deregistered and moved file to: {moved}")
    else:
        print("Deregistered provider. Source file not found.")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="llm_adapter_manager.py", add_help=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true")
    g.add_argument("--register", action="store_true")
    g.add_argument("--deregister", action="store_true")
    p.add_argument("--name", default="", help="Registry key (e.g. openai)")
    p.add_argument("--source-file", default="", help="Path to provider source file")
    p.add_argument("--module-name", default="", help="Target python module file name (optional)")
    p.add_argument("--class-name", default="", help="Provider class name (optional auto-detect)")
    return p


def _help(p: argparse.ArgumentParser) -> None:
    p.print_help()
    print()
    print("Examples:")
    print("  python template/llm/llm_adapter_manager.py --list")
    print("  python template/llm/llm_adapter_manager.py --register --name demo --source-file template/llm/demo_llm_provider.py --class-name DemoLLMProvider")
    print("  python template/llm/llm_adapter_manager.py --deregister --name demo")


def main(argv: list[str]) -> int:
    p = _parser()
    if len(argv) == 1:
        _help(p)
        return 0
    a = p.parse_args(argv[1:])
    if a.list:
        return _list()
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


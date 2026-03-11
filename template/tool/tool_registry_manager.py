"""Tool registry manager for OpenForexAI.

This script lives in template/tool and helps developers:
1. Register a tool into the running system structure
2. Deregister a tool and move its file back into template/tool
3. List all currently registered tools

If started without parameters, it prints a detailed help text.
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
TEMPLATE_TOOL_DIR = Path(__file__).resolve().parent
SYSTEM_TOOLS_DIR = REPO_ROOT / "openforexai" / "tools"
TOOLS_INIT = SYSTEM_TOOLS_DIR / "__init__.py"
BUILTIN_DOMAINS = ["account", "market", "orderbook", "system", "trading"]

IMPORT_RE = re.compile(r"^from\s+openforexai\.tools\.(?P<module>[\w\.]+)\s+import\s+(?P<class_name>\w+)\s*$")
REGISTER_RE = re.compile(r"^DEFAULT_REGISTRY\.register\((?P<class_name>\w+)\(\)\)\s*$")
NAME_RE = re.compile(r'^\s*name\s*=\s*["\'](?P<name>[^"\']+)["\']\s*$', re.MULTILINE)
CLASS_RE = re.compile(r"^class\s+(?P<class_name>\w+)\(BaseTool\):\s*$", re.MULTILINE)
DOMAIN_NAME_RE = re.compile(r"^[a-z0-9_]+$")


@dataclass
class RegisteredTool:
    class_name: str
    module_path: str
    file_path: Path
    runtime_name: str | None


def _read_init_lines() -> list[str]:
    if not TOOLS_INIT.exists():
        raise FileNotFoundError(f"Missing file: {TOOLS_INIT}")
    return TOOLS_INIT.read_text(encoding="utf-8").splitlines()


def _write_init_lines(lines: list[str]) -> None:
    TOOLS_INIT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _module_to_file(module_path: str) -> Path:
    return SYSTEM_TOOLS_DIR / Path(module_path.replace(".", "/") + ".py")


def _load_domains() -> list[str]:
    domains = [
        p.name
        for p in SYSTEM_TOOLS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("__")
    ]
    return sorted(domains)


def _extract_runtime_name(py_file: Path) -> str | None:
    if not py_file.exists():
        return None
    text = py_file.read_text(encoding="utf-8")
    match = NAME_RE.search(text)
    if not match:
        return None
    return match.group("name")


def _parse_registered_tools() -> list[RegisteredTool]:
    lines = _read_init_lines()
    imports_by_class: dict[str, str] = {}
    registered_classes: list[str] = []

    for line in lines:
        m = IMPORT_RE.match(line.strip())
        if m:
            imports_by_class[m.group("class_name")] = m.group("module")
            continue
        m = REGISTER_RE.match(line.strip())
        if m:
            registered_classes.append(m.group("class_name"))

    tools: list[RegisteredTool] = []
    for class_name in registered_classes:
        module_path = imports_by_class.get(class_name)
        if module_path is None:
            continue
        file_path = _module_to_file(module_path)
        tools.append(
            RegisteredTool(
                class_name=class_name,
                module_path=module_path,
                file_path=file_path,
                runtime_name=_extract_runtime_name(file_path),
            )
        )
    return tools


def _detect_class_name(source_file: Path) -> str:
    text = source_file.read_text(encoding="utf-8")
    matches = CLASS_RE.findall(text)
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        raise ValueError("Could not auto-detect BaseTool class. Use --class-name.")
    raise ValueError("Multiple BaseTool classes found. Use --class-name.")


def _insert_line_after_last(lines: list[str], matcher: re.Pattern[str], new_line: str) -> list[str]:
    indices = [i for i, line in enumerate(lines) if matcher.match(line.strip())]
    if not indices:
        return lines + [new_line]
    insert_at = indices[-1] + 1
    return lines[:insert_at] + [new_line] + lines[insert_at:]


def _remove_line(lines: list[str], exact_line: str) -> list[str]:
    return [line for line in lines if line.strip() != exact_line.strip()]


def _print_list() -> int:
    tools = _parse_registered_tools()
    if not tools:
        print("No registered tools found in openforexai/tools/__init__.py")
        return 0

    print("Registered tools:")
    for t in tools:
        runtime = t.runtime_name if t.runtime_name else "(name attr not found)"
        exists = "yes" if t.file_path.exists() else "no"
        print(f"- runtime_name={runtime}")
        print(f"  class={t.class_name}")
        print(f"  module={t.module_path}")
        print(f"  file={t.file_path}")
        print(f"  file_exists={exists}")
    return 0


def _print_domain_list() -> int:
    domains = _load_domains()
    print("Allowed domains (strict mode):")
    for d in domains:
        path = SYSTEM_TOOLS_DIR / d
        exists = "yes" if path.exists() else "no"
        print(f"- {d} (folder_exists={exists})")
    return 0


def _validate_domain_name(domain: str) -> str:
    d = domain.strip()
    if not DOMAIN_NAME_RE.fullmatch(d):
        raise ValueError("Domain must match [a-z0-9_]+")
    return d


def _add_domain(domain: str) -> int:
    d = _validate_domain_name(domain)
    domains = _load_domains()
    if d in domains:
        print(f"Domain already exists: {d}")
        return 0
    (SYSTEM_TOOLS_DIR / d).mkdir(parents=True, exist_ok=True)
    print(f"Added domain: {d}")
    print(f"- folder: {SYSTEM_TOOLS_DIR / d}")
    return 0


def _delete_domain(domain: str) -> int:
    d = _validate_domain_name(domain)
    domains = _load_domains()
    if d not in domains:
        raise ValueError(f"Domain folder not found: {d}")
    if d in BUILTIN_DOMAINS:
        raise ValueError(f"Cannot delete built-in domain: {d}")

    tools = _parse_registered_tools()
    if any(t.module_path.startswith(f"{d}.") for t in tools):
        raise ValueError(
            f"Domain {d!r} still has registered tools. Deregister them first."
        )

    domain_path = SYSTEM_TOOLS_DIR / d
    if domain_path.exists():
        py_files = [p for p in domain_path.rglob("*.py")]
        if py_files:
            print(f"Domain folder kept (contains Python files): {domain_path}")
        else:
            shutil.rmtree(domain_path, ignore_errors=True)
            print(f"Removed domain folder: {domain_path}")
    print(f"Deleted domain: {d}")
    return 0


def _register(args: argparse.Namespace) -> int:
    source_file = Path(args.source_file).resolve()
    if not source_file.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")
    if source_file.suffix.lower() != ".py":
        raise ValueError("Source file must be a .py file")

    tool_name = args.tool_name.strip()
    if not re.fullmatch(r"[a-z0-9_]+", tool_name):
        raise ValueError("--tool-name must match [a-z0-9_]+")

    domain = _validate_domain_name(args.domain)
    allowed_domains = _load_domains()
    if domain not in allowed_domains:
        raise ValueError(
            f"Unknown domain {domain!r}. Strict mode only allows existing tool folders: {allowed_domains}. "
            "Use --adddomain to create a new one."
        )

    class_name = args.class_name.strip() if args.class_name else _detect_class_name(source_file)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", class_name):
        raise ValueError("--class-name is not a valid Python class name")

    target_dir = SYSTEM_TOOLS_DIR / domain
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{tool_name}.py"
    shutil.copy2(source_file, target_file)

    module_path = f"{domain.replace('/', '.')}.{tool_name}"
    import_line = f"from openforexai.tools.{module_path} import {class_name}"
    register_line = f"DEFAULT_REGISTRY.register({class_name}())"

    lines = _read_init_lines()
    if all(line.strip() != import_line for line in lines):
        lines = _insert_line_after_last(lines, IMPORT_RE, import_line)
    if all(line.strip() != register_line for line in lines):
        lines = _insert_line_after_last(lines, REGISTER_RE, register_line)
    _write_init_lines(lines)

    print("Registered tool successfully.")
    print(f"- source: {source_file}")
    print(f"- copied to: {target_file}")
    print(f"- class: {class_name}")
    print(f"- module: openforexai.tools.{module_path}")
    print(f"- runtime tool name (expected): {tool_name}")
    return 0


def _find_tool_for_deregister(tool_name: str) -> RegisteredTool:
    candidates = _parse_registered_tools()
    by_runtime = [t for t in candidates if (t.runtime_name or "").lower() == tool_name.lower()]
    if by_runtime:
        return by_runtime[0]
    by_class = [t for t in candidates if t.class_name.lower() == tool_name.lower()]
    if by_class:
        return by_class[0]
    raise ValueError(
        f"No registered tool matched {tool_name!r} as runtime name or class name. "
        "Use --list to inspect current registry."
    )


def _safe_move_to_template(src: Path) -> Path:
    base_dest = TEMPLATE_TOOL_DIR / src.name
    if not base_dest.exists():
        shutil.move(str(src), str(base_dest))
        return base_dest

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    alt_dest = TEMPLATE_TOOL_DIR / f"{src.stem}_{stamp}{src.suffix}"
    shutil.move(str(src), str(alt_dest))
    return alt_dest


def _deregister(args: argparse.Namespace) -> int:
    target = _find_tool_for_deregister(args.tool_name.strip())

    import_line = f"from openforexai.tools.{target.module_path} import {target.class_name}"
    register_line = f"DEFAULT_REGISTRY.register({target.class_name}())"

    lines = _read_init_lines()
    lines = _remove_line(lines, import_line)
    lines = _remove_line(lines, register_line)
    _write_init_lines(lines)

    moved_to: Path | None = None
    if target.file_path.exists():
        moved_to = _safe_move_to_template(target.file_path)

    print("Deregistered tool successfully.")
    print(f"- class: {target.class_name}")
    print(f"- module: openforexai.tools.{target.module_path}")
    if moved_to is not None:
        print(f"- moved file to: {moved_to}")
    else:
        print("- note: tool file was not found on disk; registry entries were removed")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tool_registry_manager.py",
        add_help=True,
        description=(
            "Register, deregister, and list tools in OpenForexAI. "
            "Use --list to inspect current registry."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="List currently registered tools")
    mode.add_argument("--listdomain", action="store_true", help="List allowed domains (strict mode)")
    mode.add_argument("--adddomain", default="", help="Add a new allowed domain (strict mode)")
    mode.add_argument("--deletedomain", default="", help="Delete a custom allowed domain (strict mode)")
    mode.add_argument("--register", action="store_true", help="Register a tool")
    mode.add_argument("--deregister", action="store_true", help="Deregister a tool")

    parser.add_argument("--tool-name", default="", help="Runtime tool name (e.g. get_candles)")
    parser.add_argument(
        "--source-file",
        default="",
        help="Path to source .py file to copy into openforexai/tools (register mode)",
    )
    parser.add_argument(
        "--class-name",
        default="",
        help="Tool class to register (e.g. GetCandlesTool). If omitted, auto-detect is attempted.",
    )
    parser.add_argument(
        "--domain",
        default="system",
        help="Target domain subfolder below openforexai/tools (default: system)",
    )
    return parser


def _print_detailed_help(parser: argparse.ArgumentParser) -> None:
    parser.print_help()
    print()
    print("Detailed usage:")
    print("1) List registered tools:")
    print("   python template/tool/tool_registry_manager.py --list")
    print()
    print("2) List strict-mode domains:")
    print("   python template/tool/tool_registry_manager.py --listdomain")
    print()
    print("3) Add a custom domain:")
    print("   python template/tool/tool_registry_manager.py --adddomain research")
    print()
    print("4) Delete a custom domain:")
    print("   python template/tool/tool_registry_manager.py --deletedomain research")
    print()
    print("5) Register a tool:")
    print(
        "   python template/tool/tool_registry_manager.py --register "
        "--tool-name my_tool --source-file template/tool/my_tool.py "
        "--class-name MyTool --domain system"
    )
    print("   This will:")
    print("   - copy the source file to openforexai/tools/<domain>/<tool_name>.py")
    print("   - add import + DEFAULT_REGISTRY.register(...) entries to openforexai/tools/__init__.py")
    print()
    print("6) Deregister a tool:")
    print("   python template/tool/tool_registry_manager.py --deregister --tool-name my_tool")
    print("   This will:")
    print("   - remove import + register lines from openforexai/tools/__init__.py")
    print("   - move the tool file from openforexai/tools/... back into template/tool/")
    print()
    print("Notes:")
    print("- Strict mode: --domain must exist as a subfolder in openforexai/tools.")
    print("- --tool-name in deregister mode can match runtime tool name OR class name.")
    print("- If target filename already exists in template/tool, a timestamp suffix is used.")
    print("- Run from repository root for easiest path usage.")


def main(argv: list[str]) -> int:
    parser = _build_parser()
    if len(argv) == 1:
        _print_detailed_help(parser)
        return 0

    args = parser.parse_args(argv[1:])
    if args.list:
        return _print_list()
    if args.listdomain:
        return _print_domain_list()
    if args.adddomain:
        return _add_domain(args.adddomain)
    if args.deletedomain:
        return _delete_domain(args.deletedomain)
    if args.register:
        if not args.tool_name:
            raise ValueError("--tool-name is required in --register mode")
        if not args.source_file:
            raise ValueError("--source-file is required in --register mode")
        return _register(args)
    if args.deregister:
        if not args.tool_name:
            raise ValueError("--tool-name is required in --deregister mode")
        return _deregister(args)

    _print_detailed_help(parser)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception as exc:  # pragma: no cover - top-level error reporting
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)

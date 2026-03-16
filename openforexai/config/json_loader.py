"""JSON5 config loader with environment variable substitution and default/custom merge.

Supports ${VAR_NAME} and ${VAR_NAME:-default} patterns in string values.

For system config loading:
- If the requested file is ``system.json5`` and a sibling
  ``config.default.json5`` exists, loader behavior is:
  1) load default
  2) load system/custom
  3) deep merge (default <- custom)

Merge rules:
- Objects: recursive merge
- Arrays: append+dedupe by default
- Paths listed in ``ImportRules.Replace`` are replaced entirely

``ImportRules`` is read from the default config and removed from the final result.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import json5

_ENV_RE = re.compile(r"\$\{([^}:]+)(?::-(.*?))?\}")


def _substitute(value: str) -> str:
    def _replace(m: re.Match) -> str:
        var, default = m.group(1), m.group(2)
        return os.environ.get(var, default if default is not None else m.group(0))

    return _ENV_RE.sub(_replace, value)


def _process(node: Any) -> Any:
    if isinstance(node, str):
        return _substitute(node)
    if isinstance(node, dict):
        return {k: _process(v) for k, v in node.items() if not k.startswith("_")}
    if isinstance(node, list):
        return [_process(item) for item in node]
    return node


def _normalize_path(path: str) -> str:
    return path.strip().strip(".")


def _path_matches_rule(path: str, rule: str) -> bool:
    """Match dot-path with '*' wildcard per segment."""
    p = _normalize_path(path)
    r = _normalize_path(rule)
    if not r:
        return False
    p_parts = p.split(".") if p else []
    r_parts = r.split(".")
    if len(p_parts) != len(r_parts):
        return False
    for pp, rp in zip(p_parts, r_parts):
        if rp == "*":
            continue
        if pp != rp:
            return False
    return True


def _array_append_unique(base: list[Any], override: list[Any]) -> list[Any]:
    out = list(base)
    seen = {repr(item) for item in out}
    for item in override:
        marker = repr(item)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _deep_merge(
    base: Any,
    override: Any,
    *,
    replace_paths: list[str],
    path: str = "",
) -> Any:
    if path and any(_path_matches_rule(path, rule) for rule in replace_paths):
        return override

    if isinstance(base, dict) and isinstance(override, dict):
        out: dict[str, Any] = dict(base)
        for key, val in override.items():
            child_path = f"{path}.{key}" if path else key
            if key in out:
                out[key] = _deep_merge(out[key], val, replace_paths=replace_paths, path=child_path)
            else:
                out[key] = val
        return out

    if isinstance(base, list) and isinstance(override, list):
        return _array_append_unique(base, override)

    return override


def _load_single(path: Path) -> dict[str, Any]:
    data = json5.loads(path.read_text(encoding="utf-8-sig"))
    processed = _process(data)
    if not isinstance(processed, dict):
        raise ValueError(f"Config root must be an object: {path}")
    return processed


def _load_system_with_defaults(system_path: Path) -> dict[str, Any]:
    default_path = system_path.with_name("config.default.json5")
    if not default_path.exists():
        return _load_single(system_path)

    default_cfg = _load_single(default_path)
    custom_cfg = _load_single(system_path) if system_path.exists() else {}

    import_rules = default_cfg.get("ImportRules", {})
    replace_paths: list[str] = []
    if isinstance(import_rules, dict):
        replace_raw = import_rules.get("Replace", [])
        if isinstance(replace_raw, list):
            replace_paths = [str(x).strip() for x in replace_raw if str(x).strip()]

    default_body = dict(default_cfg)
    default_body.pop("ImportRules", None)

    merged = _deep_merge(default_body, custom_cfg, replace_paths=replace_paths)
    if not isinstance(merged, dict):
        raise ValueError("Merged system config must be an object.")
    return merged


def load_json_config(path: str | Path) -> dict[str, Any]:
    """Load a JSON5 config file with env-var substitution.

    Keys starting with ``_`` are stripped from the result.
    For ``system.json5`` with sibling ``config.default.json5`` available,
    the returned config is merged default+custom.
    """
    p = Path(path)
    if p.name == "system.json5":
        return _load_system_with_defaults(p)
    return _load_single(p)

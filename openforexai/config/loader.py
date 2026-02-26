from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


_ENV_VAR_RE = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _substitute_env_vars(value: str) -> str:
    """Replace ${VAR} and ${VAR:-default} patterns with environment values."""

    def replacer(match: re.Match[str]) -> str:
        var_name, default = match.group(1), match.group(2)
        return os.environ.get(var_name, default if default is not None else match.group(0))

    return _ENV_VAR_RE.sub(replacer, value)


def _process_node(node: Any) -> Any:
    if isinstance(node, str):
        return _substitute_env_vars(node)
    if isinstance(node, dict):
        return {k: _process_node(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_process_node(item) for item in node]
    return node


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file with environment variable substitution."""
    with open(path) as fh:
        raw = yaml.safe_load(fh) or {}
    return _process_node(raw)


def merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge multiple config dicts; later values override earlier ones."""
    result: dict[str, Any] = {}
    for cfg in configs:
        _deep_merge(result, cfg)
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value

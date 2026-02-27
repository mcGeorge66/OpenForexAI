"""JSON config loader with environment variable substitution.

Supports ${VAR_NAME} and ${VAR_NAME:-default} patterns in string values.

Usage::

    cfg = load_json_config(Path("config/system.json"))
    module_cfg = load_json_config(Path("config/modules/llm/anthropic_claude.json"))
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

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


def load_json_config(path: str | Path) -> dict[str, Any]:
    """Load a JSON config file with env-var substitution.

    Keys starting with ``_`` (comments, docs) are stripped from the result.
    Raises ``FileNotFoundError`` if the file does not exist.
    Raises ``json.JSONDecodeError`` if the file contains invalid JSON.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return _process(data)

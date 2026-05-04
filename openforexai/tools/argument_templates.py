from __future__ import annotations

import re
from typing import Any

from openforexai.messaging.agent_id import AgentId

_PLACEHOLDER_RE = re.compile(r"{([A-Za-z0-9_]+)}")


def build_agent_placeholder_values(
    *,
    agent_id: str,
    agent_config: dict[str, Any] | None = None,
    broker_name: str | None = None,
    pair: str | None = None,
) -> dict[str, Any]:
    cfg = agent_config if isinstance(agent_config, dict) else {}
    parsed_id = AgentId.try_parse(agent_id)

    values: dict[str, Any] = {}

    for key, value in cfg.items():
        if isinstance(key, str) and isinstance(value, (str, int, float, bool)) and value != "":
            values[key] = value

    values["agent_id"] = agent_id
    values["broker"] = cfg.get("broker") if isinstance(cfg.get("broker"), str) else values.get("broker")
    values["broker_name"] = broker_name or values.get("broker_name")
    values["pair"] = cfg.get("pair") if isinstance(cfg.get("pair"), str) else (pair or values.get("pair"))
    values["llm"] = cfg.get("llm") if isinstance(cfg.get("llm"), str) else values.get("llm")
    values["comment"] = cfg.get("_comment") if isinstance(cfg.get("_comment"), str) else values.get("comment")
    values["AnyCandle"] = cfg.get("AnyCandle", values.get("AnyCandle"))

    if parsed_id is not None:
        values["broker_id"] = parsed_id.broker
        values["pair_id"] = parsed_id.pair
        values["type"] = parsed_id.type
        values["name"] = parsed_id.name
        values["extension"] = parsed_id.extension or ""

    return {key: value for key, value in values.items() if value is not None}


def resolve_argument_templates(value: Any, placeholders: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {
            key: resolve_argument_templates(item, placeholders)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [resolve_argument_templates(item, placeholders) for item in value]
    if not isinstance(value, str):
        return value

    exact = _PLACEHOLDER_RE.fullmatch(value.strip())
    if exact:
        key = exact.group(1)
        return placeholders.get(key, value)

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        replacement = placeholders.get(key)
        if replacement is None:
            return match.group(0)
        return str(replacement)

    return _PLACEHOLDER_RE.sub(_replace, value)

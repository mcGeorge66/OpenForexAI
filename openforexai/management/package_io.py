from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import json5

from openforexai.messaging.agent_id import AgentId, substitute_template

AGENT_ID_RE = re.compile(r"^[A-Z0-9_]{5}-[A-Z0-9_]{6}-[A-Z]{2}-[A-Z0-9]{1,5}(?:-.+)?$")


def parse_json5_text(content: str) -> dict[str, Any]:
    parsed = json5.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Package root must be a JSON5 object.")
    return parsed


def parse_mapping_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        old = left.strip()
        new = right.strip()
        if old and new:
            out[old] = new
    return out


def _read_json5_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json5.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _pattern_matches_agent(pattern: str, agent_id: str) -> bool:
    aid = AgentId.try_parse(agent_id)
    if aid is None:
        return False
    return aid.matches(pattern)


def _target_matches_selected(target: str, selected_ids: list[str], selected_parsed: dict[str, AgentId]) -> bool:
    target = (target or "").strip()
    if not target:
        return False
    if target == "*":
        return True
    if target == "@handlers":
        return False

    for sid in selected_ids:
        if target == sid:
            return True

    if "*" in target:
        for sid in selected_ids:
            if _pattern_matches_agent(target, sid):
                return True

    if "{sender." in target:
        for sid, sender_aid in selected_parsed.items():
            _ = sid
            resolved = substitute_template(target, sender_aid)
            if resolved == "*":
                return True
            if resolved in selected_ids:
                return True
            if "*" in resolved:
                for tid in selected_ids:
                    if _pattern_matches_agent(resolved, tid):
                        return True

    return False


def _filter_routing_for_agents(
    event_routing: dict[str, Any],
    selected_ids: list[str],
    selected_triggers: set[str],
) -> dict[str, Any]:
    rules = event_routing.get("rules", [])
    if not isinstance(rules, list):
        return {"rules": []}

    selected_parsed = {
        sid: aid
        for sid in selected_ids
        if (aid := AgentId.try_parse(sid)) is not None
    }

    filtered: list[dict[str, Any]] = []
    for raw in rules:
        if not isinstance(raw, dict):
            continue
        from_pattern = str(raw.get("from", "*")).strip() or "*"
        to_target = str(raw.get("to", "")).strip()
        event_name = str(raw.get("event", "")).strip()

        from_specific_match = (
            from_pattern != "*"
            and any(_pattern_matches_agent(from_pattern, sid) for sid in selected_ids)
        )
        to_match_selected = _target_matches_selected(to_target, selected_ids, selected_parsed)
        handler_relevant = (
            to_target == "@handlers"
            and event_name in selected_triggers
        )

        if from_specific_match or to_match_selected or handler_relevant:
            filtered.append(copy.deepcopy(raw))

    return {"rules": filtered}


def _collect_used_tools(export_agents: dict[str, Any]) -> set[str]:
    used: set[str] = set()
    for cfg in export_agents.values():
        if not isinstance(cfg, dict):
            continue
        tool_cfg = cfg.get("tool_config", {})
        if not isinstance(tool_cfg, dict):
            continue

        allowed = tool_cfg.get("allowed_tools", [])
        if isinstance(allowed, list):
            used.update(str(t) for t in allowed if isinstance(t, str) and t != "*")
    return used


def _filter_agent_tools_for_agents(
    agent_tools: dict[str, Any],
    _selected_ids: list[str],
    used_tools: set[str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}

    bridges = agent_tools.get("bridge_tools", [])
    if isinstance(bridges, list):
        relevant_bridges: list[dict[str, Any]] = []
        for item in bridges:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name in used_tools:
                relevant_bridges.append(copy.deepcopy(item))
        if relevant_bridges:
            out["bridge_tools"] = relevant_bridges

    return out


def check_export_dependency_issues(
    export_agents: dict[str, Any],
    filtered_routing: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Detect likely indirect dependencies that are not included in the export."""
    issues: list[dict[str, str]] = []
    selected_ids = list(export_agents.keys())
    selected_set = set(selected_ids)
    selected_parsed = {
        sid: aid
        for sid in selected_ids
        if (aid := AgentId.try_parse(sid)) is not None
    }

    if not isinstance(filtered_routing, dict):
        return issues
    rules = filtered_routing.get("rules", [])
    if not isinstance(rules, list):
        return issues

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid = str(rule.get("id", "(no-id)"))
        target = str(rule.get("to", "")).strip()
        if not target or target in {"*", "@handlers"}:
            continue

        if "*" not in target and "{sender." not in target:
            if target not in selected_set and AgentId.try_parse(target) is not None:
                issues.append({
                    "level": "warning",
                    "path": f"runtime.event_routing.rules[{rid}].to",
                    "message": (
                        f'Rule target "{target}" is outside the exported agent set. '
                        "Import target system may require additional agents."
                    ),
                })
            continue

        if "{sender." in target:
            for sender_id, sender_aid in selected_parsed.items():
                _ = sender_id
                resolved = substitute_template(target, sender_aid).strip()
                if not resolved or resolved in {"*", "@handlers"}:
                    continue
                if "*" in resolved:
                    if not any(_pattern_matches_agent(resolved, sid) for sid in selected_ids):
                        issues.append({
                            "level": "warning",
                            "path": f"runtime.event_routing.rules[{rid}].to",
                            "message": (
                                f'Template target "{target}" resolves to pattern "{resolved}" '
                                "without a match inside the exported agents."
                            ),
                        })
                elif resolved not in selected_set and AgentId.try_parse(resolved) is not None:
                    issues.append({
                        "level": "warning",
                        "path": f"runtime.event_routing.rules[{rid}].to",
                        "message": (
                            f'Template target "{target}" resolves to external agent "{resolved}". '
                            "This dependency is not included in export."
                        ),
                    })
            continue

        if "*" in target:
            if not any(_pattern_matches_agent(target, sid) for sid in selected_ids):
                issues.append({
                    "level": "warning",
                    "path": f"runtime.event_routing.rules[{rid}].to",
                    "message": (
                        f'Pattern target "{target}" does not match any exported agent. '
                        "Likely external dependency."
                    ),
                })

    return issues


def build_export_package(
    system_config: dict[str, Any],
    *,
    selected_agent_ids: list[str] | None,
    include_agents: bool,
    include_snapshot_profiles: bool,
    include_decision_prompt_profiles: bool,
    include_bridge_tools: bool,
    include_event_routing: bool,
    include_system_config: bool,
    event_routing_path: Path,
    agent_tools_path: Path,
    strict_dependencies: bool = False,
) -> dict[str, Any]:
    agents_cfg = system_config.get("agents", {})
    if not isinstance(agents_cfg, dict):
        agents_cfg = {}

    if selected_agent_ids:
        wanted = [aid for aid in selected_agent_ids if aid in agents_cfg]
    else:
        wanted = list(agents_cfg.keys())

    export_agents: dict[str, Any] = {aid: copy.deepcopy(agents_cfg[aid]) for aid in wanted} if include_agents else {}

    package: dict[str, Any] = {
        "meta": {
            "format": "ofai-config-package",
            "format_version": 2,
            "exported_at_utc": datetime.now(UTC).isoformat(),
        },
    }

    if include_agents:
        package["agents"] = export_agents
    if include_snapshot_profiles:
        snapshot_profiles = system_config.get("snapshot_profiles", {})
        if isinstance(snapshot_profiles, dict):
            package["snapshot_profiles"] = copy.deepcopy(snapshot_profiles)
    if include_decision_prompt_profiles:
        decision_prompt_profiles = system_config.get("decision_prompt_profiles", {})
        if isinstance(decision_prompt_profiles, dict):
            package["decision_prompt_profiles"] = copy.deepcopy(decision_prompt_profiles)
    if include_system_config:
        package["system_config"] = {
            key: copy.deepcopy(system_config.get(key, {}))
            for key in ("ImportRules", "system", "database", "data")
            if key in system_config
        }

    runtime: dict[str, Any] = {}
    selected_triggers: set[str] = set()
    for cfg in export_agents.values():
        if not isinstance(cfg, dict):
            continue
        triggers = cfg.get("event_triggers", [])
        if isinstance(triggers, list):
            selected_triggers.update(str(t) for t in triggers if isinstance(t, str))

    used_tools = _collect_used_tools(export_agents)

    filtered_routing: dict[str, Any] | None = None
    if include_event_routing:
        routing_all = _read_json5_file(event_routing_path)
        filtered_routing = (
            _filter_routing_for_agents(routing_all, wanted, selected_triggers)
            if include_agents
            else copy.deepcopy(routing_all)
        )
        runtime["event_routing"] = filtered_routing
    if include_bridge_tools:
        tools_all = _read_json5_file(agent_tools_path)
        runtime["agent_tools"] = (
            _filter_agent_tools_for_agents(tools_all, wanted, used_tools)
            if include_agents
            else copy.deepcopy(tools_all)
        )
    if runtime:
        package["runtime"] = runtime

    if strict_dependencies:
        issues = check_export_dependency_issues(export_agents, filtered_routing)
        meta = package.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["strict_dependencies"] = True
            meta["strict_ok"] = len(issues) == 0
            if issues:
                meta["dependency_issues"] = issues

    return package


def _map_agent_id(agent_id: str, mapping: dict[str, Any]) -> str:
    id_map = mapping.get("agent_id_map", {})
    if isinstance(id_map, dict) and agent_id in id_map and isinstance(id_map[agent_id], str):
        return str(id_map[agent_id]).strip().upper()
    prefix = str(mapping.get("agent_id_prefix", "") or "").strip().upper()
    if prefix:
        return f"{prefix}{agent_id}"
    return agent_id


def _map_agent_cfg(agent_cfg: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(agent_cfg)
    broker_map = mapping.get("broker_map", {})
    llm_map = mapping.get("llm_map", {})

    if isinstance(broker_map, dict):
        broker = out.get("broker")
        if isinstance(broker, str) and broker in broker_map and isinstance(broker_map[broker], str):
            out["broker"] = broker_map[broker]

    if isinstance(llm_map, dict):
        llm = out.get("llm")
        if isinstance(llm, str) and llm in llm_map and isinstance(llm_map[llm], str):
            out["llm"] = llm_map[llm]
    return out


def _validate_agent_tools(
    agent_id: str,
    cfg: dict[str, Any],
    known_tools: set[str],
    problems: list[dict[str, str]],
) -> None:
    tool_cfg = cfg.get("tool_config", {})
    if not isinstance(tool_cfg, dict):
        return

    allowed = tool_cfg.get("allowed_tools", [])
    if isinstance(allowed, list):
        for idx, tool in enumerate(allowed):
            if not isinstance(tool, str):
                problems.append({
                    "level": "error",
                    "path": f"agents.{agent_id}.tool_config.allowed_tools[{idx}]",
                    "message": "Tool name must be a string.",
                })
                continue
            if tool != "*" and tool not in known_tools:
                problems.append({
                    "level": "error",
                    "path": f"agents.{agent_id}.tool_config.allowed_tools[{idx}]",
                    "message": f'Tool "{tool}" does not exist.',
                })

    forced_arguments = tool_cfg.get("forced_arguments", {})
    if forced_arguments is None:
        return
    if not isinstance(forced_arguments, dict):
        problems.append({
            "level": "error",
            "path": f"agents.{agent_id}.tool_config.forced_arguments",
            "message": "forced_arguments must be an object keyed by tool name.",
        })
        return

    for tool_name, forced_cfg in forced_arguments.items():
        if not isinstance(tool_name, str):
            problems.append({
                "level": "error",
                "path": f"agents.{agent_id}.tool_config.forced_arguments",
                "message": "forced_arguments keys must be tool names.",
            })
            continue
        if tool_name not in known_tools:
            problems.append({
                "level": "error",
                "path": f"agents.{agent_id}.tool_config.forced_arguments.{tool_name}",
                "message": f'Tool "{tool_name}" does not exist.',
            })
            continue
        if not isinstance(forced_cfg, dict):
            problems.append({
                "level": "error",
                "path": f"agents.{agent_id}.tool_config.forced_arguments.{tool_name}",
                "message": "Forced arguments for a tool must be an object.",
            })


def validate_package(
    package: dict[str, Any],
    *,
    current_system_config: dict[str, Any],
    known_tools: set[str],
    mapping: dict[str, Any] | None = None,
    replace_existing_agents: bool = False,
) -> dict[str, Any]:
    mapping = mapping or {}
    problems: list[dict[str, str]] = []

    agents = package.get("agents")
    snapshot_profiles = package.get("snapshot_profiles")
    decision_prompt_profiles = package.get("decision_prompt_profiles")
    system_config_section = package.get("system_config")
    runtime = package.get("runtime")

    has_agents = isinstance(agents, dict) and bool(agents)
    has_snapshot_profiles = isinstance(snapshot_profiles, dict) and bool(snapshot_profiles)
    has_decision_prompt_profiles = isinstance(decision_prompt_profiles, dict) and bool(decision_prompt_profiles)
    has_system_config = isinstance(system_config_section, dict) and bool(system_config_section)
    has_runtime = isinstance(runtime, dict) and any(
        isinstance(runtime.get(key), dict) for key in ("event_routing", "agent_tools")
    )

    if not any((has_agents, has_snapshot_profiles, has_decision_prompt_profiles, has_system_config, has_runtime)):
        problems.append({
            "level": "error",
            "path": "package",
            "message": "Package must contain at least one configuration section.",
        })
        return {"ok": False, "problems": problems, "preview": {"agents": 0}}

    modules = current_system_config.get("modules", {})
    llm_names = set((modules.get("llm") or {}).keys()) if isinstance(modules, dict) else set()
    broker_names = set((modules.get("broker") or {}).keys()) if isinstance(modules, dict) else set()

    current_agents = current_system_config.get("agents", {})
    if not isinstance(current_agents, dict):
        current_agents = {}

    combined_snapshot_profiles: set[str] = set()
    current_snapshot_profiles = current_system_config.get("snapshot_profiles", {})
    if isinstance(current_snapshot_profiles, dict):
        combined_snapshot_profiles.update(str(name) for name in current_snapshot_profiles.keys())
    if isinstance(snapshot_profiles, dict):
        combined_snapshot_profiles.update(str(name) for name in snapshot_profiles.keys())
        for name, value in snapshot_profiles.items():
            if not isinstance(value, dict):
                problems.append({
                    "level": "error",
                    "path": f"snapshot_profiles.{name}",
                    "message": "Snapshot profile must be an object.",
                })

    combined_decision_profiles: set[str] = set()
    current_decision_profiles = current_system_config.get("decision_prompt_profiles", {})
    if isinstance(current_decision_profiles, dict):
        combined_decision_profiles.update(str(name) for name in current_decision_profiles.keys())
    if isinstance(decision_prompt_profiles, dict):
        combined_decision_profiles.update(str(name) for name in decision_prompt_profiles.keys())
        for name, value in decision_prompt_profiles.items():
            if not isinstance(value, dict):
                problems.append({
                    "level": "error",
                    "path": f"decision_prompt_profiles.{name}",
                    "message": "Decision prompt profile must be an object.",
                })

    if isinstance(system_config_section, dict):
        for key in system_config_section.keys():
            if key not in {"ImportRules", "system", "database", "data"}:
                problems.append({
                    "level": "warning",
                    "path": f"system_config.{key}",
                    "message": "Unknown system_config section will be ignored on import.",
                })

    if isinstance(agents, dict):
        mapped_ids: set[str] = set()
        for source_agent_id, raw_cfg in agents.items():
            if not isinstance(raw_cfg, dict):
                problems.append({
                    "level": "error",
                    "path": f"agents.{source_agent_id}",
                    "message": "Agent config must be an object.",
                })
                continue

            target_agent_id = _map_agent_id(str(source_agent_id).upper(), mapping)
            if not AGENT_ID_RE.match(target_agent_id):
                problems.append({
                    "level": "error",
                    "path": f"agents.{source_agent_id}",
                    "message": f'Invalid target agent_id "{target_agent_id}" after mapping.',
                })

            if target_agent_id in mapped_ids:
                problems.append({
                    "level": "error",
                    "path": f"agents.{source_agent_id}",
                    "message": f'Duplicate target agent_id "{target_agent_id}" after mapping.',
                })
            mapped_ids.add(target_agent_id)

            mapped_cfg = _map_agent_cfg(raw_cfg, mapping)
            llm = mapped_cfg.get("llm")
            broker = mapped_cfg.get("broker")

            if not isinstance(llm, str) or not llm.strip():
                problems.append({
                    "level": "error",
                    "path": f"agents.{source_agent_id}.llm",
                    "message": "LLM is required.",
                })
            elif llm not in llm_names:
                problems.append({
                    "level": "error",
                    "path": f"agents.{source_agent_id}.llm",
                    "message": f'LLM "{llm}" does not exist.',
                })

            if not isinstance(broker, str) or not broker.strip():
                problems.append({
                    "level": "error",
                    "path": f"agents.{source_agent_id}.broker",
                    "message": "Broker is required.",
                })
            elif broker not in broker_names:
                problems.append({
                    "level": "error",
                    "path": f"agents.{source_agent_id}.broker",
                    "message": f'Broker "{broker}" does not exist.',
                })

            if target_agent_id in current_agents and not replace_existing_agents:
                problems.append({
                    "level": "error",
                    "path": f"agents.{source_agent_id}",
                    "message": (
                        f'Target agent_id "{target_agent_id}" already exists. '
                        "Enable replace_existing_agents or adjust mapping."
                    ),
                })

            snapshot_profile_name = mapped_cfg.get("snapshot_profile")
            if isinstance(snapshot_profile_name, str) and snapshot_profile_name.strip():
                if snapshot_profile_name not in combined_snapshot_profiles:
                    problems.append({
                        "level": "error",
                        "path": f"agents.{source_agent_id}.snapshot_profile",
                        "message": f'Snapshot profile "{snapshot_profile_name}" does not exist locally or in package.',
                    })

            decision_profile_name = mapped_cfg.get("decision_prompt_profile")
            if isinstance(decision_profile_name, str) and decision_profile_name.strip():
                if decision_profile_name not in combined_decision_profiles:
                    problems.append({
                        "level": "error",
                        "path": f"agents.{source_agent_id}.decision_prompt_profile",
                        "message": f'Decision prompt profile "{decision_profile_name}" does not exist locally or in package.',
                    })

            _validate_agent_tools(source_agent_id, mapped_cfg, known_tools, problems)

    if isinstance(runtime, dict):
        event_routing = runtime.get("event_routing")
        if isinstance(event_routing, dict):
            rules = event_routing.get("rules")
            if rules is not None and not isinstance(rules, list):
                problems.append({
                    "level": "error",
                    "path": "runtime.event_routing.rules",
                    "message": "Rules must be a list.",
                })
        agent_tools = runtime.get("agent_tools")
        if isinstance(agent_tools, dict):
            if "agents" in agent_tools:
                problems.append({
                    "level": "warning",
                    "path": "runtime.agent_tools.agents",
                    "message": "agent_tools.agents is deprecated and ignored. Tool assignment must live in agents.<id>.tool_config.",
                })

    has_error = any(p.get("level") == "error" for p in problems)
    return {
        "ok": not has_error,
        "problems": problems,
        "preview": {
            "agents": len(agents) if isinstance(agents, dict) else 0,
            "snapshot_profiles": len(snapshot_profiles) if isinstance(snapshot_profiles, dict) else 0,
            "decision_prompt_profiles": len(decision_prompt_profiles) if isinstance(decision_prompt_profiles, dict) else 0,
            "system_sections": len(system_config_section) if isinstance(system_config_section, dict) else 0,
            "runtime_event_routing": int(
                isinstance(runtime, dict)
                and isinstance(runtime.get("event_routing"), dict)
                and isinstance(runtime["event_routing"].get("rules"), list)
            ),
            "runtime_agent_tools": int(
                isinstance(runtime, dict) and isinstance(runtime.get("agent_tools"), dict)
            ),
        },
    }


def apply_import_package(
    package: dict[str, Any],
    *,
    current_system_config: dict[str, Any],
    mapping: dict[str, Any] | None = None,
    replace_existing_agents: bool = False,
    import_agents: bool = True,
    import_snapshot_profiles: bool = True,
    import_decision_prompt_profiles: bool = True,
    import_bridge_tools: bool = True,
    import_event_routing: bool = True,
    import_system_config: bool = False,
    event_routing_path: Path,
    agent_tools_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    mapping = mapping or {}
    next_system = copy.deepcopy(current_system_config)
    next_agents = next_system.setdefault("agents", {})
    if not isinstance(next_agents, dict):
        next_agents = {}
        next_system["agents"] = next_agents

    package_agents = package.get("agents", {})
    if import_agents and isinstance(package_agents, dict):
        for source_id, raw_cfg in package_agents.items():
            if not isinstance(raw_cfg, dict):
                continue
            target_id = _map_agent_id(str(source_id).upper(), mapping)
            mapped_cfg = _map_agent_cfg(raw_cfg, mapping)
            if target_id in next_agents and not replace_existing_agents:
                continue
            next_agents[target_id] = mapped_cfg

    if import_snapshot_profiles:
        package_snapshot_profiles = package.get("snapshot_profiles", {})
        if isinstance(package_snapshot_profiles, dict):
            next_snapshot_profiles = next_system.setdefault("snapshot_profiles", {})
            if not isinstance(next_snapshot_profiles, dict):
                next_snapshot_profiles = {}
                next_system["snapshot_profiles"] = next_snapshot_profiles
            for name, profile in package_snapshot_profiles.items():
                if isinstance(profile, dict):
                    next_snapshot_profiles[name] = copy.deepcopy(profile)

    if import_decision_prompt_profiles:
        package_decision_profiles = package.get("decision_prompt_profiles", {})
        if isinstance(package_decision_profiles, dict):
            next_decision_profiles = next_system.setdefault("decision_prompt_profiles", {})
            if not isinstance(next_decision_profiles, dict):
                next_decision_profiles = {}
                next_system["decision_prompt_profiles"] = next_decision_profiles
            for name, profile in package_decision_profiles.items():
                if isinstance(profile, dict):
                    next_decision_profiles[name] = copy.deepcopy(profile)

    if import_system_config:
        package_system_config = package.get("system_config", {})
        if isinstance(package_system_config, dict):
            for key in ("ImportRules", "system", "database", "data"):
                value = package_system_config.get(key)
                if isinstance(value, dict):
                    next_system[key] = copy.deepcopy(value)

    next_routing = _read_json5_file(event_routing_path)
    if import_event_routing:
        runtime = package.get("runtime", {})
        packaged_routing = runtime.get("event_routing") if isinstance(runtime, dict) else None
        if isinstance(packaged_routing, dict):
            pkg_rules = packaged_routing.get("rules")
            if isinstance(pkg_rules, list):
                base_rules = next_routing.get("rules", [])
                if not isinstance(base_rules, list):
                    base_rules = []
                existing_by_id = {
                    str(r.get("id")): idx
                    for idx, r in enumerate(base_rules)
                    if isinstance(r, dict) and isinstance(r.get("id"), str)
                }
                for rule in pkg_rules:
                    if not isinstance(rule, dict):
                        continue
                    rid = rule.get("id")
                    if isinstance(rid, str) and rid in existing_by_id:
                        base_rules[existing_by_id[rid]] = rule
                    else:
                        base_rules.append(rule)
                next_routing["rules"] = base_rules

    next_agent_tools = _read_json5_file(agent_tools_path)
    if import_bridge_tools:
        runtime = package.get("runtime", {})
        packaged_tools = runtime.get("agent_tools") if isinstance(runtime, dict) else None
        if isinstance(packaged_tools, dict):
            if isinstance(packaged_tools.get("bridge_tools"), list):
                base_bridge = next_agent_tools.get("bridge_tools", [])
                if not isinstance(base_bridge, list):
                    base_bridge = []
                idx_by_name = {
                    str(item.get("name")): idx
                    for idx, item in enumerate(base_bridge)
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                }
                for item in packaged_tools["bridge_tools"]:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if isinstance(name, str) and name in idx_by_name:
                        base_bridge[idx_by_name[name]] = item
                    else:
                        base_bridge.append(item)
                next_agent_tools["bridge_tools"] = base_bridge

    return next_system, next_routing, next_agent_tools


def dump_json5_text(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"



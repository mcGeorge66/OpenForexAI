#!/usr/bin/env python3
"""LLM diagnostics tool — deep health and failure analysis for configured LLM modules.

Usage::

    python test_llm.py <llm_module_name>

Examples::

    python test_llm.py azure_openai
    python test_llm.py openai

This script is intentionally verbose and designed for troubleshooting real-world
runtime failures (including hidden adapter fallback behavior).

Exit codes:
  0 = all checks passed
  1 = at least one FAIL
  2 = no FAIL, but at least one WARN
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import sysconfig
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent

# Prevent local tools/logging.py from shadowing stdlib logging when running from tools/.
_this_dir_str = str(_THIS_DIR)
while _this_dir_str in sys.path:
    sys.path.remove(_this_dir_str)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))




@dataclass
class CheckResult:
    name: str
    status: str = "FAIL"  # PASS | WARN | FAIL
    details: list[str] = field(default_factory=list)


def _mask_secret(value: str | None, left: int = 4, right: int = 3) -> str:
    if not value:
        return "MISSING"
    if len(value) <= left + right:
        return "*" * len(value)
    return f"{value[:left]}{'*' * (len(value) - left - right)}{value[-right:]}"


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def _print_kv(key: str, value: Any) -> None:
    print(f"  {key:<24}: {value}")



def _force_stdlib_logging_module() -> None:
    """Ensure stdlib logging is loaded even if local logging.py shadows it."""
    stdlib_logging = Path(sysconfig.get_paths()["stdlib"]) / "logging" / "__init__.py"
    spec = importlib.util.spec_from_file_location("logging", stdlib_logging)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["logging"] = module

def _load_config(name: str) -> tuple[Path, dict[str, Any]]:
    cfg_path = _ROOT / "config" / "modules" / "llm" / f"{name}.json5"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config not found: {cfg_path}")
    from openforexai.config.json_loader import load_json_config
    cfg = load_json_config(cfg_path)
    if not isinstance(cfg, dict):
        raise TypeError(f"Config root must be object, got {type(cfg).__name__}")
    return cfg_path, cfg


def _create_llm(name: str, cfg: dict[str, Any]):
    import openforexai.adapters.llm  # noqa: F401
    from openforexai.registry.plugin_registry import PluginRegistry

    adapter = cfg.get("adapter", name)
    LLMClass = PluginRegistry.get_llm_provider(adapter)
    return LLMClass.from_config(cfg)


def _error_chain(exc: BaseException) -> list[str]:
    lines: list[str] = []
    cur: BaseException | None = exc
    idx = 0
    while cur is not None and idx < 8:
        prefix = "root" if idx == 0 else f"cause#{idx}"
        lines.append(f"{prefix}: {type(cur).__name__}: {cur}")

        for attr in ("status_code", "code", "type", "param"):
            if hasattr(cur, attr):
                try:
                    value = getattr(cur, attr)
                    if value is not None:
                        lines.append(f"{prefix}.{attr}: {value}")
                except Exception:
                    pass

        # OpenAI exceptions may expose HTTP response objects.
        resp = getattr(cur, "response", None)
        if resp is not None:
            try:
                status = getattr(resp, "status_code", None)
                if status is not None:
                    lines.append(f"{prefix}.response.status_code: {status}")
            except Exception:
                pass
            try:
                text = resp.text if isinstance(resp.text, str) else None
                if text:
                    preview = text.replace("\n", " ")[:800]
                    lines.append(f"{prefix}.response.body: {preview}")
            except Exception:
                pass

        nxt = cur.__cause__ or cur.__context__
        if nxt is cur:
            break
        cur = nxt
        idx += 1

    return lines


def _content_preview(value: Any, max_len: int = 220) -> str:
    if value is None:
        return "<None>"
    if isinstance(value, str):
        t = value.replace("\n", " ").strip()
        if len(t) > max_len:
            return t[:max_len] + " ..."
        return t
    txt = str(value).replace("\n", " ").strip()
    return txt[:max_len] + (" ..." if len(txt) > max_len else "")


async def _check_complete(llm) -> CheckResult:
    result = CheckResult("Adapter complete()")
    t0 = time.perf_counter()
    try:
        resp = await llm.complete(
            system_prompt="You are a test assistant.",
            user_message="Reply with exactly: OK",
            max_tokens=32,
        )
        dt = (time.perf_counter() - t0) * 1000
        result.status = "PASS"
        result.details.extend([
            f"latency_ms={dt:.1f}",
            f"model={getattr(resp, 'model', '<unknown>')}",
            f"input_tokens={getattr(resp, 'input_tokens', '?')} output_tokens={getattr(resp, 'output_tokens', '?')}",
            f"content={_content_preview(getattr(resp, 'content', None))}",
        ])
    except Exception as exc:
        result.status = "FAIL"
        result.details.extend(_error_chain(exc))
    return result


async def _check_tool_loop_adapter(llm) -> CheckResult:
    result = CheckResult("Adapter complete_with_tools()")
    tool_spec = {
        "name": "get_time",
        "description": "Returns current UTC time.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    }
    t0 = time.perf_counter()
    try:
        resp = await llm.complete_with_tools(
            system_prompt=(
                "You are a test assistant. "
                "Call the get_time tool first, then return a short sentence."
            ),
            messages=[{"role": "user", "content": "Use get_time now."}],
            tools=[tool_spec],
            max_tokens=120,
        )
        dt = (time.perf_counter() - t0) * 1000

        wants_tools = bool(getattr(resp, "wants_tools", False))
        calls = getattr(resp, "tool_calls", []) or []
        stop_reason = getattr(resp, "stop_reason", "?")

        # Not always an error (model may answer directly), but suspicious for diagnostics.
        if wants_tools and calls:
            result.status = "PASS"
        else:
            result.status = "WARN"

        result.details.extend([
            f"latency_ms={dt:.1f}",
            f"stop_reason={stop_reason}",
            f"wants_tools={wants_tools}",
            f"tool_call_count={len(calls)}",
            f"content={_content_preview(getattr(resp, 'content', None))}",
        ])
        if result.status == "WARN":
            result.details.append(
                
                    "No tool call requested although prompt explicitly requested one; "
                    "this can indicate model/tool-routing issues or adapter fallback behavior."
                
            )
    except Exception as exc:
        result.status = "FAIL"
        result.details.extend(_error_chain(exc))
    return result


async def _check_azure_raw_calls(llm) -> list[CheckResult]:
    """Azure-specific raw API probes bypassing adapter retry/fallback logic."""
    results: list[CheckResult] = []

    if not hasattr(llm, "_client") or not hasattr(llm, "_deployment"):
        return results

    client = getattr(llm, "_client")
    deployment = getattr(llm, "_deployment")

    # Raw basic completion
    r1 = CheckResult("Azure raw chat.completions (no tools)")
    t0 = time.perf_counter()
    try:
        resp = await client.chat.completions.create(
            model=deployment,
            max_completion_tokens=32,
            messages=[
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user", "content": "Reply with OK only."},
            ],
        )
        dt = (time.perf_counter() - t0) * 1000
        msg = resp.choices[0].message
        r1.status = "PASS"
        r1.details.extend([
            f"latency_ms={dt:.1f}",
            f"model={resp.model}",
            f"finish_reason={resp.choices[0].finish_reason}",
            f"content={_content_preview(getattr(msg, 'content', None))}",
        ])
    except Exception as exc:
        r1.status = "FAIL"
        r1.details.extend(_error_chain(exc))
    results.append(r1)

    # Raw tool call with forced tool choice
    r2 = CheckResult("Azure raw chat.completions (tools, forced)")
    t1 = time.perf_counter()
    try:
        resp = await client.chat.completions.create(
            model=deployment,
            max_completion_tokens=120,
            messages=[
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user", "content": "Use the get_time tool."},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_time",
                        "description": "Return UTC time.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "get_time"}},
        )
        dt = (time.perf_counter() - t1) * 1000
        msg = resp.choices[0].message
        calls = getattr(msg, "tool_calls", None) or []
        if calls:
            r2.status = "PASS"
        else:
            r2.status = "WARN"
        r2.details.extend([
            f"latency_ms={dt:.1f}",
            f"model={resp.model}",
            f"finish_reason={resp.choices[0].finish_reason}",
            f"tool_call_count={len(calls)}",
        ])
        if r2.status == "WARN":
            r2.details.append("API call succeeded but no tool_calls returned despite forced tool_choice.")
    except Exception as exc:
        r2.status = "FAIL"
        r2.details.extend(_error_chain(exc))
    results.append(r2)

    return results


def _emit_result(res: CheckResult) -> None:
    icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(res.status, "[????]")
    print(f"{icon} {res.name}")
    for line in res.details:
        print(f"  - {line}")


async def _run_tests(name: str) -> tuple[list[CheckResult], dict[str, Any]]:
    checks: list[CheckResult] = []

    # Config load and static inspection
    cfg_check = CheckResult("Load module config")
    try:
        cfg_path, cfg = _load_config(name)
        cfg_check.status = "PASS"
        cfg_check.details.extend([
            f"path={cfg_path}",
            f"adapter={cfg.get('adapter')}",
            f"model={cfg.get('model')}",
        ])
    except Exception as exc:
        cfg_check.status = "FAIL"
        cfg_check.details.extend(_error_chain(exc))
        checks.append(cfg_check)
        return checks, {}
    checks.append(cfg_check)

    # Config sanity hints
    sanity = CheckResult("Config sanity")
    adapter = str(cfg.get("adapter", "")).strip().lower()
    key = str(cfg.get("api_key", "") or "")
    endpoint = str(cfg.get("endpoint", "") or "")
    deployment = str(cfg.get("deployment", "") or "")

    missing: list[str] = []
    if not adapter:
        missing.append("adapter")
    if not key:
        missing.append("api_key")
    if adapter == "azure":
        if not endpoint:
            missing.append("endpoint")
        if not deployment:
            missing.append("deployment")

    if missing:
        sanity.status = "FAIL"
        sanity.details.append("Missing required keys: " + ", ".join(missing))
    else:
        sanity.status = "PASS"

    sanity.details.extend([
        f"api_key(masked)={_mask_secret(key)}",
        f"endpoint={endpoint or '<n/a>'}",
        f"deployment={deployment or '<n/a>'}",
        f"api_version={cfg.get('api_version', '<n/a>')}",
    ])

    if key and "${" in key:
        sanity.status = "WARN"
        sanity.details.append("api_key still contains placeholder syntax (${...}); env substitution may have failed.")

    checks.append(sanity)
    if sanity.status == "FAIL":
        return checks, cfg

    # Adapter init
    init_check = CheckResult("Instantiate adapter")
    try:
        llm = _create_llm(name, cfg)
        init_check.status = "PASS"
        init_check.details.extend([
            f"provider_class={llm.__class__.__name__}",
            f"model_id={getattr(llm, 'model_id', '<unknown>')}",
        ])
    except Exception as exc:
        init_check.status = "FAIL"
        init_check.details.extend(_error_chain(exc))
        checks.append(init_check)
        return checks, cfg
    checks.append(init_check)

    # Runtime checks
    checks.append(await _check_complete(llm))
    checks.append(await _check_tool_loop_adapter(llm))

    # Azure deep probes (bypass adapter behavior)
    checks.extend(await _check_azure_raw_calls(llm))

    return checks, cfg


def main() -> None:
    _force_stdlib_logging_module()
    import asyncio

    parser = argparse.ArgumentParser(
        description="Deep diagnostics for one configured LLM module.",
    )
    parser.add_argument(
        "llm_module_name",
        help="Module name from config/modules/llm/<name>.json5 (e.g. azure_openai)",
    )
    args = parser.parse_args()
    name = args.llm_module_name

    _print_header("LLM Diagnostics")
    _print_kv("module", name)
    _print_kv("workspace", str(_ROOT))
    _print_kv("python", sys.version.split()[0])

    try:
        checks, cfg = asyncio.run(_run_tests(name))
    except KeyboardInterrupt:
        print("\nAborted by user")
        sys.exit(130)
    except Exception as exc:
        print("\n[FAIL] Unexpected diagnostics crash")
        print("  " + "\n  ".join(_error_chain(exc)))
        traceback.print_exc()
        sys.exit(1)

    _print_header("Results")
    for c in checks:
        _emit_result(c)

    pass_count = sum(1 for c in checks if c.status == "PASS")
    warn_count = sum(1 for c in checks if c.status == "WARN")
    fail_count = sum(1 for c in checks if c.status == "FAIL")

    _print_header("Summary")
    _print_kv("checks_total", len(checks))
    _print_kv("pass", pass_count)
    _print_kv("warn", warn_count)
    _print_kv("fail", fail_count)

    if fail_count > 0:
        print("\nOverall status: FAIL")
        sys.exit(1)
    if warn_count > 0:
        print("\nOverall status: WARN")
        sys.exit(2)

    print("\nOverall status: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()



#!/usr/bin/env python3
"""LLM module test — loads a named LLM module and verifies the interface.

Usage::

    python test_llm.py anthropic_claude
    python test_llm.py openai_gpt4

The test:
  1. Loads config/modules/llm/<name>.json
  2. Instantiates the adapter via PluginRegistry
  3. Sends a simple completion request
  4. Sends a tool-use request
  5. Prints a pass/fail summary

Exit code: 0 = all tests passed, 1 = at least one test failed.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent


def _load_config(name: str) -> dict:
    cfg_path = _ROOT / "config" / "modules" / "llm" / f"{name}.json"
    if not cfg_path.exists():
        print(f"[ERROR] Config not found: {cfg_path}")
        sys.exit(1)
    from openforexai.config.json_loader import load_json_config
    return load_json_config(cfg_path)


def _create_llm(name: str, cfg: dict):
    import openforexai.adapters.llm  # trigger registration
    from openforexai.registry.plugin_registry import PluginRegistry

    adapter = cfg.get("adapter", name)
    LLMClass = PluginRegistry.get_llm_provider(adapter)

    if adapter == "anthropic":
        return LLMClass(api_key=cfg.get("api_key", ""), model=cfg.get("model", "claude-opus-4-6"))
    elif adapter == "lmstudio":
        return LLMClass(base_url=cfg.get("base_url", "http://localhost:1234"), model=cfg.get("model", "local"))
    else:
        return LLMClass(api_key=cfg.get("api_key", ""), model=cfg.get("model", "gpt-4o"))


async def _run_tests(name: str) -> bool:
    cfg = _load_config(name)
    print(f"\nLLM module: {name!r}")
    print(f"  adapter : {cfg.get('adapter')}")
    print(f"  model   : {cfg.get('model')}")
    print(f"  api_key : {'SET' if cfg.get('api_key') else 'MISSING'}")
    print()

    if not cfg.get("api_key"):
        print("[FAIL] api_key is empty — check environment variable")
        return False

    llm = _create_llm(name, cfg)
    passed = True

    # ── Test 1: simple completion ─────────────────────────────────────────────
    print("Test 1: simple completion...")
    try:
        resp = await llm.complete(
            system_prompt="You are a helpful assistant.",
            user_message="Reply with exactly: OK",
            max_tokens=10,
        )
        print(f"  response : {resp.content!r}")
        print(f"  tokens   : in={resp.input_tokens} out={resp.output_tokens}")
        print(f"  [PASS]")
    except Exception as e:
        print(f"  [FAIL] {e}")
        passed = False

    # ── Test 2: tool-use completion ───────────────────────────────────────────
    print("\nTest 2: tool-use completion...")
    tool_spec = {
        "name": "get_time",
        "description": "Returns the current time.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }
    try:
        resp = await llm.complete_with_tools(
            system_prompt="You are a helpful assistant. Use the get_time tool.",
            messages=[{"role": "user", "content": "What time is it? Use the tool."}],
            tools=[tool_spec],
            max_tokens=100,
        )
        print(f"  wants_tools : {resp.wants_tools}")
        print(f"  tool_calls  : {len(resp.tool_calls)}")
        if resp.tool_calls:
            print(f"  first call  : {resp.tool_calls[0].name}")
        print(f"  [PASS]")
    except Exception as e:
        print(f"  [FAIL] {e}")
        passed = False

    return passed


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <llm_module_name>")
        print(f"  e.g. python {sys.argv[0]} anthropic_claude")
        sys.exit(1)

    name = sys.argv[1]
    ok = asyncio.run(_run_tests(name))

    print()
    if ok:
        print("All tests PASSED")
        sys.exit(0)
    else:
        print("Some tests FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()

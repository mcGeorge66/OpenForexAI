#!/usr/bin/env python3
"""Broker module test — loads a named broker module and verifies the interface.

Usage::

    python test_broker.py oanda
    python test_broker.py mt5

The test:
  1. Loads config/modules/broker/<name>.json
  2. Instantiates the adapter via PluginRegistry
  3. Connects to the broker
  4. Fetches account status
  5. Fetches open positions
  6. Fetches M5 candles for the first configured pair
  7. Disconnects
  8. Prints a pass/fail summary

Exit code: 0 = all tests passed, 1 = at least one test failed.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).parent


def _load_module_config(name: str) -> dict:
    cfg_path = _ROOT / "config" / "modules" / "broker" / f"{name}.json"
    if not cfg_path.exists():
        print(f"[ERROR] Config not found: {cfg_path}")
        sys.exit(1)
    from openforexai.config.json_loader import load_json_config
    return load_json_config(cfg_path)


def _get_test_pair(name: str) -> str:
    """Pick a test pair from system.json for this broker."""
    try:
        from openforexai.config.json_loader import load_json_config
        sys_cfg = load_json_config(_ROOT / "config" / "system.json")
        for cfg in sys_cfg.get("agents", {}).values():
            if cfg.get("broker") == name and cfg.get("pair"):
                return cfg["pair"]
    except Exception:
        pass
    return "EURUSD"


def _create_broker(name: str, cfg: dict):
    import openforexai.adapters.brokers  # trigger registration
    from openforexai.registry.plugin_registry import PluginRegistry

    adapter = cfg.get("adapter", name)
    BrokerClass = PluginRegistry.get_broker(adapter)

    if adapter == "oanda":
        return BrokerClass(
            api_key=cfg.get("api_key", ""),
            account_id=cfg.get("account_id", ""),
            practice=cfg.get("practice", True),
        )
    elif adapter == "mt5":
        return BrokerClass(
            login=int(cfg.get("login", 0)),
            password=cfg.get("password", ""),
            server=cfg.get("server", ""),
        )
    else:
        raise ValueError(f"Unknown broker adapter: {adapter!r}")


async def _run_tests(name: str) -> bool:
    cfg = _load_module_config(name)
    pair = _get_test_pair(name)

    print(f"\nBroker module : {name!r}")
    print(f"  adapter     : {cfg.get('adapter')}")
    print(f"  practice    : {cfg.get('practice', 'N/A')}")
    print(f"  api_key     : {'SET' if cfg.get('api_key') else 'MISSING'}")
    print(f"  test pair   : {pair}")
    print()

    broker = _create_broker(name, cfg)
    passed = True

    # ── Test 1: connect ───────────────────────────────────────────────────────
    print("Test 1: connect...")
    try:
        await broker.connect()
        print(f"  short_name : {broker.short_name!r}")
        print(f"  [PASS]")
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False

    # ── Test 2: account status ────────────────────────────────────────────────
    print("\nTest 2: account status...")
    try:
        status = await broker.get_account_status()
        print(f"  balance     : {status.balance} {status.currency}")
        print(f"  equity      : {status.equity}")
        print(f"  margin_free : {status.margin_free}")
        print(f"  leverage    : {status.leverage}")
        print(f"  trade_ok    : {status.trade_allowed}")
        print(f"  [PASS]")
    except Exception as e:
        print(f"  [FAIL] {e}")
        passed = False

    # ── Test 3: open positions ─────────────────────────────────────────────────
    print("\nTest 3: open positions...")
    try:
        positions = await broker.get_open_positions()
        print(f"  open positions : {len(positions)}")
        for p in positions[:3]:
            print(f"    {p.pair} {p.direction} {p.units} @ {p.entry_price}  pnl={p.unrealized_pnl}")
        print(f"  [PASS]")
    except Exception as e:
        print(f"  [FAIL] {e}")
        passed = False

    # ── Test 4: fetch M5 candles ──────────────────────────────────────────────
    print(f"\nTest 4: fetch M5 candles ({pair})...")
    try:
        candles = await broker.get_historical_m5_candles(pair=pair, count=10)
        print(f"  received : {len(candles)} candles")
        if candles:
            c = candles[-1]
            print(f"  latest   : {c.timestamp}  O={c.open} H={c.high} L={c.low} C={c.close}")
        print(f"  [PASS]")
    except Exception as e:
        print(f"  [FAIL] {e}")
        passed = False

    # ── Disconnect ────────────────────────────────────────────────────────────
    try:
        await broker.disconnect()
    except Exception:
        pass

    return passed


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <broker_module_name>")
        print(f"  e.g. python {sys.argv[0]} oanda")
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

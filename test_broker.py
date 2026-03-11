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
    cfg_path = _ROOT / "config" / "modules" / "broker" / f"{name}.json5"
    if not cfg_path.exists():
        print(f"[ERROR] Config not found: {cfg_path}")
        sys.exit(1)
    from openforexai.config.json_loader import load_json_config
    return load_json_config(cfg_path)


def _get_test_pair(name: str, cfg: dict) -> str:
    """Pick a test pair: module config first, then system.json5 fallback."""
    if cfg.get("pair"):
        return cfg["pair"]
    try:
        from openforexai.config.json_loader import load_json_config
        sys_cfg = load_json_config(_ROOT / "config" / "system.json5")
        for agent_cfg in sys_cfg.get("agents", {}).values():
            if agent_cfg.get("broker") == name and agent_cfg.get("pair"):
                return agent_cfg["pair"]
    except Exception:
        pass
    return "EURUSD"


def _create_broker(cfg: dict):
    import openforexai.adapters.brokers  # trigger registration
    from openforexai.registry.plugin_registry import PluginRegistry

    adapter = cfg.get("adapter", "")
    BrokerClass = PluginRegistry.get_broker(adapter)
    return BrokerClass.from_config(cfg)


async def _run_tests(name: str) -> bool:
    cfg = _load_module_config(name)
    pair = _get_test_pair(name, cfg)

    print(f"\nBroker module : {name!r}")
    print(f"  adapter     : {cfg.get('adapter')}")
    print(f"  short_name  : {cfg.get('short_name', '(not set)')}")
    print(f"  practice    : {cfg.get('practice', 'N/A')}")
    print(f"  api_url     : {cfg.get('api_url', '(default)')}")
    print(f"  api_key     : {'SET' if cfg.get('api_key') else 'MISSING'}")
    print(f"  pair        : {cfg.get('pair', '(from system.json5)')}")
    print(f"  test pair   : {pair}")
    print()

    broker = _create_broker(cfg)
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

    # ── Test 5: background M5 loop ───────────────────────────────────────────
    print("\nTest 5: background M5 loop (patched fast sleep)...")
    try:
        from openforexai.adapters.brokers.base import BrokerBase
        from openforexai.models.messaging import EventType

        events: list = []

        class _StubBus:
            async def publish(self, msg):
                events.append(msg)

        class _StubRepo:
            async def save_account_status(self, s):
                pass
            async def get_open_order_book_entries(self, b, p):
                return []

        # Patch _sleep_until_next_m5 so the loop fires after 1 s instead of up to 5 min
        _original_sleep = BrokerBase._sleep_until_next_m5
        async def _fast_sleep():
            await asyncio.sleep(1)
        BrokerBase._sleep_until_next_m5 = staticmethod(_fast_sleep)

        try:
            broker.start_background_tasks(
                pair=pair,
                event_bus=_StubBus(),
                repository=_StubRepo(),
            )
            await asyncio.sleep(5)   # 1 s sleep + API round-trip + margin
            broker.stop_background_tasks()
        finally:
            # _original_sleep is the raw function (descriptor protocol strips staticmethod).
            # Wrap it back so self is not passed on the next call.
            BrokerBase._sleep_until_next_m5 = staticmethod(_original_sleep)

        candle_events = [e for e in events if e.event_type == EventType.M5_CANDLE_AVAILABLE]
        if candle_events:
            ev = candle_events[0]
            c  = ev.payload.get("candle", {})
            print(f"  event          : M5_CANDLE_AVAILABLE")
            print(f"  pair           : {ev.payload.get('pair')}")
            print(f"  timestamp      : {c.get('timestamp')}")
            print(f"  close          : {c.get('close')}")
            print(f"  total events   : {len(events)}")
            print(f"  [PASS]")
        else:
            print(f"  no M5_CANDLE_AVAILABLE received within 5 s")
            print(f"  total events   : {len(events)}")
            print(f"  [FAIL]")
            passed = False
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  [FAIL] {e}")
        passed = False

    # ── Test 6: live M5 streaming (real timing, Ctrl+C to exit) ─────────────
    from datetime import datetime, timezone as _tz
    _now = datetime.now(_tz.utc)
    _secs_to_next = int(
        (((int(_now.timestamp() / 60) // 5) + 1) * 5 * 60) - _now.timestamp()
    ) + 10

    print(f"\nTest 6: live M5 streaming — press Ctrl+C to exit")
    print(f"  Next candle in approx. {_secs_to_next} s  "
          f"({_secs_to_next // 60}:{_secs_to_next % 60:02d} min)")
    print(f"  Streaming {pair} via {broker.short_name!r} ...\n")

    _live_count = 0

    try:
        from openforexai.models.messaging import EventType as _ET
    except ImportError:
        _ET = None

    class _LiveBus:
        async def publish(self, msg):
            nonlocal _live_count
            if _ET and msg.event_type == _ET.M5_CANDLE_AVAILABLE:
                _live_count += 1
                c = msg.payload.get("candle", {})
                print(
                    f"  [{_live_count:>4}] {c.get('timestamp')}  "
                    f"O={c.get('open')} H={c.get('high')} "
                    f"L={c.get('low')} C={c.get('close')}  "
                    f"spread={c.get('spread')}"
                )

    class _LiveRepo:
        async def save_account_status(self, s):
            pass
        async def get_open_order_book_entries(self, b, p):
            return []

    _TIMEOUT = 30 * 60  # 30 minutes

    broker.start_background_tasks(
        pair=pair,
        event_bus=_LiveBus(),
        repository=_LiveRepo(),
    )
    try:
        await asyncio.sleep(_TIMEOUT)
        print(f"\n  30-minute timeout reached.")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print(f"\n  Stopped by user.")
    finally:
        broker.stop_background_tasks()
        print(f"  Total candles received: {_live_count}")

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


#!/usr/bin/env python
"""Backfill missing close result data for already closed order book entries.

Usage:
    python scripts/backfill_order_results.py
    python scripts/backfill_order_results.py --broker OXS_T
    python scripts/backfill_order_results.py --broker mt5_oxs_t --pair EURUSD --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

from openforexai.config.json_loader import load_json_config
from openforexai.registry.plugin_registry import PluginRegistry


ROOT = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill missing closed-trade result fields from the broker history."
    )
    parser.add_argument("--config", default="config/system.json5", help="Path to system config.")
    parser.add_argument(
        "--broker",
        default=None,
        help="Optional broker filter. Accepts module name (e.g. mt5_oxs_t) or short name (e.g. OXS_T).",
    )
    parser.add_argument("--pair", default=None, help="Optional pair filter, e.g. EURUSD.")
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Max number of order book entries to inspect per broker.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without writing to the database.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Also overwrite existing result fields with broker history values.",
    )
    return parser.parse_args()


def _resolve_config_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _coerce_decimal(value: Any) -> Any:
    if value is None:
        return None
    return value


def _needs_backfill(entry: Any, overwrite: bool) -> bool:
    if str(getattr(entry, "status", "")).upper() != "CLOSED":
        return False
    if not getattr(entry, "broker_order_id", None):
        return False
    if overwrite:
        return True
    return any(
        getattr(entry, field, None) is None
        for field in ("pnl_account_currency", "close_price", "closed_at", "close_reasoning")
    )


def _build_updates(entry: Any, broker_result: dict[str, Any], overwrite: bool) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if not isinstance(broker_result, dict):
        return updates

    for field in ("pnl_account_currency", "close_price", "closed_at"):
        value = broker_result.get(field)
        if value is None:
            continue
        current = getattr(entry, field, None)
        if overwrite or current is None:
            updates[field] = _coerce_decimal(value)

    reason = broker_result.get("close_reason")
    if isinstance(reason, str) and reason.strip():
        current_reasoning = getattr(entry, "close_reasoning", None)
        if overwrite or not current_reasoning:
            updates["close_reasoning"] = reason.strip()

    return updates


async def _create_repository(system_config: dict[str, Any]):
    import openforexai.adapters.database  # noqa: F401

    db_cfg = system_config.get("database", {})
    backend = db_cfg.get("backend", "sqlite")
    repo_class = PluginRegistry.get_repository(backend)
    if backend == "sqlite":
        sqlite_path_raw = str(db_cfg.get("sqlite_path", "./data/openforexai.db"))
        sqlite_path = Path(sqlite_path_raw)
        if not sqlite_path.is_absolute():
            sqlite_path = (ROOT / sqlite_path).resolve()
        repository = repo_class(db_path=str(sqlite_path))
    else:
        repository = repo_class(
            database_url=db_cfg.get("database_url", ""),
            pool_size=db_cfg.get("pool_size", 5),
        )
    await repository.initialize()
    return repository


async def _connect_brokers(system_config: dict[str, Any], broker_filter: str | None):
    import openforexai.adapters.brokers  # noqa: F401

    connected: list[tuple[str, Any]] = []
    mod_cfg = system_config.get("modules", {}).get("broker", {})
    normalized_filter = str(broker_filter).strip().upper() if broker_filter else None
    attempted = 0

    for broker_name, cfg_path in mod_cfg.items():
        broker_mod = load_json_config(ROOT / cfg_path)
        adapter = broker_mod.get("adapter", broker_name)
        broker_class = PluginRegistry.get_broker(adapter)
        broker = broker_class.from_config(broker_mod)
        short_name = str(getattr(broker, "short_name", "")).strip()
        if normalized_filter and normalized_filter not in {broker_name.upper(), short_name.upper()}:
            continue
        attempted += 1
        try:
            await broker.connect()
        except Exception as exc:
            try:
                await broker.disconnect()
            except Exception:
                pass
            print(f"[warn] Broker connect failed for {broker_name} ({short_name}): {exc}")
            if normalized_filter:
                raise
            continue
        connected.append((broker_name, broker))
    return connected, attempted


async def _disconnect_brokers(connected: list[tuple[str, Any]]) -> None:
    for _, broker in connected:
        try:
            await broker.disconnect()
        except Exception as exc:
            print(f"[warn] Broker disconnect failed for {getattr(broker, 'short_name', '?')}: {exc}")


async def main(args: argparse.Namespace) -> None:
    _load_env(ROOT / ".env")
    system_config = load_json_config(_resolve_config_path(args.config))
    repository = await _create_repository(system_config)
    connected_brokers, attempted_brokers = await _connect_brokers(system_config, args.broker)
    if not connected_brokers:
        if attempted_brokers == 0:
            raise SystemExit("No matching brokers found for backfill.")
        raise SystemExit("No brokers could be connected for backfill.")

    total_checked = 0
    total_candidates = 0
    total_updated = 0

    try:
        for broker_module_name, broker in connected_brokers:
            broker_short_name = str(getattr(broker, "short_name", "")).strip()
            entries = await repository.get_order_book_entries(
                broker_name=broker_short_name,
                pair=(str(args.pair).upper() if args.pair else None),
                limit=max(1, int(args.limit)),
            )
            print(f"[broker] {broker_module_name} ({broker_short_name}) -> {len(entries)} entries loaded")

            for entry in entries:
                total_checked += 1
                if not _needs_backfill(entry, overwrite=args.overwrite):
                    continue

                total_candidates += 1
                broker_result = await broker.get_closed_trade_result(
                    entry.broker_order_id or "",
                    pair=entry.pair,
                    sync_key=entry.sync_key,
                )
                updates = _build_updates(entry, broker_result or {}, overwrite=args.overwrite)
                if not updates:
                    continue

                total_updated += 1
                print(
                    f"[update] {entry.id} {entry.pair} {entry.direction} "
                    f"fields={','.join(sorted(updates.keys()))}"
                )
                if not args.dry_run:
                    await repository.update_order_book_entry(str(entry.id), updates)

        mode = "dry-run" if args.dry_run else "applied"
        print(
            f"[done] checked={total_checked} candidates={total_candidates} "
            f"updated={total_updated} mode={mode}"
        )
    finally:
        await _disconnect_brokers(connected_brokers)


if __name__ == "__main__":
    asyncio.run(main(parse_args()))

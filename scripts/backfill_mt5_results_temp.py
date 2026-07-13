#!/usr/bin/env python
"""Temporary MT5-only backfill for closed orderbook entries.

This script tries to reuse the currently logged-in MT5 terminal session first.
If that fails, it falls back to the configured login credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
    parser = argparse.ArgumentParser(description="Temporary MT5-only orderbook result backfill.")
    parser.add_argument("--config", default="config/system.json5")
    parser.add_argument("--broker-module", default="mt5_oxs_t")
    parser.add_argument("--pair", default=None)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _resolve_config_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


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


def _mt5_closed_trade_result(mt5: Any, position_id: str) -> dict[str, Any] | None:
    if not position_id:
        return None

    deals = None
    try:
        deals = mt5.history_deals_get(position=int(position_id))
    except Exception:
        deals = None

    if not deals:
        date_to = datetime.now(UTC)
        date_from = date_to - timedelta(days=90)
        recent_deals = mt5.history_deals_get(date_from, date_to)
        if recent_deals:
            deals = [
                deal for deal in recent_deals
                if str(getattr(deal, "position_id", "")) == str(position_id)
            ]

    if not deals:
        return None

    sorted_deals = sorted(
        deals,
        key=lambda deal: int(getattr(deal, "time_msc", 0) or 0) or int(getattr(deal, "time", 0) or 0),
    )
    exit_deal = None
    for deal in reversed(sorted_deals):
        entry_flag = getattr(deal, "entry", None)
        if entry_flag in {1, 3}:  # DEAL_ENTRY_OUT / DEAL_ENTRY_OUT_BY
            exit_deal = deal
            break
    if exit_deal is None:
        exit_deal = sorted_deals[-1]

    closed_at = None
    deal_time = getattr(exit_deal, "time", None)
    if deal_time:
        closed_at = datetime.fromtimestamp(int(deal_time), tz=UTC)

    pnl = Decimal(str(getattr(exit_deal, "profit", 0) or 0))
    price = getattr(exit_deal, "price", None)
    reason = getattr(exit_deal, "comment", None) or getattr(exit_deal, "reason", None)
    return {
        "pnl_account_currency": pnl,
        "close_price": Decimal(str(price)) if price is not None else None,
        "closed_at": closed_at,
        "close_reasoning": str(reason).strip() if reason is not None and str(reason).strip() else None,
    }


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
    for field in ("pnl_account_currency", "close_price", "closed_at", "close_reasoning"):
        value = broker_result.get(field)
        if value is None:
            continue
        current = getattr(entry, field, None)
        if overwrite or current is None:
            updates[field] = value
    return updates


def _initialize_mt5(mt5_cfg: dict[str, Any]) -> Any:
    import MetaTrader5 as mt5  # type: ignore[import]

    installation_path = str(mt5_cfg.get("installation_path", "") or "").strip()
    init_kwargs: dict[str, Any] = {}
    if installation_path:
        init_kwargs["path"] = installation_path

    if mt5.initialize(**init_kwargs):
        return mt5

    try:
        mt5.shutdown()
    except Exception:
        pass

    login_kwargs: dict[str, Any] = {
        "login": int(mt5_cfg.get("account_id", 0) or 0),
        "password": mt5_cfg.get("password", ""),
        "server": mt5_cfg.get("server", ""),
    }
    if installation_path:
        login_kwargs["path"] = installation_path

    if not mt5.initialize(**login_kwargs):
        error = mt5.last_error()
        try:
            mt5.shutdown()
        except Exception:
            pass
        raise ConnectionError(f"MT5 initialize failed: {error}")

    return mt5


async def main(args: argparse.Namespace) -> None:
    import openforexai.adapters.brokers  # noqa: F401

    _load_env(ROOT / ".env")
    system_config = load_json_config(_resolve_config_path(args.config))
    repository = await _create_repository(system_config)

    broker_module_name = str(args.broker_module).strip()
    broker_modules = system_config.get("modules", {}).get("broker", {})
    cfg_path = broker_modules.get(broker_module_name)
    if not cfg_path:
        raise SystemExit(f"Broker module {broker_module_name!r} not found in system config.")

    mt5_cfg = load_json_config(ROOT / cfg_path)
    short_name = str(mt5_cfg.get("short_name", "")).strip()
    if not short_name:
        raise SystemExit("MT5 broker config has no short_name.")

    try:
        mt5 = _initialize_mt5(mt5_cfg)
    except Exception as exc:
        raise SystemExit(
            "MT5 connection failed for temporary backfill. "
            "Either no logged-in MT5 terminal session is available or the configured "
            f"credentials are rejected. Details: {exc}"
        ) from exc
    try:
        entries = await repository.get_order_book_entries(
            broker_name=short_name,
            pair=(str(args.pair).upper() if args.pair else None),
            limit=max(1, int(args.limit)),
        )
        print(f"[broker] {broker_module_name} ({short_name}) -> {len(entries)} entries loaded")

        total_checked = 0
        total_candidates = 0
        total_updated = 0

        for entry in entries:
            total_checked += 1
            if not _needs_backfill(entry, args.overwrite):
                continue

            total_candidates += 1
            broker_result = _mt5_closed_trade_result(mt5, entry.broker_order_id or "")
            if not broker_result:
                continue

            updates = _build_updates(entry, broker_result, args.overwrite)
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
        try:
            await repository.close()
        except Exception:
            pass
        try:
            mt5.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main(parse_args()))

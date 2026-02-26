#!/usr/bin/env python
"""CLI: run a backtest for a given pair and date range.

Usage:
    python scripts/run_backtest.py --pair EURUSD --start 2024-01-01 --end 2024-03-31
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a backtest for a forex pair.")
    parser.add_argument("--pair", required=True, help="Forex pair, e.g. EURUSD")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--config",
        default="config/default.yaml",
        help="Path to config YAML (default: config/default.yaml)",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    from openforexai.config.loader import load_yaml_config
    from openforexai.config.settings import Settings

    config = load_yaml_config(Path(args.config))
    settings = Settings(**config)

    print(f"[backtest] pair={args.pair}  start={args.start}  end={args.end}")
    print(f"[backtest] db={settings.database.sqlite_path}")

    # TODO: implement full historical replay using stored candles + prompt candidates
    print("[backtest] Full historical replay not yet implemented.")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))

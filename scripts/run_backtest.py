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
        default="config/system.json5",
        help="Path to config JSON5 (default: config/system.json5)",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    from openforexai.config.json_loader import load_json_config

    config = load_json_config(Path(args.config))

    print(f"[backtest] pair={args.pair}  start={args.start}  end={args.end}")
    print(f"[backtest] db={config['database']['sqlite_path']}")

    # TODO: implement full historical replay using stored candles + prompt candidates
    print("[backtest] Full historical replay not yet implemented.")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))



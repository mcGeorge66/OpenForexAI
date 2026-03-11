#!/usr/bin/env python
"""CLI: export the currently active system prompt for each pair.

Usage:
    python scripts/export_prompts.py [--output prompts.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export active prompts per pair.")
    parser.add_argument("--output", default="prompts.json", help="Output file (JSON/JSON5-compatible)")
    parser.add_argument("--config", default="config/system.json5")
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    import aiosqlite
    from openforexai.config.json_loader import load_json_config

    config = load_json_config(Path(args.config))
    db_path = config["database"]["sqlite_path"]
    pairs = sorted({v["pair"] for v in config["agents"].values() if "pair" in v})

    result: dict[str, str] = {}
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        for pair in pairs:
            cursor = await conn.execute(
                "SELECT system_prompt FROM prompt_candidates "
                "WHERE pair=? AND is_active=1 ORDER BY version DESC LIMIT 1",
                (pair,),
            )
            row = await cursor.fetchone()
            result[pair] = row["system_prompt"] if row else "(no active prompt — using default)"

    out_path = Path(args.output)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Exported {len(result)} prompts -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))



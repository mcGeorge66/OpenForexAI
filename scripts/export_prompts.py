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
    parser.add_argument("--output", default="prompts.json", help="Output file (JSON)")
    parser.add_argument("--config", default="config/default.yaml")
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    from openforexai.config.loader import load_yaml_config
    from openforexai.config.settings import Settings
    from openforexai.adapters.database.sqlite import SQLiteRepository

    config = load_yaml_config(Path(args.config))
    settings = Settings(**config)

    repo = SQLiteRepository(db_path=settings.database.sqlite_path)
    await repo.initialize()

    result: dict[str, str] = {}
    for pair in settings.pairs:
        candidate = await repo.get_best_prompt(pair)
        if candidate:
            result[pair] = candidate.system_prompt
        else:
            result[pair] = "(no active prompt — using default)"

    await repo.close()

    out_path = Path(args.output)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Exported {len(result)} prompts → {out_path}")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))

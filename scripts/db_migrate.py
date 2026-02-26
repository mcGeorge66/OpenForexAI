#!/usr/bin/env python
"""CLI: run database migrations.

Usage:
    python scripts/db_migrate.py [--config config/default.yaml]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DB migrations.")
    parser.add_argument("--config", default="config/default.yaml")
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    from openforexai.config.loader import load_yaml_config
    from openforexai.config.settings import Settings
    from openforexai.adapters.database.sqlite import SQLiteRepository

    config = load_yaml_config(Path(args.config))
    settings = Settings(**config)

    if settings.database.backend != "sqlite":
        print(f"[migrate] Backend '{settings.database.backend}' migrations not yet automated.")
        return

    repo = SQLiteRepository(db_path=settings.database.sqlite_path)
    await repo.initialize()
    await repo.close()
    print(f"[migrate] Migrations applied to {settings.database.sqlite_path}")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))

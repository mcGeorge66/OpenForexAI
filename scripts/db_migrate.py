#!/usr/bin/env python
"""CLI: run database migrations.

Usage:
    python scripts/db_migrate.py [--config config/system.json]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DB migrations.")
    parser.add_argument("--config", default="config/system.json")
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    import aiosqlite
    from openforexai.config.json_loader import load_json_config

    config = load_json_config(Path(args.config))
    db_cfg = config["database"]

    if db_cfg["backend"] != "sqlite":
        print(f"[migrate] Backend '{db_cfg['backend']}' migrations not yet automated.")
        return

    db_path = db_cfg["sqlite_path"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    migrations_dir = Path(__file__).parent.parent / "migrations"
    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        print(f"[migrate] No migration files found in {migrations_dir}")
        return

    async with aiosqlite.connect(db_path) as conn:
        for sql_file in sql_files:
            await conn.executescript(sql_file.read_text())
            print(f"[migrate] Applied {sql_file.name}")
        await conn.commit()

    print(f"[migrate] Migrations applied to {db_path}")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))

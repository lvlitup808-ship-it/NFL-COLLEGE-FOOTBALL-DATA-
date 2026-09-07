import asyncio
import hashlib
import json
import os
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "db" / "schema.sql"
MIGRATIONS_DIR = ROOT / "db" / "migrations"
MIGRATION_LOCK_ID = 734612209


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    conn = await asyncpg.connect(database_url, command_timeout=60)
    applied_now: list[str] = []
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_ID)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

        has_plays = await conn.fetchval("SELECT to_regclass('public.plays') IS NOT NULL")
        if not has_plays:
            async with conn.transaction():
                await conn.execute(SCHEMA_PATH.read_text())

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.name
            sql = path.read_text()
            digest = checksum(sql)
            existing = await conn.fetchrow(
                "SELECT checksum FROM schema_migrations WHERE version=$1", version
            )
            if existing:
                if existing["checksum"] != digest:
                    raise RuntimeError(
                        f"migration checksum mismatch for {version}; never edit an applied migration"
                    )
                continue

            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES ($1,$2)",
                    version,
                    digest,
                )
            applied_now.append(version)

        latest = await conn.fetchval("SELECT MAX(version) FROM schema_migrations")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "applied_now": applied_now,
                    "latest_migration": latest,
                },
                separators=(",", ":"),
            )
        )
    finally:
        try:
            await conn.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_ID)
        except Exception:
            pass
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

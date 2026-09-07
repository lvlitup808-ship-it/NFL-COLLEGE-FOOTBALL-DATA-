import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "movement_skillcorner_like.json"
KNOWN_FIELDS = {
    "player_id",
    "play_id",
    "max_speed_mph",
    "accel",
    "cod",
    "sep_yards",
    "getoff_ms",
    "source",
}


def load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError("movement fixture must be a JSON array")
    return payload


async def ingest_rows(conn: asyncpg.Connection, rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"ingested": 0, "skipped": 0, "errors": 0}
    for row in rows:
        play_raw = row.get("play_id")
        player_raw = row.get("player_id")
        source = row.get("source")
        if not play_raw or not player_raw or not source:
            counts["skipped"] += 1
            counts["errors"] += 1
            continue

        try:
            play_id = UUID(str(play_raw))
            player_id = UUID(str(player_raw))
            extra = {key: value for key, value in row.items() if key not in KNOWN_FIELDS}
            await conn.execute(
                """
                INSERT INTO movement_events (
                  play_id,player_id,source,max_speed_mph,accel,cod,sep_yards,getoff_ms,extra
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
                ON CONFLICT (play_id,player_id,source) DO UPDATE SET
                  max_speed_mph=EXCLUDED.max_speed_mph,
                  accel=EXCLUDED.accel,
                  cod=EXCLUDED.cod,
                  sep_yards=EXCLUDED.sep_yards,
                  getoff_ms=EXCLUDED.getoff_ms,
                  extra=EXCLUDED.extra
                """,
                play_id,
                player_id,
                str(source),
                row.get("max_speed_mph"),
                row.get("accel"),
                row.get("cod"),
                row.get("sep_yards"),
                row.get("getoff_ms"),
                json.dumps(extra, separators=(",", ":")),
            )
            counts["ingested"] += 1
        except Exception:
            counts["skipped"] += 1
            counts["errors"] += 1
    return counts


async def ingest(path: Path) -> dict[str, int]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    rows = load_rows(path)
    conn = await asyncpg.connect(database_url, command_timeout=20)
    try:
        table_ready = await conn.fetchval(
            "SELECT to_regclass('public.movement_events') IS NOT NULL"
        )
        if not table_ready:
            raise RuntimeError("database is not migrated; run `python scripts/migrate.py` first")
        counts = await ingest_rows(conn, rows)
        stored = await conn.fetchval(
            """
            SELECT COUNT(*)::int
            FROM movement_events
            WHERE source=ANY($1::text[])
            """,
            sorted({str(row["source"]) for row in rows if row.get("source")}),
        )
        return {**counts, "stored": int(stored or 0)}
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest vendor-shaped player movement JSON into FIELDMIND"
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_FIXTURE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(ingest(args.file))
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.nflverse import SOURCE, canonicalize_row, csv_rows, source_url

NAMESPACE = UUID("d6a813a6-0aa5-4f9a-9ad6-7fe123e178d4")
PROGRAM_ID = uuid5(NAMESPACE, "nflverse:program:nfl")


def stable_id(kind: str, external_id: str) -> UUID:
    return uuid5(NAMESPACE, f"{SOURCE}:{kind}:{external_id}")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


async def ensure_program(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO programs (id,name,level,external_source,external_id)
        VALUES ($1,'NFL','nfl',$2,'NFL')
        ON CONFLICT (id) DO UPDATE SET
            name=EXCLUDED.name,
            level=EXCLUDED.level,
            external_source=EXCLUDED.external_source,
            external_id=EXCLUDED.external_id
        """,
        PROGRAM_ID,
        SOURCE,
    )


async def flush_batch(
    conn: asyncpg.Connection,
    batch: list[dict[str, Any]],
    season: int,
) -> tuple[int, int]:
    if not batch:
        return 0, 0

    team_codes: set[str] = set()
    for row in batch:
        for key in ("home_team", "away_team", "offense_team", "defense_team"):
            value = row.get(key)
            if isinstance(value, str) and value:
                team_codes.add(value)

    team_ids = {code: stable_id("team", f"{season}:{code}") for code in team_codes}
    game_rows: dict[str, dict[str, Any]] = {}
    for row in batch:
        game_rows.setdefault(str(row["game_external_id"]), row)

    async with conn.transaction():
        await ensure_program(conn)
        await conn.executemany(
            """
            INSERT INTO teams (id,program_id,name,season,external_source,external_id)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name,
                season=EXCLUDED.season,
                external_source=EXCLUDED.external_source,
                external_id=EXCLUDED.external_id
            """,
            [
                (team_ids[code], PROGRAM_ID, code, season, SOURCE, code)
                for code in sorted(team_codes)
            ],
        )

        await conn.executemany(
            """
            INSERT INTO games (
                id,season,week,game_date,home_team_id,away_team_id,
                external_source,external_id,season_type
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (id) DO UPDATE SET
                week=EXCLUDED.week,
                game_date=EXCLUDED.game_date,
                home_team_id=EXCLUDED.home_team_id,
                away_team_id=EXCLUDED.away_team_id,
                external_source=EXCLUDED.external_source,
                external_id=EXCLUDED.external_id,
                season_type=EXCLUDED.season_type
            """,
            [
                (
                    stable_id("game", game_external_id),
                    season,
                    row.get("week"),
                    parse_date(row.get("game_date")),
                    team_ids.get(str(row.get("home_team"))) if row.get("home_team") else None,
                    team_ids.get(str(row.get("away_team"))) if row.get("away_team") else None,
                    SOURCE,
                    game_external_id,
                    row.get("season_type"),
                )
                for game_external_id, row in game_rows.items()
            ],
        )

        external_ids = [str(row["play_external_id"]) for row in batch]
        existing = await conn.fetch(
            """
            SELECT external_id FROM plays
            WHERE external_source=$1 AND external_id = ANY($2::text[])
            """,
            SOURCE,
            external_ids,
        )
        existing_ids = {record["external_id"] for record in existing}

        await conn.executemany(
            """
            INSERT INTO plays (
                id,game_id,play_sequence,quarter,clock,down,distance,yard_line,
                distance_bucket,field_zone,score_diff,offense_team_id,defense_team_id,
                offense_team_name,defense_team_name,personnel_offense,formation,motion,
                play_family,concept,coverage,pressure,result_yards,epa,success,explosive,
                turnover,qb_player_id,cognition_events,tags,external_source,external_id
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
                $19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29::jsonb,$30::text[],$31,$32
            )
            ON CONFLICT (id) DO UPDATE SET
                game_id=EXCLUDED.game_id,
                play_sequence=EXCLUDED.play_sequence,
                quarter=EXCLUDED.quarter,
                clock=EXCLUDED.clock,
                down=EXCLUDED.down,
                distance=EXCLUDED.distance,
                yard_line=EXCLUDED.yard_line,
                distance_bucket=EXCLUDED.distance_bucket,
                field_zone=EXCLUDED.field_zone,
                score_diff=EXCLUDED.score_diff,
                offense_team_id=EXCLUDED.offense_team_id,
                defense_team_id=EXCLUDED.defense_team_id,
                offense_team_name=EXCLUDED.offense_team_name,
                defense_team_name=EXCLUDED.defense_team_name,
                personnel_offense=EXCLUDED.personnel_offense,
                formation=EXCLUDED.formation,
                motion=EXCLUDED.motion,
                play_family=EXCLUDED.play_family,
                concept=EXCLUDED.concept,
                coverage=EXCLUDED.coverage,
                pressure=EXCLUDED.pressure,
                result_yards=EXCLUDED.result_yards,
                epa=EXCLUDED.epa,
                success=EXCLUDED.success,
                explosive=EXCLUDED.explosive,
                turnover=EXCLUDED.turnover,
                tags=EXCLUDED.tags,
                external_source=EXCLUDED.external_source,
                external_id=EXCLUDED.external_id
            """,
            [
                (
                    stable_id("play", str(row["play_external_id"])),
                    stable_id("game", str(row["game_external_id"])),
                    row["play_sequence"],
                    row["quarter"],
                    row["clock"],
                    row["down"],
                    row["distance"],
                    row["yard_line"],
                    row["distance_bucket"],
                    row["field_zone"],
                    row["score_diff"],
                    team_ids.get(str(row["offense_team"])),
                    team_ids.get(str(row["defense_team"])),
                    row["offense_team"],
                    row["defense_team"],
                    row["personnel_offense"],
                    row["formation"],
                    row["motion"],
                    row["play_family"],
                    row["concept"],
                    row["coverage"],
                    row["pressure"],
                    row["result_yards"],
                    row["epa"],
                    row["success"],
                    row["explosive"],
                    row["turnover"],
                    None,
                    "{}",
                    row["tags"],
                    SOURCE,
                    row["play_external_id"],
                )
                for row in batch
            ],
        )

    updated = sum(1 for external_id in external_ids if external_id in existing_ids)
    inserted = len(batch) - updated
    return inserted, updated


async def ingest(season: int, uri: str, batch_size: int, max_rows: int | None) -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    conn = await asyncpg.connect(database_url, command_timeout=30)
    run_id: UUID | None = None
    counts = {"rows_seen": 0, "rows_inserted": 0, "rows_updated": 0, "rows_skipped": 0, "error_count": 0}
    try:
        has_ingest_schema = await conn.fetchval("SELECT to_regclass('public.ingest_runs') IS NOT NULL")
        if not has_ingest_schema:
            raise RuntimeError("database is not migrated; run `python scripts/migrate.py` first")

        run_id = await conn.fetchval(
            """
            INSERT INTO ingest_runs (source,season,source_uri,status,metadata)
            VALUES ($1,$2,$3,'running',$4::jsonb)
            RETURNING id
            """,
            SOURCE,
            season,
            uri,
            json.dumps({"batch_size": batch_size, "max_rows": max_rows}),
        )

        batch: list[dict[str, Any]] = []
        with csv_rows(uri) as reader:
            for source_row in reader:
                if max_rows is not None and counts["rows_seen"] >= max_rows:
                    break
                counts["rows_seen"] += 1
                try:
                    normalized = canonicalize_row(source_row, season)
                except Exception:
                    counts["error_count"] += 1
                    counts["rows_skipped"] += 1
                    continue
                if normalized is None:
                    counts["rows_skipped"] += 1
                    continue
                batch.append(normalized)
                if len(batch) >= batch_size:
                    inserted, updated = await flush_batch(conn, batch, season)
                    counts["rows_inserted"] += inserted
                    counts["rows_updated"] += updated
                    batch.clear()

        if batch:
            inserted, updated = await flush_batch(conn, batch, season)
            counts["rows_inserted"] += inserted
            counts["rows_updated"] += updated

        await conn.execute(
            """
            UPDATE ingest_runs SET
                status='succeeded', rows_seen=$2, rows_inserted=$3, rows_updated=$4,
                rows_skipped=$5, error_count=$6, finished_at=now()
            WHERE id=$1
            """,
            run_id,
            counts["rows_seen"],
            counts["rows_inserted"],
            counts["rows_updated"],
            counts["rows_skipped"],
            counts["error_count"],
        )
        return {"status": "ok", "run_id": str(run_id), "source": SOURCE, "season": season, **counts}
    except Exception:
        if run_id is not None:
            await conn.execute(
                """
                UPDATE ingest_runs SET status='failed', rows_seen=$2, rows_inserted=$3,
                    rows_updated=$4, rows_skipped=$5, error_count=$6, finished_at=now()
                WHERE id=$1
                """,
                run_id,
                counts["rows_seen"],
                counts["rows_inserted"],
                counts["rows_updated"],
                counts["rows_skipped"],
                counts["error_count"] + 1,
            )
        raise
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream nflverse NFL play-by-play into FIELDMIND")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--url", dest="uri", help="Override nflverse URL with a URL or local CSV path")
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--max-rows", type=int)
    args = parser.parse_args()
    if args.batch_size < 25 or args.batch_size > 2000:
        parser.error("--batch-size must be between 25 and 2000")
    if args.max_rows is not None and args.max_rows < 1:
        parser.error("--max-rows must be positive")
    return args


def main() -> None:
    args = parse_args()
    uri = args.uri or source_url(args.season)
    result = asyncio.run(ingest(args.season, uri, args.batch_size, args.max_rows))
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()

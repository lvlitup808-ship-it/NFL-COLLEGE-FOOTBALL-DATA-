import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.cfbd import SOURCE, canonicalize_play, fetch_week

NAMESPACE = UUID("56d823df-a9e9-4c4f-9c65-67f736963297")
PROGRAM_ID = uuid5(NAMESPACE, "cfbd:program:ncaa")


def stable_id(kind: str, external_id: str) -> UUID:
    return uuid5(NAMESPACE, f"{SOURCE}:{kind}:{external_id}")


async def ensure_program(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO programs (id,name,level,external_source,external_id)
        VALUES ($1,'NCAA Football','college',$2,'NCAA')
        ON CONFLICT (id) DO UPDATE SET
          name=EXCLUDED.name,level=EXCLUDED.level,
          external_source=EXCLUDED.external_source,external_id=EXCLUDED.external_id
        """,
        PROGRAM_ID,
        SOURCE,
    )


async def flush_batch(
    conn: asyncpg.Connection,
    rows: list[dict[str, Any]],
    season: int,
    week: int,
    season_type: str,
) -> tuple[int, int]:
    if not rows:
        return 0, 0

    team_names: set[str] = set()
    for row in rows:
        for key in ("home_team", "away_team", "offense_team", "defense_team"):
            value = row.get(key)
            if isinstance(value, str) and value:
                team_names.add(value)
    team_ids = {name: stable_id("team", f"{season}:{name}") for name in team_names}

    games: dict[str, dict[str, Any]] = {}
    for row in rows:
        games.setdefault(str(row["game_external_id"]), row)

    external_ids = [str(row["play_external_id"]) for row in rows]
    existing = await conn.fetch(
        """
        SELECT external_id FROM plays
        WHERE external_source=$1 AND external_id=ANY($2::text[])
        """,
        SOURCE,
        external_ids,
    )
    existing_ids = {record["external_id"] for record in existing}

    async with conn.transaction():
        await ensure_program(conn)
        if team_names:
            await conn.executemany(
                """
                INSERT INTO teams (id,program_id,name,season,external_source,external_id)
                VALUES ($1,$2,$3,$4,$5,$6)
                ON CONFLICT (id) DO UPDATE SET
                  name=EXCLUDED.name,season=EXCLUDED.season,
                  external_source=EXCLUDED.external_source,external_id=EXCLUDED.external_id
                """,
                [
                    (team_ids[name], PROGRAM_ID, name, season, SOURCE, name)
                    for name in sorted(team_names)
                ],
            )

        await conn.executemany(
            """
            INSERT INTO games (
              id,season,week,home_team_id,away_team_id,
              external_source,external_id,season_type
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (id) DO UPDATE SET
              week=EXCLUDED.week,home_team_id=EXCLUDED.home_team_id,
              away_team_id=EXCLUDED.away_team_id,external_source=EXCLUDED.external_source,
              external_id=EXCLUDED.external_id,season_type=EXCLUDED.season_type
            """,
            [
                (
                    stable_id("game", game_id),
                    season,
                    week,
                    team_ids.get(str(row.get("home_team"))) if row.get("home_team") else None,
                    team_ids.get(str(row.get("away_team"))) if row.get("away_team") else None,
                    SOURCE,
                    game_id,
                    season_type,
                )
                for game_id, row in games.items()
            ],
        )

        await conn.executemany(
            """
            INSERT INTO plays (
              id,game_id,play_sequence,quarter,clock,down,distance,yard_line,
              distance_bucket,field_zone,score_diff,offense_team_id,defense_team_id,
              offense_team_name,defense_team_name,personnel_offense,formation,motion,
              play_family,concept,coverage,pressure,result_yards,epa,ppa,success,explosive,
              turnover,qb_player_id,cognition_events,tags,external_source,external_id,
              source_play_type,play_text
            ) VALUES (
              $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
              $19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30::jsonb,$31::text[],$32,$33,$34,$35
            )
            ON CONFLICT (id) DO UPDATE SET
              game_id=EXCLUDED.game_id,play_sequence=EXCLUDED.play_sequence,
              quarter=EXCLUDED.quarter,clock=EXCLUDED.clock,down=EXCLUDED.down,
              distance=EXCLUDED.distance,yard_line=EXCLUDED.yard_line,
              distance_bucket=EXCLUDED.distance_bucket,field_zone=EXCLUDED.field_zone,
              score_diff=EXCLUDED.score_diff,offense_team_id=EXCLUDED.offense_team_id,
              defense_team_id=EXCLUDED.defense_team_id,offense_team_name=EXCLUDED.offense_team_name,
              defense_team_name=EXCLUDED.defense_team_name,personnel_offense=EXCLUDED.personnel_offense,
              formation=EXCLUDED.formation,motion=EXCLUDED.motion,play_family=EXCLUDED.play_family,
              concept=EXCLUDED.concept,coverage=EXCLUDED.coverage,pressure=EXCLUDED.pressure,
              result_yards=EXCLUDED.result_yards,epa=EXCLUDED.epa,ppa=EXCLUDED.ppa,
              success=EXCLUDED.success,explosive=EXCLUDED.explosive,turnover=EXCLUDED.turnover,
              tags=EXCLUDED.tags,external_source=EXCLUDED.external_source,
              external_id=EXCLUDED.external_id,source_play_type=EXCLUDED.source_play_type,
              play_text=EXCLUDED.play_text
            """,
            [
                (
                    stable_id("play", str(row["play_external_id"])),
                    stable_id("game", str(row["game_external_id"])),
                    row["play_sequence"],row["quarter"],row["clock"],row["down"],
                    row["distance"],row["yard_line"],row["distance_bucket"],row["field_zone"],
                    row["score_diff"],team_ids.get(str(row["offense_team"])),
                    team_ids.get(str(row["defense_team"])),row["offense_team"],row["defense_team"],
                    row["personnel_offense"],row["formation"],row["motion"],row["play_family"],
                    row["concept"],row["coverage"],row["pressure"],row["result_yards"],
                    row["epa"],row["ppa"],row["success"],row["explosive"],row["turnover"],
                    None,"{}",row["tags"],SOURCE,row["play_external_id"],
                    row["source_play_type"],row["play_text"],
                )
                for row in rows
            ],
        )

    updated = sum(1 for external_id in external_ids if external_id in existing_ids)
    return len(rows) - updated, updated


def load_fixture(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, list):
        raise ValueError("CFBD fixture must be a JSON array")
    return payload


async def ingest(
    season: int,
    start_week: int,
    end_week: int,
    season_type: str,
    fixture: str | None,
    batch_size: int,
) -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    api_key = os.getenv("CFBD_API_KEY", "")
    if fixture and start_week != end_week:
        raise ValueError("fixture mode supports exactly one week")
    if not fixture and not api_key:
        raise SystemExit("CFBD_API_KEY is required for live CFBD ingestion")

    conn = await asyncpg.connect(database_url, command_timeout=30)
    run_id: UUID | None = None
    counts = {"rows_seen":0,"rows_inserted":0,"rows_updated":0,"rows_skipped":0,"error_count":0}
    try:
        migrated = await conn.fetchval("SELECT to_regclass('public.ingest_runs') IS NOT NULL")
        ppa_ready = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='plays' AND column_name='ppa')"
        )
        if not migrated or not ppa_ready:
            raise RuntimeError("database is not migrated; run `python scripts/migrate.py` first")

        source_uri = fixture or f"https://api.collegefootballdata.com/plays?year={season}&weeks={start_week}-{end_week}"
        run_id = await conn.fetchval(
            """
            INSERT INTO ingest_runs (source,season,source_uri,status,metadata)
            VALUES ($1,$2,$3,'running',$4::jsonb) RETURNING id
            """,
            SOURCE,season,source_uri,
            json.dumps({"start_week":start_week,"end_week":end_week,"season_type":season_type,"batch_size":batch_size}),
        )

        for week in range(start_week, end_week + 1):
            source_rows = load_fixture(fixture) if fixture else fetch_week(api_key, season, week, season_type)
            normalized: list[dict[str, Any]] = []
            for index, source_row in enumerate(source_rows, start=1):
                counts["rows_seen"] += 1
                try:
                    play = canonicalize_play(source_row, season, week, index)
                except Exception:
                    counts["rows_skipped"] += 1
                    counts["error_count"] += 1
                    continue
                if play is None:
                    counts["rows_skipped"] += 1
                    continue
                normalized.append(play)
                if len(normalized) >= batch_size:
                    inserted, updated = await flush_batch(conn, normalized, season, week, season_type)
                    counts["rows_inserted"] += inserted
                    counts["rows_updated"] += updated
                    normalized.clear()
            if normalized:
                inserted, updated = await flush_batch(conn, normalized, season, week, season_type)
                counts["rows_inserted"] += inserted
                counts["rows_updated"] += updated

        await conn.execute(
            """
            UPDATE ingest_runs SET status='succeeded',rows_seen=$2,rows_inserted=$3,
              rows_updated=$4,rows_skipped=$5,error_count=$6,finished_at=now()
            WHERE id=$1
            """,
            run_id,counts["rows_seen"],counts["rows_inserted"],counts["rows_updated"],
            counts["rows_skipped"],counts["error_count"],
        )
        return {"status":"ok","run_id":str(run_id),"source":SOURCE,"season":season,
                "weeks":[start_week,end_week],**counts}
    except Exception:
        if run_id is not None:
            await conn.execute(
                """
                UPDATE ingest_runs SET status='failed',rows_seen=$2,rows_inserted=$3,
                  rows_updated=$4,rows_skipped=$5,error_count=$6,finished_at=now()
                WHERE id=$1
                """,
                run_id,counts["rows_seen"],counts["rows_inserted"],counts["rows_updated"],
                counts["rows_skipped"],counts["error_count"]+1,
            )
        raise
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest CFBD college football play-by-play into FIELDMIND")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int)
    parser.add_argument("--start-week", type=int)
    parser.add_argument("--end-week", type=int)
    parser.add_argument("--season-type", choices=["regular","postseason","both"], default="regular")
    parser.add_argument("--fixture")
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    if args.week is not None:
        args.start_week = args.end_week = args.week
    elif args.start_week is None:
        parser.error("provide --week or --start-week")
    elif args.end_week is None:
        args.end_week = args.start_week
    if args.start_week < 0 or args.end_week < args.start_week:
        parser.error("invalid week range")
    if not 25 <= args.batch_size <= 2000:
        parser.error("--batch-size must be between 25 and 2000")
    return args


def main() -> None:
    args = parse_args()
    result = asyncio.run(
        ingest(args.season,args.start_week,args.end_week,args.season_type,args.fixture,args.batch_size)
    )
    print(json.dumps(result,separators=(",",":")))


if __name__ == "__main__":
    main()

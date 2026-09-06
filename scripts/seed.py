import asyncio
import json
import os
from datetime import date
from pathlib import Path
from uuid import UUID

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "db" / "schema.sql"
SEED_PATH = ROOT / "data" / "seed_plays.json"


def as_uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


async def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    seed = json.loads(SEED_PATH.read_text())
    schema = SCHEMA_PATH.read_text()
    conn = await asyncpg.connect(database_url, command_timeout=20)
    try:
        async with conn.transaction():
            await conn.execute(schema)

            for row in seed["programs"]:
                await conn.execute(
                    """
                    INSERT INTO programs (id,name,level)
                    VALUES ($1,$2,$3)
                    ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, level=EXCLUDED.level
                    """,
                    as_uuid(row["id"]), row["name"], row["level"],
                )

            for row in seed["teams"]:
                await conn.execute(
                    """
                    INSERT INTO teams (id,program_id,name,season)
                    VALUES ($1,$2,$3,$4)
                    ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, season=EXCLUDED.season
                    """,
                    as_uuid(row["id"]), as_uuid(row["program_id"]), row["name"], row["season"],
                )

            for row in seed["players"]:
                await conn.execute(
                    """
                    INSERT INTO players (id,team_id,name,position,class_year,jersey)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    ON CONFLICT (id) DO UPDATE SET
                        team_id=EXCLUDED.team_id,
                        name=EXCLUDED.name,
                        position=EXCLUDED.position,
                        class_year=EXCLUDED.class_year,
                        jersey=EXCLUDED.jersey
                    """,
                    as_uuid(row["id"]), as_uuid(row["team_id"]), row["name"], row["position"],
                    row.get("class_year"), row.get("jersey"),
                )

            for row in seed["games"]:
                await conn.execute(
                    """
                    INSERT INTO games (id,season,week,game_date,home_team_id,away_team_id,venue)
                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                    ON CONFLICT (id) DO UPDATE SET
                        season=EXCLUDED.season,
                        week=EXCLUDED.week,
                        game_date=EXCLUDED.game_date,
                        home_team_id=EXCLUDED.home_team_id,
                        away_team_id=EXCLUDED.away_team_id,
                        venue=EXCLUDED.venue
                    """,
                    as_uuid(row["id"]), row["season"], row.get("week"),
                    date.fromisoformat(row["game_date"]) if row.get("game_date") else None,
                    as_uuid(row.get("home_team_id")), as_uuid(row.get("away_team_id")), row.get("venue"),
                )

            for row in seed["plays"]:
                await conn.execute(
                    """
                    INSERT INTO plays (
                        id,game_id,play_sequence,quarter,clock,down,distance,yard_line,
                        distance_bucket,field_zone,score_diff,offense_team_id,defense_team_id,
                        offense_team_name,defense_team_name,personnel_offense,formation,motion,
                        play_family,concept,coverage,pressure,result_yards,epa,success,explosive,
                        turnover,qb_player_id,cognition_events,tags
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
                        $19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29::jsonb,$30::text[]
                    )
                    ON CONFLICT (id) DO UPDATE SET
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
                        qb_player_id=EXCLUDED.qb_player_id,
                        cognition_events=EXCLUDED.cognition_events,
                        tags=EXCLUDED.tags
                    """,
                    as_uuid(row["id"]),
                    as_uuid(row["game_id"]),
                    row["play_sequence"],
                    row["quarter"],
                    row["clock"],
                    row["down"],
                    row["distance"],
                    row["yard_line"],
                    row["distance_bucket"],
                    row["field_zone"],
                    row.get("score_diff", 0),
                    as_uuid(row.get("offense_team_id")),
                    as_uuid(row.get("defense_team_id")),
                    row["offense_team_name"],
                    row["defense_team_name"],
                    row["personnel_offense"],
                    row["formation"],
                    row.get("motion"),
                    row["play_family"],
                    row.get("concept"),
                    row.get("coverage"),
                    row.get("pressure"),
                    row.get("result_yards", 0),
                    row.get("epa"),
                    row.get("success", False),
                    row.get("explosive", False),
                    row.get("turnover", False),
                    as_uuid(row.get("qb_player_id")),
                    json.dumps(row.get("cognition_events", {})),
                    row.get("tags", []),
                )

            for row in seed["cognition_trait_scores"]:
                player_id = as_uuid(row["player_id"])
                await conn.execute(
                    "DELETE FROM cognition_trait_scores WHERE player_id=$1 AND trait=$2",
                    player_id, row["trait"],
                )
                await conn.execute(
                    """
                    INSERT INTO cognition_trait_scores
                    (player_id,position,trait,score,sample_n,evidence_count,confidence,evidence)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb)
                    """,
                    player_id, row["position"], row["trait"], row["score"], row["sample_n"],
                    row["evidence_count"], row["confidence"], json.dumps(row["evidence"]),
                )

            await conn.execute("DELETE FROM call_rules WHERE opponent_name='Metro State Panthers'")
            for row in seed["call_rules"]:
                await conn.execute(
                    """
                    INSERT INTO call_rules (opponent_name,rule_type,situation,call_name,reason,sample_n,priority)
                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                    """,
                    row["opponent_name"], row["rule_type"], row["situation"], row["call_name"],
                    row["reason"], row["sample_n"], row["priority"],
                )

        play_count = await conn.fetchval("SELECT COUNT(*) FROM plays")
        print(json.dumps({"status": "ok", "plays_in_db": play_count}))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

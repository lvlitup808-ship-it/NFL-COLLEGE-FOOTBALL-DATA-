import asyncio
import json
import os
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "db" / "schema.sql"
SEED_PATH = ROOT / "data" / "seed_plays.json"


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
                    row["id"], row["name"], row["level"],
                )

            for row in seed["teams"]:
                await conn.execute(
                    """
                    INSERT INTO teams (id,program_id,name,season)
                    VALUES ($1,$2,$3,$4)
                    ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, season=EXCLUDED.season
                    """,
                    row["id"], row["program_id"], row["name"], row["season"],
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
                    row["id"], row["team_id"], row["name"], row["position"], row.get("class_year"), row.get("jersey"),
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
                    row["id"], row["season"], row.get("week"), row.get("game_date"),
                    row.get("home_team_id"), row.get("away_team_id"), row.get("venue"),
                )

            play_columns = [
                "id","game_id","play_sequence","quarter","clock","down","distance","yard_line",
                "distance_bucket","field_zone","score_diff","offense_team_id","defense_team_id",
                "offense_team_name","defense_team_name","personnel_offense","formation","motion",
                "play_family","concept","coverage","pressure","result_yards","epa","success",
                "explosive","turnover","qb_player_id"
            ]
            for row in seed["plays"]:
                values = [row.get(c) for c in play_columns]
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
                        cognition_events=EXCLUDED.cognition_events,
                        tags=EXCLUDED.tags
                    """,
                    *values,
                    json.dumps(row.get("cognition_events", {})),
                    row.get("tags", []),
                )

            for row in seed["cognition_trait_scores"]:
                await conn.execute(
                    "DELETE FROM cognition_trait_scores WHERE player_id=$1 AND trait=$2",
                    row["player_id"], row["trait"],
                )
                await conn.execute(
                    """
                    INSERT INTO cognition_trait_scores
                    (player_id,position,trait,score,sample_n,evidence_count,confidence,evidence)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb)
                    """,
                    row["player_id"], row["position"], row["trait"], row["score"],
                    row["sample_n"], row["evidence_count"], row["confidence"], json.dumps(row["evidence"]),
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

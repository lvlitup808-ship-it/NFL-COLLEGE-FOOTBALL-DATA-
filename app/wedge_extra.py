import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.wedge import (
    AuthContext,
    owned_week_plan,
    require_auth,
    require_coach,
    require_pool,
)

router = APIRouter(prefix="/api/v1", tags=["FIELDMIND Pilot"])


class RosterPlayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    position: str = Field(min_length=1, max_length=20)
    class_year: str | None = Field(default=None, max_length=40)
    jersey: int | None = Field(default=None, ge=0, le=99)


@router.get("/week-plans/{week_plan_id}/call-rules")
async def list_call_rules(
    week_plan_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    pool = require_pool(request)
    async with pool.acquire() as conn:
        await owned_week_plan(conn, week_plan_id, ctx)
        rows = await conn.fetch(
            """
            SELECT id,rule_type,situation,call_name,reason,sample_n,priority,confidence,
                   evidence_play_ids,status,created_at,updated_at
            FROM call_rules
            WHERE program_id=$1 AND week_plan_id=$2
            ORDER BY
                CASE status WHEN 'candidate' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                priority DESC,created_at
            """,
            ctx.program_id,
            week_plan_id,
        )
    return {"week_plan_id": week_plan_id, "rules": [dict(row) for row in rows]}


@router.post("/week-plans/{week_plan_id}/roster-players", status_code=201)
async def add_roster_player(
    week_plan_id: uuid.UUID,
    body: RosterPlayerCreate,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_coach(ctx)
    pool = require_pool(request)
    player_id = uuid.uuid4()
    async with pool.acquire() as conn:
        plan = await owned_week_plan(conn, week_plan_id, ctx)
        if plan["status"] == "frozen":
            raise HTTPException(status_code=409, detail="week_plan_frozen")
        async with conn.transaction():
            team_id = await conn.fetchval(
                """
                SELECT id FROM teams
                WHERE program_id=$1 AND name=$2 AND season=$3
                """,
                ctx.program_id,
                plan["team_name"],
                plan["season"],
            )
            if team_id is None:
                team_id = uuid.uuid4()
                await conn.execute(
                    """
                    INSERT INTO teams (
                        id,program_id,name,season,external_source,external_id
                    ) VALUES ($1,$2,$3,$4,'fieldmind_customer',$5)
                    """,
                    team_id,
                    ctx.program_id,
                    plan["team_name"],
                    plan["season"],
                    f"{ctx.program_id}:{plan['season']}:{plan['team_name']}",
                )
            await conn.execute(
                "UPDATE week_plans SET team_id=$1 WHERE id=$2 AND program_id=$3",
                team_id,
                week_plan_id,
                ctx.program_id,
            )
            existing = await conn.fetchrow(
                """
                SELECT id,name,position,class_year,jersey
                FROM players
                WHERE team_id=$1 AND lower(name)=lower($2)
                  AND ($3::int IS NULL OR jersey=$3)
                ORDER BY created_at
                LIMIT 1
                """,
                team_id,
                body.name,
                body.jersey,
            )
            if existing:
                return {"created": False, "player": dict(existing), "team_id": team_id}
            player = await conn.fetchrow(
                """
                INSERT INTO players (id,team_id,name,position,class_year,jersey)
                VALUES ($1,$2,$3,$4,$5,$6)
                RETURNING id,name,position,class_year,jersey
                """,
                player_id,
                team_id,
                body.name,
                body.position.upper(),
                body.class_year,
                body.jersey,
            )
    return {"created": True, "player": dict(player), "team_id": team_id}


@router.get("/week-plans/{week_plan_id}/roster-players")
async def list_roster_players(
    week_plan_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    pool = require_pool(request)
    async with pool.acquire() as conn:
        plan = await owned_week_plan(conn, week_plan_id, ctx)
        if plan["team_id"] is None:
            return {"week_plan_id": week_plan_id, "players": []}
        owned = await conn.fetchval(
            "SELECT 1 FROM teams WHERE id=$1 AND program_id=$2",
            plan["team_id"],
            ctx.program_id,
        )
        if not owned:
            return {"week_plan_id": week_plan_id, "players": []}
        rows = await conn.fetch(
            """
            SELECT id,name,position,class_year,jersey
            FROM players
            WHERE team_id=$1
            ORDER BY position,jersey NULLS LAST,name
            """,
            plan["team_id"],
        )
    return {"week_plan_id": week_plan_id, "players": [dict(row) for row in rows]}

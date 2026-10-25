"""Program-scoped persistence for frozen synthetic scenarios."""
from __future__ import annotations
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.wedge import AuthContext, require_auth, require_pool, require_write

router = APIRouter(prefix="/api/v1/scenarios", tags=["Synthetic scenarios"])
class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)

class Player(Point):
    id: str = Field(min_length=2, max_length=4)
    name: str = Field(min_length=1, max_length=80)
    routes: list[Point] = Field(max_length=200)

class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["fieldmind-synthetic-v1"]
    synthetic: Literal[True]
    name: str = Field(min_length=1, max_length=120)
    players: list[Player] = Field(min_length=14, max_length=14)

    @model_validator(mode="after")
    def validate_players(self):
        if [p.id for p in self.players] != [f"p{i}" for i in range(1, 15)]:
            raise ValueError("expected ordered p1–p14")
        return self

class SaveScenario(BaseModel):
    scenario: Scenario

@router.post("", status_code=201)
async def save(body: SaveScenario, request: Request, ctx: AuthContext = Depends(require_auth)):
    require_write(ctx)
    pool = require_pool(request)
    identifier = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO synthetic_scenarios (id,program_id,created_by,body)
               VALUES ($1,$2,$3,$4::jsonb)""",
            identifier, ctx.program_id, ctx.user_id, body.scenario.model_dump_json()
        )
    return {"id": identifier, "version": body.scenario.version}

@router.get("")
async def list_scenarios(request: Request, ctx: AuthContext = Depends(require_auth)):
    pool = require_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id,body->>'name' AS name,created_at
               FROM synthetic_scenarios WHERE program_id=$1
               ORDER BY created_at DESC LIMIT 100""", ctx.program_id
        )
    return {"scenarios": [dict(row) for row in rows]}

@router.get("/{scenario_id}")
async def load(scenario_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(require_auth)):
    pool = require_pool(request)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT body FROM synthetic_scenarios WHERE id=$1 AND program_id=$2",
            scenario_id, ctx.program_id
        )
    if row is None:
        raise HTTPException(status_code=404, detail="scenario_not_found")
    return {"id": scenario_id, "scenario": Scenario.model_validate_json(row["body"]) if isinstance(row["body"], str) else Scenario.model_validate(row["body"])}

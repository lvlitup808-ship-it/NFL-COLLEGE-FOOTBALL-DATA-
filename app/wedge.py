import hashlib
import json
import uuid
from collections import defaultdict
from datetime import date
from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, HttpUrl

router = APIRouter(prefix="/api/v1", tags=["FIELDMIND Pilot"])

PLAY_FAMILY = {
    "UNKNOWN", "INSIDE_ZONE", "OUTSIDE_ZONE", "DUO", "POWER", "COUNTER", "ISO",
    "DRAW", "MESH", "STICK", "SPACING", "FLOOD", "FOUR_VERTICALS", "SCREEN",
}
FORMATION = {"UNKNOWN", "2X2", "3X1", "BUNCH", "EMPTY", "NUB", "CONDENSED"}
MOTION = {"UNKNOWN", "NONE", "JET", "ORBIT", "RETURN", "SHIFT"}
COVERAGE = {"UNKNOWN", "COVER_0", "COVER_1", "COVER_2", "COVER_3", "QUARTERS", "COVER_6"}
PERSONNEL = {"UNKNOWN", "10", "11", "12", "20", "21"}
VOCAB = {
    "play_family": PLAY_FAMILY,
    "formation": FORMATION,
    "motion": MOTION,
    "coverage_family": COVERAGE,
    "personnel": PERSONNEL,
}
TAG_FIELDS = tuple(VOCAB.keys())
WRITE_ROLES = {"owner", "coach", "ga"}
COACH_ROLES = {"owner", "coach"}


def require_pool(request: Request) -> asyncpg.Pool:
    pool = request.app.state.db.pool
    if pool is None:
        raise HTTPException(status_code=503, detail="database_not_ready")
    return pool


class AuthContext(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None = None
    program_id: uuid.UUID
    program_name: str
    role: Literal["owner", "coach", "ga", "viewer"]


async def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    x_program_id: str | None = Header(default=None, alias="X-Program-ID"),
) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="bearer_token_required")
    raw = authorization[7:].strip()
    if len(raw) < 32:
        raise HTTPException(status_code=401, detail="invalid_token")
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    pool = require_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT u.id AS user_id, u.email, u.display_name,
                   pm.program_id, p.name AS program_name, pm.role, t.id AS token_id
            FROM auth_tokens t
            JOIN users u ON u.id=t.user_id
            JOIN program_memberships pm ON pm.user_id=u.id
            JOIN programs p ON p.id=pm.program_id
            WHERE t.token_hash=$1
              AND u.active
              AND t.revoked_at IS NULL
              AND t.expires_at > now()
            ORDER BY pm.program_id
            """,
            token_hash,
        )
        if not rows:
            raise HTTPException(status_code=401, detail="invalid_or_expired_token")
        selected = None
        if x_program_id:
            try:
                requested = uuid.UUID(x_program_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid_x_program_id") from exc
            selected = next((r for r in rows if r["program_id"] == requested), None)
            if selected is None:
                raise HTTPException(status_code=403, detail="not_a_program_member")
        elif len(rows) == 1:
            selected = rows[0]
        else:
            raise HTTPException(status_code=409, detail="x_program_id_required_for_multi_program_user")
        await conn.execute("UPDATE auth_tokens SET last_used_at=now() WHERE id=$1", selected["token_id"])
    return AuthContext(**{k: selected[k] for k in ("user_id", "email", "display_name", "program_id", "program_name", "role")})


def require_write(ctx: AuthContext) -> None:
    if ctx.role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="write_role_required")


def require_coach(ctx: AuthContext) -> None:
    if ctx.role not in COACH_ROLES:
        raise HTTPException(status_code=403, detail="coach_role_required")


def validate_tag(field: str, value: str | None) -> None:
    if value is None:
        return
    if field not in VOCAB or value not in VOCAB[field]:
        raise HTTPException(status_code=422, detail=f"invalid_{field}:{value}")


class TagBody(BaseModel):
    play_family: str | None = None
    formation: str | None = None
    motion: str | None = None
    coverage_family: str | None = None
    personnel: str | None = None


class PlayLinkBody(BaseModel):
    provider: Literal["hudl", "other"] = "hudl"
    url: HttpUrl


class WeekPlanCreate(BaseModel):
    team_id: uuid.UUID | None = None
    team_name: str = Field(min_length=1, max_length=120)
    season: int = Field(ge=2000, le=2100)
    week: int = Field(ge=0, le=25)
    opponent_name: str = Field(min_length=1, max_length=120)
    side: Literal["offense", "defense"]


class CallRuleCreate(BaseModel):
    rule_type: Literal["call", "do_not_call", "if_then"]
    situation: str = Field(min_length=1, max_length=500)
    call_name: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1200)
    sample_n: int = Field(default=0, ge=0)
    priority: int = Field(default=0, ge=0, le=100)
    confidence: Literal["insufficient", "directional", "usable"] = "insufficient"
    evidence_play_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class CallRulePatch(BaseModel):
    status: Literal["candidate", "approved", "rejected"] | None = None
    situation: str | None = Field(default=None, min_length=1, max_length=500)
    call_name: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str | None = Field(default=None, min_length=1, max_length=1200)
    priority: int | None = Field(default=None, ge=0, le=100)
    confidence: Literal["insufficient", "directional", "usable"] | None = None
    evidence_play_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


class PlayerLookEvidenceCreate(BaseModel):
    player_id: uuid.UUID
    source_type: Literal["game", "practice", "meeting"]
    event_date: date
    play_id: uuid.UUID | None = None
    formation: str = "UNKNOWN"
    motion: str = "UNKNOWN"
    coverage_family: str = "UNKNOWN"
    personnel: str = "UNKNOWN"
    call_name: str | None = Field(default=None, max_length=200)
    processed_correctly: bool
    notes: str | None = Field(default=None, max_length=1000)


class ChangedCallCreate(BaseModel):
    call_rule_id: uuid.UUID | None = None
    changed_call: bool
    change_type: Literal["added", "removed", "modified", "confirmed"]
    notes: str | None = Field(default=None, max_length=1000)


async def owned_week_plan(conn: asyncpg.Connection, week_plan_id: uuid.UUID, ctx: AuthContext) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT id, program_id, team_id, team_name, season, week, opponent_name, side, status, frozen_at
        FROM week_plans
        WHERE id=$1 AND program_id=$2
        """,
        week_plan_id,
        ctx.program_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="week_plan_not_found")
    return row


async def recompute_play_resolution(
    conn: asyncpg.Connection, program_id: uuid.UUID, play_id: uuid.UUID
) -> dict[str, Any]:
    votes = await conn.fetch(
        """
        SELECT field, value, user_id
        FROM play_tag_votes
        WHERE program_id=$1 AND play_id=$2
        """,
        program_id,
        play_id,
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for vote in votes:
        grouped[vote["field"]].append(vote["value"])

    resolved: dict[str, str] = {}
    agreement: dict[str, Any] = {}
    for field in TAG_FIELDS:
        values = grouped.get(field, [])
        if len(values) < 2:
            resolved[field] = "UNKNOWN"
            agreement[field] = {"n_taggers": len(values), "exact": False, "agreement_pct": None}
            continue
        counts: dict[str, int] = defaultdict(int)
        for value in values:
            counts[value] += 1
        winner, winner_n = max(counts.items(), key=lambda item: item[1])
        pct = round(100.0 * winner_n / len(values), 1)
        exact = len(counts) == 1
        resolved[field] = winner if exact else "UNKNOWN"
        agreement[field] = {"n_taggers": len(values), "exact": exact, "agreement_pct": pct}

    await conn.execute(
        """
        INSERT INTO program_play_tags (
            program_id, play_id, play_family, formation, motion, coverage_family,
            personnel, agreement, resolved_by, updated_at
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,NULL,now())
        ON CONFLICT (program_id,play_id) DO UPDATE SET
            play_family=EXCLUDED.play_family,
            formation=EXCLUDED.formation,
            motion=EXCLUDED.motion,
            coverage_family=EXCLUDED.coverage_family,
            personnel=EXCLUDED.personnel,
            agreement=EXCLUDED.agreement,
            resolved_by=NULL,
            updated_at=now()
        """,
        program_id,
        play_id,
        resolved["play_family"],
        resolved["formation"],
        resolved["motion"],
        resolved["coverage_family"],
        resolved["personnel"],
        json.dumps(agreement),
    )
    return {"tags": resolved, "agreement": agreement}


@router.get("/me")
async def me(ctx: AuthContext = Depends(require_auth)):
    return ctx.model_dump()


@router.get("/vocab")
async def vocab(ctx: AuthContext = Depends(require_auth)):
    return {
        "program_id": ctx.program_id,
        "tagging_rule": "Two blind taggers are required per play; field and term agreement must reach 80% on calibration or the term is removed.",
        "groups": {key: sorted(values) for key, values in VOCAB.items()},
    }


@router.get("/plays")
async def list_plays(
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    offense: str | None = None,
    defense: str | None = None,
    down: int | None = Query(default=None, ge=1, le=4),
    distance_bucket: Literal["short", "medium", "long"] | None = None,
    field_zone: Literal["backed_up", "open_field", "plus", "red_zone"] | None = None,
    personnel: str | None = None,
    formation: str | None = None,
    motion: str | None = None,
    coverage_family: str | None = None,
    play_family: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    for field, value in [
        ("personnel", personnel), ("formation", formation), ("motion", motion),
        ("coverage_family", coverage_family), ("play_family", play_family),
    ]:
        validate_tag(field, value)
    pool = require_pool(request)
    conditions = []
    values: list[Any] = [ctx.program_id]

    def add(expr: str, value: Any) -> None:
        if value is not None:
            values.append(value)
            conditions.append(f"{expr} = ${len(values)}")

    add("p.offense_team_name", offense)
    add("p.defense_team_name", defense)
    add("p.down", down)
    add("p.distance_bucket", distance_bucket)
    add("p.field_zone", field_zone)
    add("COALESCE(pt.personnel,'UNKNOWN')", personnel)
    add("COALESCE(pt.formation,'UNKNOWN')", formation)
    add("COALESCE(pt.motion,'UNKNOWN')", motion)
    add("COALESCE(pt.coverage_family,'UNKNOWN')", coverage_family)
    add("COALESCE(pt.play_family,'UNKNOWN')", play_family)
    values.append(limit)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT p.id,p.game_id,p.play_sequence,p.quarter,p.clock,p.down,p.distance,p.yard_line,
               p.distance_bucket,p.field_zone,p.offense_team_name,p.defense_team_name,
               p.result_yards,p.epa,p.ppa,p.success,p.explosive,p.turnover,
               p.external_source,p.external_id,p.source_play_type,p.play_text,p.source_play_class,
               COALESCE(pt.personnel,'UNKNOWN') AS personnel,
               COALESCE(pt.formation,'UNKNOWN') AS formation,
               COALESCE(pt.motion,'UNKNOWN') AS motion,
               COALESCE(pt.coverage_family,'UNKNOWN') AS coverage_family,
               COALESCE(pt.play_family,'UNKNOWN') AS play_family,
               pt.agreement, pt.resolved_by,
               EXISTS (
                   SELECT 1 FROM play_links l
                   WHERE l.program_id=$1 AND l.play_id=p.id
               ) AS has_film_link
        FROM plays p
        LEFT JOIN program_play_tags pt ON pt.program_id=$1 AND pt.play_id=p.id
        {where}
        ORDER BY p.game_id,p.play_sequence
        LIMIT ${len(values)}
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *values)
    return {"count": len(rows), "plays": [dict(row) for row in rows]}


@router.post("/plays/{play_id}/tag-votes", status_code=201)
async def tag_votes(
    play_id: uuid.UUID,
    body: TagBody,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_write(ctx)
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=422, detail="at_least_one_tag_required")
    for field, value in payload.items():
        validate_tag(field, value)
    pool = require_pool(request)
    async with pool.acquire() as conn:
        if not await conn.fetchval("SELECT 1 FROM plays WHERE id=$1", play_id):
            raise HTTPException(status_code=404, detail="play_not_found")
        async with conn.transaction():
            for field, value in payload.items():
                await conn.execute(
                    """
                    INSERT INTO play_tag_votes (program_id,play_id,field,value,user_id,created_at)
                    VALUES ($1,$2,$3,$4,$5,now())
                    ON CONFLICT (program_id,play_id,field,user_id)
                    DO UPDATE SET value=EXCLUDED.value,created_at=now()
                    """,
                    ctx.program_id, play_id, field, value, ctx.user_id,
                )
            resolution = await recompute_play_resolution(conn, ctx.program_id, play_id)
    return {"play_id": play_id, **resolution}


@router.post("/plays/{play_id}/tag-resolve")
async def resolve_tags(
    play_id: uuid.UUID,
    body: TagBody,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_coach(ctx)
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=422, detail="at_least_one_tag_required")
    for field, value in payload.items():
        validate_tag(field, value)
    pool = require_pool(request)
    async with pool.acquire() as conn:
        if not await conn.fetchval("SELECT 1 FROM plays WHERE id=$1", play_id):
            raise HTTPException(status_code=404, detail="play_not_found")
        current = await conn.fetchrow(
            """
            SELECT play_family,formation,motion,coverage_family,personnel,agreement
            FROM program_play_tags WHERE program_id=$1 AND play_id=$2
            """,
            ctx.program_id, play_id,
        )
        tags = {field: (current[field] if current else "UNKNOWN") for field in TAG_FIELDS}
        tags.update(payload)
        agreement = dict(current["agreement"] or {}) if current else {}
        for field in payload:
            agreement[field] = {"method": "coach_override", "user_id": str(ctx.user_id)}
        await conn.execute(
            """
            INSERT INTO program_play_tags (
                program_id,play_id,play_family,formation,motion,coverage_family,personnel,
                agreement,resolved_by,updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,now())
            ON CONFLICT (program_id,play_id) DO UPDATE SET
                play_family=EXCLUDED.play_family,formation=EXCLUDED.formation,motion=EXCLUDED.motion,
                coverage_family=EXCLUDED.coverage_family,personnel=EXCLUDED.personnel,
                agreement=EXCLUDED.agreement,resolved_by=EXCLUDED.resolved_by,updated_at=now()
            """,
            ctx.program_id, play_id, tags["play_family"], tags["formation"], tags["motion"],
            tags["coverage_family"], tags["personnel"], json.dumps(agreement), ctx.user_id,
        )
    return {"play_id": play_id, "tags": tags, "resolved_by": ctx.user_id}


@router.get("/tag-agreement")
async def tag_agreement(
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    game_id: uuid.UUID | None = None,
):
    pool = require_pool(request)
    sql = """
        SELECT v.play_id,v.field,v.value,v.user_id
        FROM play_tag_votes v
        JOIN plays p ON p.id=v.play_id
        WHERE v.program_id=$1
    """
    args: list[Any] = [ctx.program_id]
    if game_id:
        sql += " AND p.game_id=$2"
        args.append(game_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)

    groups: dict[tuple[uuid.UUID, str], list[str]] = defaultdict(list)
    for row in rows:
        groups[(row["play_id"], row["field"])].append(row["value"])

    by_field: dict[str, dict[str, int]] = {field: {"overlap": 0, "exact": 0} for field in TAG_FIELDS}
    by_term: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"opportunities": 0, "agreements": 0})
    for (_, field), values in groups.items():
        if len(values) < 2:
            continue
        by_field[field]["overlap"] += 1
        exact = len(set(values)) == 1
        if exact:
            by_field[field]["exact"] += 1
        for term in set(values):
            by_term[(field, term)]["opportunities"] += 1
            if exact and values[0] == term:
                by_term[(field, term)]["agreements"] += 1

    field_result = {}
    for field, counts in by_field.items():
        pct = round(100.0 * counts["exact"] / counts["overlap"], 1) if counts["overlap"] else None
        field_result[field] = {**counts, "agreement_pct": pct, "usable": bool(pct is not None and pct >= 80.0)}

    term_result = []
    for (field, term), counts in sorted(by_term.items()):
        pct = round(100.0 * counts["agreements"] / counts["opportunities"], 1) if counts["opportunities"] else None
        status = "kill" if counts["opportunities"] >= 10 and pct is not None and pct < 80.0 else "active"
        term_result.append({"field": field, "term": term, **counts, "agreement_pct": pct, "status": status})
    return {"program_id": ctx.program_id, "by_field": field_result, "by_term": term_result}


@router.post("/plays/{play_id}/links", status_code=201)
async def create_play_link(
    play_id: uuid.UUID,
    body: PlayLinkBody,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_write(ctx)
    pool = require_pool(request)
    link_id = uuid.uuid4()
    async with pool.acquire() as conn:
        if not await conn.fetchval("SELECT 1 FROM plays WHERE id=$1", play_id):
            raise HTTPException(status_code=404, detail="play_not_found")
        await conn.execute(
            """
            INSERT INTO play_links (id,program_id,play_id,provider,url,created_by)
            VALUES ($1,$2,$3,$4,$5,$6)
            """,
            link_id, ctx.program_id, play_id, body.provider, str(body.url), ctx.user_id,
        )
    return {"id": link_id, "play_id": play_id, "provider": body.provider, "url": str(body.url)}


@router.post("/week-plans", status_code=201)
async def create_week_plan(
    body: WeekPlanCreate,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_coach(ctx)
    pool = require_pool(request)
    plan_id = uuid.uuid4()
    async with pool.acquire() as conn:
        if body.team_id and not await conn.fetchval("SELECT 1 FROM teams WHERE id=$1", body.team_id):
            raise HTTPException(status_code=422, detail="team_id_not_found")
        row = await conn.fetchrow(
            """
            INSERT INTO week_plans (
                id,program_id,team_id,team_name,season,week,opponent_name,side,status,created_by
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'open',$9)
            ON CONFLICT (program_id,team_name,season,week,side)
            DO UPDATE SET opponent_name=EXCLUDED.opponent_name, team_id=EXCLUDED.team_id
            RETURNING *
            """,
            plan_id, ctx.program_id, body.team_id, body.team_name, body.season, body.week,
            body.opponent_name, body.side, ctx.user_id,
        )
    return dict(row)


@router.get("/week-plans/{week_plan_id}/opponent")
async def opponent_one_pager(
    week_plan_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    min_n: int = Query(default=8, ge=4, le=50),
):
    pool = require_pool(request)
    async with pool.acquire() as conn:
        plan = await owned_week_plan(conn, week_plan_id, ctx)
        rows = await conn.fetch(
            """
            SELECT pt.play_family,pt.formation,pt.motion,pt.coverage_family,pt.personnel,
                   COUNT(*)::int AS n,
                   ROUND(100.0*AVG(CASE WHEN p.success THEN 1 ELSE 0 END),1) AS success_pct,
                   ROUND(AVG(COALESCE(p.epa,p.ppa))::numeric,3) AS avg_value,
                   ARRAY_AGG(p.id ORDER BY p.game_id,p.play_sequence) AS evidence_play_ids
            FROM plays p
            JOIN program_play_tags pt ON pt.program_id=$1 AND pt.play_id=p.id
            WHERE p.offense_team_name=$2
              AND pt.play_family <> 'UNKNOWN'
            GROUP BY pt.play_family,pt.formation,pt.motion,pt.coverage_family,pt.personnel
            ORDER BY n DESC
            LIMIT 25
            """,
            ctx.program_id, plan["opponent_name"],
        )
    tendencies = []
    for row in rows:
        item = dict(row)
        n = item["n"]
        item["confidence"] = "insufficient" if n < 8 else "directional" if n < 20 else "usable"
        item["actionable"] = n >= min_n
        tendencies.append(item)
    return {
        "week_plan_id": week_plan_id,
        "opponent": plan["opponent_name"],
        "min_n": min_n,
        "tendencies": tendencies,
        "honesty_rule": "Rows below n=8 are questions, not game-plan facts.",
    }


@router.get("/week-plans/{week_plan_id}/self-scout")
async def self_scout(
    week_plan_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    min_n: int = Query(default=8, ge=4, le=50),
):
    pool = require_pool(request)
    async with pool.acquire() as conn:
        plan = await owned_week_plan(conn, week_plan_id, ctx)
        rows = await conn.fetch(
            """
            SELECT pt.play_family,pt.formation,pt.motion,pt.personnel,
                   COUNT(*)::int AS n,
                   SUM(CASE WHEN p.explosive THEN 1 ELSE 0 END)::int AS explosives,
                   SUM(CASE WHEN NOT p.success THEN 1 ELSE 0 END)::int AS failures,
                   ROUND(100.0*AVG(CASE WHEN p.success THEN 1 ELSE 0 END),1) AS success_pct,
                   ARRAY_AGG(p.id ORDER BY p.game_id,p.play_sequence) AS evidence_play_ids
            FROM plays p
            JOIN program_play_tags pt ON pt.program_id=$1 AND pt.play_id=p.id
            WHERE p.offense_team_name=$2
              AND pt.play_family <> 'UNKNOWN'
            GROUP BY pt.play_family,pt.formation,pt.motion,pt.personnel
            ORDER BY n DESC
            LIMIT 25
            """,
            ctx.program_id, plan["team_name"],
        )
    families = []
    for row in rows:
        item = dict(row)
        item["confidence"] = "insufficient" if item["n"] < 8 else "directional" if item["n"] < 20 else "usable"
        item["actionable"] = item["n"] >= min_n
        families.append(item)
    return {"week_plan_id": week_plan_id, "team": plan["team_name"], "min_n": min_n, "families": families}


@router.post("/week-plans/{week_plan_id}/call-rules", status_code=201)
async def create_call_rule(
    week_plan_id: uuid.UUID,
    body: CallRuleCreate,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_coach(ctx)
    pool = require_pool(request)
    rule_id = uuid.uuid4()
    async with pool.acquire() as conn:
        plan = await owned_week_plan(conn, week_plan_id, ctx)
        row = await conn.fetchrow(
            """
            INSERT INTO call_rules (
                id,program_id,week_plan_id,opponent_name,rule_type,situation,call_name,reason,
                sample_n,priority,confidence,evidence_play_ids,status,created_by,updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::uuid[],'candidate',$13,now())
            RETURNING *
            """,
            rule_id, ctx.program_id, week_plan_id, plan["opponent_name"], body.rule_type,
            body.situation, body.call_name, body.reason, body.sample_n, body.priority,
            body.confidence, body.evidence_play_ids, ctx.user_id,
        )
    return dict(row)


@router.patch("/week-plans/{week_plan_id}/call-rules/{rule_id}")
async def patch_call_rule(
    week_plan_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: CallRulePatch,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_coach(ctx)
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="no_changes")
    pool = require_pool(request)
    async with pool.acquire() as conn:
        plan = await owned_week_plan(conn, week_plan_id, ctx)
        if plan["status"] == "frozen":
            raise HTTPException(status_code=409, detail="week_plan_frozen")
        allowed = {"status", "situation", "call_name", "reason", "priority", "confidence", "evidence_play_ids"}
        sets, args = [], [rule_id, week_plan_id, ctx.program_id]
        for key, value in changes.items():
            if key not in allowed:
                continue
            args.append(value)
            cast = "::uuid[]" if key == "evidence_play_ids" else ""
            sets.append(f"{key}=${len(args)}{cast}")
        sets.append("updated_at=now()")
        row = await conn.fetchrow(
            f"""
            UPDATE call_rules SET {", ".join(sets)}
            WHERE id=$1 AND week_plan_id=$2 AND program_id=$3
            RETURNING *
            """,
            *args,
        )
        if not row:
            raise HTTPException(status_code=404, detail="call_rule_not_found")
    return dict(row)


@router.post("/week-plans/{week_plan_id}/player-look-evidence", status_code=201)
async def create_player_evidence(
    week_plan_id: uuid.UUID,
    body: PlayerLookEvidenceCreate,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_write(ctx)
    for field in ("formation", "motion", "coverage_family", "personnel"):
        validate_tag(field, getattr(body, field))
    pool = require_pool(request)
    evidence_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await owned_week_plan(conn, week_plan_id, ctx)
        if not await conn.fetchval("SELECT 1 FROM players WHERE id=$1", body.player_id):
            raise HTTPException(status_code=422, detail="player_id_not_found")
        row = await conn.fetchrow(
            """
            INSERT INTO player_look_evidence (
                id,program_id,week_plan_id,player_id,source_type,event_date,play_id,
                formation,motion,coverage_family,personnel,call_name,processed_correctly,
                notes,created_by
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
            RETURNING *
            """,
            evidence_id, ctx.program_id, week_plan_id, body.player_id, body.source_type,
            body.event_date, body.play_id, body.formation, body.motion, body.coverage_family,
            body.personnel, body.call_name, body.processed_correctly, body.notes, ctx.user_id,
        )
    return dict(row)


@router.post("/week-plans/{week_plan_id}/freeze")
async def freeze_week_plan(
    week_plan_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_coach(ctx)
    pool = require_pool(request)
    async with pool.acquire() as conn:
        await owned_week_plan(conn, week_plan_id, ctx)
        row = await conn.fetchrow(
            """
            UPDATE week_plans SET status='frozen',frozen_at=now()
            WHERE id=$1 AND program_id=$2
            RETURNING *
            """,
            week_plan_id, ctx.program_id,
        )
    return dict(row)


@router.get("/week-plans/{week_plan_id}/call-sheet")
async def call_sheet(
    week_plan_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    min_n: int = Query(default=8, ge=4, le=50),
):
    pool = require_pool(request)
    async with pool.acquire() as conn:
        plan = await owned_week_plan(conn, week_plan_id, ctx)
        rules = await conn.fetch(
            """
            SELECT id,rule_type,situation,call_name,reason,sample_n,priority,confidence,
                   evidence_play_ids,status,updated_at
            FROM call_rules
            WHERE program_id=$1 AND week_plan_id=$2 AND status='approved'
            ORDER BY priority DESC,created_at
            LIMIT 15
            """,
            ctx.program_id, week_plan_id,
        )
        evidence = await conn.fetch(
            """
            SELECT ple.call_name,ple.formation,ple.motion,ple.coverage_family,ple.personnel,
                   p.id AS player_id,p.name AS player_name,
                   COUNT(*)::int AS n,
                   SUM(CASE WHEN ple.processed_correctly THEN 1 ELSE 0 END)::int AS correct,
                   MAX(ple.event_date) AS as_of
            FROM player_look_evidence ple
            JOIN players p ON p.id=ple.player_id
            WHERE ple.program_id=$1 AND ple.week_plan_id=$2
            GROUP BY ple.call_name,ple.formation,ple.motion,ple.coverage_family,ple.personnel,p.id,p.name
            ORDER BY ple.call_name,p.name
            """,
            ctx.program_id, week_plan_id,
        )
    rule_rows = []
    for rule in rules:
        item = dict(rule)
        item["actionable"] = item["sample_n"] >= min_n and item["confidence"] != "insufficient"
        rule_rows.append(item)
    return {
        "week_plan": dict(plan),
        "rules": rule_rows,
        "player_look_evidence": [dict(row) for row in evidence],
        "decision_rule": "No tendency or call rule becomes actionable below the minimum sample guard.",
        "never_claim": "Player evidence is football-performance evidence only; no IQ, diagnosis, medical, genetic, race, or standalone roster/scholarship/draft claim.",
    }


@router.post("/week-plans/{week_plan_id}/changed-call", status_code=201)
async def changed_call(
    week_plan_id: uuid.UUID,
    body: ChangedCallCreate,
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    require_coach(ctx)
    pool = require_pool(request)
    log_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await owned_week_plan(conn, week_plan_id, ctx)
        if body.call_rule_id:
            exists = await conn.fetchval(
                "SELECT 1 FROM call_rules WHERE id=$1 AND week_plan_id=$2 AND program_id=$3",
                body.call_rule_id, week_plan_id, ctx.program_id,
            )
            if not exists:
                raise HTTPException(status_code=422, detail="call_rule_not_in_week_plan")
        row = await conn.fetchrow(
            """
            INSERT INTO changed_call_logs (
                id,week_plan_id,call_rule_id,changed_call,change_type,notes,logged_by
            ) VALUES ($1,$2,$3,$4,$5,$6,$7)
            RETURNING *
            """,
            log_id, week_plan_id, body.call_rule_id, body.changed_call, body.change_type,
            body.notes, ctx.user_id,
        )
    return dict(row)

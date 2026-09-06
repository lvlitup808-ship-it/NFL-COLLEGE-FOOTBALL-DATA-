import asyncio
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

import asyncpg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

SERVICE_NAME = "fieldmind-api"
STARTED_AT = time.monotonic()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": int(time.time() * 1000),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "message": record.getMessage(),
        }
        if hasattr(record, "event"):
            payload["event"] = record.event
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger = logging.getLogger(SERVICE_NAME)
logger.handlers.clear()
logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
logger.propagate = False


def _uncaught_exception(exc_type, exc_value, exc_traceback):
    logger.critical(
        "uncaught_exception",
        exc_info=(exc_type, exc_value, exc_traceback),
        extra={"event": "uncaught_exception"},
    )


sys.excepthook = _uncaught_exception


class DatabaseManager:
    """Keeps DB connectivity out of the liveness path and reconnects with backoff."""

    def __init__(self) -> None:
        self.url = os.getenv("DATABASE_URL")
        self.pool: asyncpg.Pool | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.pool_max = max(1, int(os.getenv("DB_POOL_MAX", "5")))
        self.connect_timeout = float(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "3"))

    async def start(self) -> None:
        self._task = asyncio.create_task(self._maintain(), name="db-maintainer")

    async def _open_pool(self) -> None:
        if not self.url or self.pool is not None:
            return
        async with self._lock:
            if self.pool is not None:
                return
            self.pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    dsn=self.url,
                    min_size=1,
                    max_size=self.pool_max,
                    command_timeout=3,
                    max_inactive_connection_lifetime=300,
                ),
                timeout=self.connect_timeout,
            )
            logger.info("database_pool_connected", extra={"event": "db_connected"})

    async def _drop_pool(self) -> None:
        pool, self.pool = self.pool, None
        if pool is not None:
            try:
                await asyncio.wait_for(pool.close(), timeout=5)
            except Exception:
                logger.exception("database_pool_close_failed", extra={"event": "db_close_failed"})

    async def _maintain(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                if not self.url:
                    await self._sleep_or_stop(5)
                    continue

                if self.pool is None:
                    await self._open_pool()
                    backoff = 1.0
                else:
                    async with self.pool.acquire() as conn:
                        await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=1.5)

                await self._sleep_or_stop(15)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("database_connectivity_failed", extra={"event": "db_connectivity_failed"})
                await self._drop_pool()
                await self._sleep_or_stop(backoff)
                backoff = min(backoff * 2, 30)

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def close(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._drop_pool()


def _loop_exception_handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
    exc = context.get("exception")
    message = context.get("message", "unhandled_async_exception")
    logger.error(
        message,
        exc_info=(type(exc), exc, exc.__traceback__) if exc else None,
        extra={"event": "unhandled_async_exception"},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_loop_exception_handler)
    db = DatabaseManager()
    app.state.db = db
    await db.start()
    logger.info("service_started", extra={"event": "startup"})
    try:
        yield
    finally:
        logger.info("graceful_shutdown_started", extra={"event": "shutdown_start"})
        await db.close()
        logger.info("graceful_shutdown_complete", extra={"event": "shutdown_complete"})


app = FastAPI(
    title="FIELDMIND API",
    version="0.1.0",
    description="Play intelligence, opponent tendency, self-scout, cognition evidence, and QB translation V1.",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            extra={"event": "request_failed", "request_id": request_id},
        )
        raise
    response.headers["x-request-id"] = request_id
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    logger.info(
        f"{request.method} {request.url.path} {response.status_code} {elapsed_ms}ms",
        extra={"event": "request", "request_id": request_id},
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_request_exception", extra={"event": "request_exception"})
    return JSONResponse(status_code=500, content={"error": "internal_server_error"})


def require_pool(request: Request) -> asyncpg.Pool:
    pool = request.app.state.db.pool
    if pool is None:
        raise HTTPException(status_code=503, detail="database_not_ready")
    return pool


@app.get("/health")
async def health() -> dict[str, Any]:
    """Railway liveness. Intentionally has no DB or external-service dependency."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "uptime_ms": int((time.monotonic() - STARTED_AT) * 1000),
    }


@app.get("/ready")
async def ready(request: Request):
    pool = request.app.state.db.pool
    if pool is None:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "disconnected"})
    try:
        async with pool.acquire() as conn:
            await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=0.8)
        return {"status": "ready", "database": "ok"}
    except Exception:
        logger.exception("readiness_database_failed", extra={"event": "readiness_failed"})
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "error"})


class ClipAttachRequest(BaseModel):
    object_key: str = Field(min_length=3, max_length=512)
    provider: Literal["s3", "r2", "railway_bucket"] = "s3"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)


class OpponentReportRequest(BaseModel):
    opponent: str = Field(min_length=1, max_length=120)
    down: int | None = Field(default=None, ge=1, le=4)
    distance_bucket: Literal["short", "medium", "long"] | None = None
    field_zone: Literal["backed_up", "open_field", "plus", "red_zone"] | None = None
    min_n: int = Field(default=8, ge=4, le=50)


class QbTranslationInput(BaseModel):
    epa_per_dropback: float = Field(ge=-1.5, le=1.5)
    pressure_success_rate: float = Field(ge=0, le=1)
    turnover_worthy_rate: float = Field(ge=0, le=0.30)
    processing_score: float = Field(ge=0, le=100)
    sample_dropbacks: int = Field(ge=1, le=2000)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


@app.get("/api/v1/plays")
async def list_plays(
    request: Request,
    offense: str | None = None,
    defense: str | None = None,
    down: int | None = Query(default=None, ge=1, le=4),
    distance_bucket: Literal["short", "medium", "long"] | None = None,
    field_zone: Literal["backed_up", "open_field", "plus", "red_zone"] | None = None,
    personnel: str | None = None,
    formation: str | None = None,
    play_family: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    pool = require_pool(request)
    conditions: list[str] = []
    values: list[Any] = []

    def add(field: str, value: Any) -> None:
        if value is not None:
            values.append(value)
            conditions.append(f"{field} = ${len(values)}")

    add("offense_team_name", offense)
    add("defense_team_name", defense)
    add("down", down)
    add("distance_bucket", distance_bucket)
    add("field_zone", field_zone)
    add("personnel_offense", personnel)
    add("formation", formation)
    add("play_family", play_family)
    values.append(limit)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
        SELECT id, game_id, play_sequence, quarter, clock, down, distance, yard_line,
               distance_bucket, field_zone, offense_team_name, defense_team_name,
               personnel_offense, formation, motion, play_family, concept, coverage,
               pressure, result_yards, epa, success, explosive, turnover, qb_player_id,
               cognition_events, tags
        FROM plays
        {where}
        ORDER BY game_id, play_sequence
        LIMIT ${len(values)}
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *values)
    return {"count": len(rows), "plays": [dict(row) for row in rows]}


@app.post("/api/v1/plays/{play_id}/clip", status_code=201)
async def attach_clip(play_id: uuid.UUID, body: ClipAttachRequest, request: Request):
    if body.end_ms <= body.start_ms:
        raise HTTPException(status_code=422, detail="end_ms_must_be_greater_than_start_ms")
    pool = require_pool(request)
    clip_id = uuid.uuid4()
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM plays WHERE id=$1", play_id)
        if not exists:
            raise HTTPException(status_code=404, detail="play_not_found")
        await conn.execute(
            """
            INSERT INTO clips (id, play_id, provider, object_key, start_ms, end_ms)
            VALUES ($1,$2,$3,$4,$5,$6)
            """,
            clip_id,
            play_id,
            body.provider,
            body.object_key,
            body.start_ms,
            body.end_ms,
        )
    return {"id": clip_id, "play_id": play_id, **body.model_dump()}


@app.post("/api/v1/reports/opponent")
async def opponent_report(body: OpponentReportRequest, request: Request):
    pool = require_pool(request)
    conditions = ["offense_team_name = $1"]
    values: list[Any] = [body.opponent]
    for field, value in [
        ("down", body.down),
        ("distance_bucket", body.distance_bucket),
        ("field_zone", body.field_zone),
    ]:
        if value is not None:
            values.append(value)
            conditions.append(f"{field} = ${len(values)}")
    where = " AND ".join(conditions)
    sql = f"""
        SELECT play_family,
               COUNT(*)::int AS n,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS rate_pct,
               ROUND(AVG(epa)::numeric, 3) AS avg_epa,
               ROUND(AVG(result_yards)::numeric, 1) AS avg_yards,
               ROUND(100.0 * AVG(CASE WHEN success THEN 1 ELSE 0 END), 1) AS success_pct
        FROM plays
        WHERE {where}
        GROUP BY play_family
        ORDER BY n DESC, avg_epa DESC
    """
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(sql, *values)]
    total_n = sum(r["n"] for r in rows)
    sample_status = "insufficient" if total_n < body.min_n else ("directional" if total_n < 20 else "usable")
    return {
        "opponent": body.opponent,
        "filters": {
            "down": body.down,
            "distance_bucket": body.distance_bucket,
            "field_zone": body.field_zone,
        },
        "sample_n": total_n,
        "min_n": body.min_n,
        "flagged": total_n >= body.min_n,
        "sample_status": sample_status,
        "tendencies": rows,
        "warning": None if total_n >= body.min_n else "Do not game-plan from this split yet; sample is below the n-guard.",
    }


@app.get("/api/v1/reports/self-scout")
async def self_scout(team: str, request: Request, min_n: int = Query(default=8, ge=4, le=50)):
    pool = require_pool(request)
    sql = """
        SELECT play_family,
               COUNT(*)::int AS n,
               SUM(CASE WHEN explosive THEN 1 ELSE 0 END)::int AS explosives,
               SUM(CASE WHEN NOT success THEN 1 ELSE 0 END)::int AS failures,
               ROUND(AVG(epa)::numeric, 3) AS avg_epa,
               ROUND(100.0 * AVG(CASE WHEN success THEN 1 ELSE 0 END), 1) AS success_pct
        FROM plays
        WHERE offense_team_name=$1
        GROUP BY play_family
        ORDER BY avg_epa DESC
    """
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(sql, team)]
    for row in rows:
        row["sample_flag"] = "ok" if row["n"] >= min_n else "low_n"
    return {"team": team, "min_n": min_n, "families": rows}


@app.get("/api/v1/players/{player_id}")
async def player_card(player_id: uuid.UUID, request: Request):
    pool = require_pool(request)
    async with pool.acquire() as conn:
        player = await conn.fetchrow(
            "SELECT id, team_id, name, position, class_year, jersey FROM players WHERE id=$1",
            player_id,
        )
        if not player:
            raise HTTPException(status_code=404, detail="player_not_found")
        traits = await conn.fetch(
            """
            SELECT trait, score, sample_n, evidence_count, confidence, as_of
            FROM cognition_trait_scores
            WHERE player_id=$1
            ORDER BY trait
            """,
            player_id,
        )
        production = await conn.fetchrow(
            """
            SELECT COUNT(*)::int AS plays,
                   ROUND(AVG(epa)::numeric, 3) AS avg_epa,
                   ROUND(100.0 * AVG(CASE WHEN success THEN 1 ELSE 0 END), 1) AS success_pct
            FROM plays WHERE qb_player_id=$1
            """,
            player_id,
        )
    return {
        "player": dict(player),
        "production": dict(production),
        "cognition": [dict(t) for t in traits],
        "guardrails": [
            "Trait scores are football-performance evidence, not IQ or clinical assessment.",
            "Never use a cognition score as a standalone cut, scholarship, contract, or draft decision.",
        ],
    }


@app.get("/api/v1/weekly/call-sheet")
async def weekly_call_sheet(opponent: str, request: Request, min_n: int = Query(default=8, ge=4, le=50)):
    pool = require_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT play_family, COUNT(*)::int AS n,
                   ROUND(AVG(epa)::numeric, 3) AS avg_epa,
                   ROUND(100.0 * AVG(CASE WHEN success THEN 1 ELSE 0 END),1) AS success_pct
            FROM plays
            WHERE offense_team_name=$1
            GROUP BY play_family
            ORDER BY n DESC
            LIMIT 6
            """,
            opponent,
        )
        avoid = await conn.fetch(
            """
            SELECT situation, call_name, reason, sample_n
            FROM call_rules
            WHERE opponent_name=$1 AND rule_type='do_not_call'
            ORDER BY priority DESC
            LIMIT 5
            """,
            opponent,
        )
    tendencies = [dict(r) for r in rows]
    return {
        "opponent": opponent,
        "one_page": True,
        "tendencies": [
            {**r, "sample_flag": "ok" if r["n"] >= min_n else "low_n"}
            for r in tendencies
        ],
        "do_not_call": [dict(r) for r in avoid],
        "decision_rule": "No tendency becomes a call-sheet flag below the minimum sample guard.",
    }


@app.post("/api/v1/models/qb-college-to-nfl")
async def qb_college_to_nfl(body: QbTranslationInput):
    """Transparent V1 baseline, not a validated draft model."""
    production = clamp(50 + body.epa_per_dropback * 80)
    pressure = clamp(body.pressure_success_rate * 100)
    ball_security = clamp(100 - body.turnover_worthy_rate * 800)
    processing = clamp(body.processing_score)
    raw = 0.35 * production + 0.25 * pressure + 0.20 * ball_security + 0.20 * processing
    sample_confidence = min(1.0, body.sample_dropbacks / 300)
    regressed = 50 + (raw - 50) * sample_confidence
    if body.sample_dropbacks < 100:
        confidence = "low"
    elif body.sample_dropbacks < 300:
        confidence = "directional"
    else:
        confidence = "usable"
    return {
        "position": "QB",
        "translation_score": round(regressed, 1),
        "confidence": confidence,
        "sample_dropbacks": body.sample_dropbacks,
        "components": {
            "production": round(production, 1),
            "pressure": round(pressure, 1),
            "ball_security": round(ball_security, 1),
            "processing": round(processing, 1),
        },
        "model_status": "v1_heuristic_baseline_not_validated",
        "never_claim": "This score does not predict NFL success by itself and must not be used as a standalone draft decision.",
    }

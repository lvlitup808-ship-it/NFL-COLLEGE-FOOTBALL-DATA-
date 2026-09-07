import asyncio
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Literal

import asyncpg
import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger("fieldmind-api")

CLAUDE_MODEL = "claude-sonnet-5"
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_TIMEOUT_SECONDS = 20.0

LIEUTENANT_SYSTEM_PROMPT = """You are FIELDMIND Lieutenant, not a GM and not a fan.
You do not flatter the user or the prospect.
You may only use the JSON evidence provided. No web, no memory of famous players.
If evidence is thin, say so and lower confidence.
Always produce FINDING, EVIDENCE play_ids, CONFIDENCE, DECISION, FALSIFIER, DISSENT.
DISSENT is mandatory: one concrete reason the staff’s implied favorite take is wrong.
Never output a single Football IQ number.
Never give medical or psychiatric claims.
Movement ≠ processing. If speed is high and diagnosis events are late, say athlete not processor."""

ATHLETICISM_TERMS = (
    "speed",
    "fast",
    "athletic",
    "athleticism",
    "accel",
    "acceleration",
    "burst",
    "change of direction",
    "cod",
    "separation",
    "sep yards",
    "getoff",
    "get-off",
    "movement",
    "quickness",
)

COMBINE_EVENT_TERMS = {
    "40_yard_dash": ("40-yard", "40 yard", "forty", "40yd"),
    "bench_press": ("bench", "bench press"),
    "vertical_jump": ("vertical", "vertical jump"),
    "broad_jump": ("broad", "broad jump"),
    "three_cone": ("three cone", "3 cone", "3-cone", "three-cone"),
    "short_shuttle": ("shuttle", "short shuttle"),
}


class LieutenantAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    player_id: uuid.UUID | None = None
    team: str | None = Field(default=None, min_length=1, max_length=120)
    week: int | None = Field(default=None, ge=0, le=30)
    min_n: int = Field(default=8, ge=1, le=100)


class LieutenantEvidence(BaseModel):
    play_ids: list[str]
    n: int
    date_range: str


class LieutenantResponse(BaseModel):
    status: Literal["ok", "insufficient_evidence", "not_configured"]
    finding: str
    evidence: LieutenantEvidence
    confidence: Literal["low", "med", "high"]
    decision: str
    falsifier: str
    dissent: str


class CombineAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def _require_pool(request: Request) -> asyncpg.Pool:
    pool = request.app.state.db.pool
    if pool is None:
        raise HTTPException(status_code=503, detail="database_not_ready")
    return pool


def _needs_movement(question: str) -> bool:
    lowered = question.casefold()
    return any(term in lowered for term in ATHLETICISM_TERMS)


def _date_range(plays: list[dict[str, Any]]) -> str:
    dates = sorted({row["game_date"] for row in plays if row.get("game_date")})
    if not dates:
        return "unknown"
    return f"{dates[0]} to {dates[-1]}"


def _base_response(
    *,
    status: Literal["ok", "insufficient_evidence", "not_configured"],
    finding: str,
    play_ids: list[str],
    date_range: str,
    confidence: Literal["low", "med", "high"],
    decision: str,
    falsifier: str,
    dissent: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "finding": finding,
        "evidence": {"play_ids": play_ids, "n": len(play_ids), "date_range": date_range},
        "confidence": confidence,
        "decision": decision,
        "falsifier": falsifier,
        "dissent": dissent,
    }


async def _retrieve_evidence(
    conn: asyncpg.Connection,
    player_id: uuid.UUID | None,
    team: str | None,
    week: int | None,
) -> dict[str, Any]:
    plays = [
        dict(row)
        for row in await conn.fetch(
            """
            SELECT
              p.id::text AS play_id,
              p.qb_player_id::text AS qb_player_id,
              g.game_date::text AS game_date,
              g.week,
              p.down,
              p.distance,
              p.yard_line,
              p.offense_team_name,
              p.defense_team_name,
              p.personnel_offense,
              p.formation,
              p.motion,
              p.play_family,
              p.concept,
              p.coverage,
              p.pressure,
              p.result_yards,
              p.epa,
              p.ppa,
              p.success,
              p.explosive,
              p.turnover,
              p.cognition_events
            FROM plays p
            JOIN games g ON g.id=p.game_id
            WHERE
              ($1::uuid IS NULL OR p.qb_player_id=$1 OR EXISTS (
                SELECT 1 FROM movement_events me
                WHERE me.play_id=p.id AND me.player_id=$1
              ))
              AND ($2::text IS NULL OR p.offense_team_name=$2 OR p.defense_team_name=$2)
              AND ($3::int IS NULL OR g.week=$3)
            ORDER BY g.game_date NULLS LAST, p.game_id, p.play_sequence
            LIMIT 100
            """,
            player_id,
            team,
            week,
        )
    ]
    if not plays:
        return {"plays": [], "movement": [], "cognition": []}

    play_uuids = [uuid.UUID(row["play_id"]) for row in plays]
    movement = [
        dict(row)
        for row in await conn.fetch(
            """
            SELECT
              play_id::text AS play_id,
              player_id::text AS player_id,
              source,
              max_speed_mph,
              accel,
              cod,
              sep_yards,
              getoff_ms,
              extra
            FROM movement_events
            WHERE play_id=ANY($1::uuid[])
              AND ($2::uuid IS NULL OR player_id=$2)
            ORDER BY play_id, player_id, source
            """,
            play_uuids,
            player_id,
        )
    ]

    if player_id is not None:
        player_ids = [player_id]
    else:
        player_ids = sorted(
            {uuid.UUID(row["qb_player_id"]) for row in plays if row.get("qb_player_id")},
            key=str,
        )

    cognition: list[dict[str, Any]] = []
    if player_ids:
        cognition = [
            dict(row)
            for row in await conn.fetch(
                """
                SELECT
                  player_id::text AS player_id,
                  trait,
                  score,
                  sample_n,
                  evidence_count,
                  confidence,
                  as_of::text AS as_of,
                  evidence
                FROM cognition_trait_scores
                WHERE player_id=ANY($1::uuid[])
                ORDER BY player_id, trait, as_of DESC
                """,
                player_ids,
            )
        ]
    return {"plays": plays, "movement": movement, "cognition": cognition}


def _extract_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Claude response must be an object")
    required = ("finding", "confidence", "decision", "falsifier", "dissent")
    if any(not isinstance(parsed.get(key), str) or not parsed[key].strip() for key in required):
        raise ValueError("Claude response missing required fields")
    if parsed["confidence"] not in {"low", "med", "high"}:
        raise ValueError("Claude response confidence is invalid")
    return parsed


async def call_claude(question: str, evidence: dict[str, Any], api_key: str) -> dict[str, Any]:
    prompt = (
        "Evaluate the question using only the evidence JSON below. "
        "Return ONLY one JSON object with string keys finding, confidence, decision, falsifier, dissent. "
        "confidence must be low, med, or high. The server will attach canonical play_ids.\n\n"
        f"QUESTION:\n{question}\n\nEVIDENCE_JSON:\n"
        f"{json.dumps(evidence, separators=(',', ':'), default=str)}"
    )

    async def _request() -> dict[str, Any]:
        timeout = httpx.Timeout(CLAUDE_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                CLAUDE_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 700,
                    "system": LIEUTENANT_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            payload = response.json()
        text = "\n".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        if not text:
            raise ValueError("Claude response contained no text")
        return _extract_json_text(text)

    return await asyncio.wait_for(_request(), timeout=CLAUDE_TIMEOUT_SECONDS)


async def _persist_run(
    conn: asyncpg.Connection,
    *,
    question: str,
    filters: dict[str, Any],
    answer: dict[str, Any],
    play_ids: list[str],
    model: str,
    latency_ms: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO lieutenant_runs (question,filters,answer,play_ids,model,latency_ms)
        VALUES ($1,$2,$3,$4::text[],$5,$6)
        """,
        question,
        filters,
        answer,
        play_ids,
        model,
        latency_ms,
    )


@router.post("/lieutenant/ask", response_model=LieutenantResponse)
async def lieutenant_ask(body: LieutenantAskRequest, request: Request):
    started = time.monotonic()
    pool = _require_pool(request)
    filters = {
        "player_id": str(body.player_id) if body.player_id else None,
        "team": body.team,
        "week": body.week,
        "min_n": body.min_n,
    }

    async with pool.acquire() as conn:
        evidence = await _retrieve_evidence(conn, body.player_id, body.team, body.week)
        plays = evidence["plays"]
        play_ids = [row["play_id"] for row in plays]
        date_range = _date_range(plays)

        if len(play_ids) < body.min_n or (_needs_movement(body.question) and not evidence["movement"]):
            if len(play_ids) < body.min_n:
                reason = f"Only {len(play_ids)} matching plays; minimum is {body.min_n}."
            else:
                reason = "Question requires athleticism evidence, but no movement rows match these plays."
            answer = _base_response(
                status="insufficient_evidence",
                finding=reason,
                play_ids=play_ids,
                date_range=date_range,
                confidence="low",
                decision="No grade. Gather more play-linked evidence before making a personnel decision.",
                falsifier="Add enough matching play_ids and, for athletic questions, play-linked movement evidence.",
                dissent="A confident staff take is not evidence when the play-linked sample is below the guardrail.",
            )
            await _persist_run(
                conn,
                question=body.question,
                filters=filters,
                answer=answer,
                play_ids=play_ids,
                model="not_called",
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            return answer

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            answer = _base_response(
                status="not_configured",
                finding="Claude evaluator is not configured; play evidence was retrieved but not evaluated.",
                play_ids=play_ids,
                date_range=date_range,
                confidence="low",
                decision="No grade until the evaluator is configured.",
                falsifier="Configure ANTHROPIC_API_KEY and rerun the same evidence-backed question.",
                dissent="Do not substitute staff confidence for the missing evaluator pass.",
            )
            await _persist_run(
                conn,
                question=body.question,
                filters=filters,
                answer=answer,
                play_ids=play_ids,
                model=CLAUDE_MODEL,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            return answer

        try:
            evaluated = await call_claude(body.question, evidence, api_key)
            answer = _base_response(
                status="ok",
                finding=evaluated["finding"],
                play_ids=play_ids,
                date_range=date_range,
                confidence=evaluated["confidence"],
                decision=evaluated["decision"],
                falsifier=evaluated["falsifier"],
                dissent=evaluated["dissent"],
            )
        except Exception:
            logger.warning(
                "lieutenant_evaluator_unavailable",
                extra={"event": "lieutenant_evaluator_unavailable"},
            )
            answer = _base_response(
                status="not_configured",
                finding="Claude evaluator is unavailable; play evidence was retrieved but no evaluation was accepted.",
                play_ids=play_ids,
                date_range=date_range,
                confidence="low",
                decision="No grade. Retry after the evaluator is available.",
                falsifier="A successful evaluator response on the same play_ids can replace this fallback.",
                dissent="Do not turn an evaluator outage into a favorable or unfavorable prospect conclusion.",
            )

        await _persist_run(
            conn,
            question=body.question,
            filters=filters,
            answer=answer,
            play_ids=play_ids,
            model=CLAUDE_MODEL,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return answer


@router.get("/radar/hidden")
async def hidden_radar(
    request: Request,
    min_speed_pct: float = Query(default=75, ge=0, le=100),
):
    pool = _require_pool(request)
    percentile = min_speed_pct / 100.0
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH player_movement AS (
              SELECT
                player_id,
                COUNT(DISTINCT play_id)::int AS n_plays,
                MAX(max_speed_mph) AS max_speed_mph,
                AVG(max_speed_mph) AS avg_speed_mph,
                MAX(cod) AS max_cod,
                AVG(cod) AS avg_cod
              FROM movement_events
              GROUP BY player_id
            ),
            thresholds AS (
              SELECT
                percentile_cont($1::double precision)
                  WITHIN GROUP (ORDER BY max_speed_mph)
                  FILTER (WHERE max_speed_mph IS NOT NULL) AS speed_threshold,
                percentile_cont($1::double precision)
                  WITHIN GROUP (ORDER BY cod)
                  FILTER (WHERE cod IS NOT NULL) AS cod_threshold
              FROM movement_events
            )
            SELECT
              p.id::text AS player_id,
              pm.n_plays,
              pm.max_speed_mph,
              pm.avg_speed_mph,
              pm.max_cod,
              pm.avg_cod,
              NULL::double precision AS production_residual,
              CASE WHEN pm.n_plays < 8 THEN 'low_n' ELSE 'ok' END AS sample_size_flag
            FROM player_movement pm
            JOIN players p ON p.id=pm.player_id
            CROSS JOIN thresholds t
            WHERE
              (p.league_level IN ('FCS','OTHER') OR p.scout_visit_flag=false)
              AND (
                (t.speed_threshold IS NOT NULL AND pm.max_speed_mph >= t.speed_threshold)
                OR (t.cod_threshold IS NOT NULL AND pm.max_cod >= t.cod_threshold)
              )
            ORDER BY pm.max_speed_mph DESC NULLS LAST, pm.max_cod DESC NULLS LAST
            """,
            percentile,
        )
    players = []
    for row in rows:
        item = dict(row)
        players.append(
            {
                "player_id": item["player_id"],
                "n_plays": item["n_plays"],
                "movement_summary": {
                    "max_speed_mph": item["max_speed_mph"],
                    "avg_speed_mph": item["avg_speed_mph"],
                    "max_cod": item["max_cod"],
                    "avg_cod": item["avg_cod"],
                },
                "production_residual": item["production_residual"],
                "sample_size_flag": item["sample_size_flag"],
            }
        )
    return {"min_speed_pct": min_speed_pct, "players": players}


def parse_combine_question(question: str) -> dict[str, Any]:
    lowered = question.casefold()
    event = None
    for canonical, aliases in COMBINE_EVENT_TERMS.items():
        if any(alias in lowered for alias in aliases):
            event = canonical
            break

    if "combine" not in lowered and event is None:
        raise ValueError("question_not_about_combine_results")

    year_match = re.search(r"\b(20\d{2})\b", lowered)
    year = int(year_match.group(1)) if year_match else None

    comparator = None
    value = None
    patterns = (
        ("lte", r"(?:at most|no more than)\s*(\d+(?:\.\d+)?)"),
        ("gte", r"(?:at least|no less than)\s*(\d+(?:\.\d+)?)"),
        ("lt", r"(?:under|below|less than)\s*(\d+(?:\.\d+)?)"),
        ("gt", r"(?:over|above|greater than)\s*(\d+(?:\.\d+)?)"),
        ("lte", r"<=\s*(\d+(?:\.\d+)?)"),
        ("gte", r">=\s*(\d+(?:\.\d+)?)"),
        ("lt", r"<\s*(\d+(?:\.\d+)?)"),
        ("gt", r">\s*(\d+(?:\.\d+)?)"),
        ("eq", r"(?:equal to|exactly)\s*(\d+(?:\.\d+)?)"),
    )
    for operator, pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            comparator = operator
            value = float(match.group(1))
            break

    return {"event": event, "year": year, "comparator": comparator, "value": value}


@router.post("/ask/combine")
async def ask_combine(body: CombineAskRequest, request: Request):
    try:
        filters = parse_combine_question(body.question)
    except ValueError:
        raise HTTPException(status_code=422, detail="question_not_about_combine_results")

    pool = _require_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT player_id::text AS player_id,event,value,year,source
            FROM combine_results
            WHERE ($1::text IS NULL OR event=$1)
              AND ($2::int IS NULL OR year=$2)
              AND (
                $3::double precision IS NULL
                OR ($4::text='lt' AND value < $3)
                OR ($4::text='lte' AND value <= $3)
                OR ($4::text='gt' AND value > $3)
                OR ($4::text='gte' AND value >= $3)
                OR ($4::text='eq' AND value = $3)
              )
            ORDER BY year DESC,event,value
            LIMIT 100
            """,
            filters["event"],
            filters["year"],
            filters["value"],
            filters["comparator"],
        )
    return {"status": "ok", "filters": filters, "count": len(rows), "results": [dict(row) for row in rows]}

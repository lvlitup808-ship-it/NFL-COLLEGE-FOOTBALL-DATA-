import uuid

from fastapi import APIRouter, Depends, Request

from app.wedge import AuthContext, owned_week_plan, require_auth, require_pool

router = APIRouter(prefix="/api/v1", tags=["FIELDMIND Pilot"])


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

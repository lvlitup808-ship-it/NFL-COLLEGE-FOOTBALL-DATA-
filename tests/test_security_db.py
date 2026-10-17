"""Real PostgreSQL tests against disposable CI data, never a production database."""
import asyncio
import hashlib
import os
import secrets
import time
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    os.getenv("HARDENING_DB_TEST") != "1", reason="requires disposable migrated PostgreSQL"
)


@pytest.fixture(scope="module")
def tenant_data():
    ids = {name: uuid.uuid4() for name in (
        "a", "b", "coach_a", "coach_b", "viewer", "ga", "team_a", "team_b", "team_public",
        "player_a", "player_b", "player_public", "plan_a", "plan_b",
    )}
    tokens = {name: secrets.token_urlsafe(48) for name in ("coach_a", "coach_b", "viewer", "ga", "expired", "revoked")}

    async def setup():
        conn = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            async with conn.transaction():
                for tenant in ("a", "b"):
                    await conn.execute("INSERT INTO programs(id,name,level) VALUES($1,$2,'college')", ids[tenant], f"Security {ids[tenant]}")
                for name, tenant, role in (("coach_a", "a", "coach"), ("coach_b", "b", "coach"), ("viewer", "a", "viewer"), ("ga", "a", "ga")):
                    await conn.execute("INSERT INTO users(id,email) VALUES($1,$2)", ids[name], f"{ids[name]}@test.invalid")
                    await conn.execute("INSERT INTO program_memberships(program_id,user_id,role) VALUES($1,$2,$3)", ids[tenant], ids[name], role)
                    await conn.execute("INSERT INTO auth_tokens(user_id,token_hash,expires_at) VALUES($1,$2,now()+interval '1 hour')", ids[name], hashlib.sha256(tokens[name].encode()).hexdigest())
                await conn.execute("INSERT INTO auth_tokens(user_id,token_hash,expires_at) VALUES($1,$2,now()-interval '1 hour')", ids["coach_a"], hashlib.sha256(tokens["expired"].encode()).hexdigest())
                await conn.execute("INSERT INTO auth_tokens(user_id,token_hash,expires_at,revoked_at) VALUES($1,$2,now()+interval '1 hour',now())", ids["coach_a"], hashlib.sha256(tokens["revoked"].encode()).hexdigest())
                for tenant in ("a", "b", "public"):
                    await conn.execute("INSERT INTO teams(id,program_id,name,season) VALUES($1,$2,$3,2026)", ids[f"team_{tenant}"], ids.get(tenant), f"Team {ids[f'team_{tenant}']}")
                    await conn.execute("INSERT INTO players(id,team_id,name,position) VALUES($1,$2,$3,'QB')", ids[f"player_{tenant}"], ids[f"team_{tenant}"], f"Player {tenant}")
                for tenant in ("a", "b"):
                    await conn.execute("""INSERT INTO week_plans(id,program_id,team_id,team_name,season,week,opponent_name,side,created_by)
                        VALUES($1,$2,$3,$4,2026,1,'Opponent','offense',$5)""", ids[f"plan_{tenant}"], ids[tenant], ids[f"team_{tenant}"], f"Team {ids[f'team_{tenant}']}", ids[f"coach_{tenant}"])
        finally:
            await conn.close()

    async def cleanup():
        conn = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            # Only these generated fixtures: frozen child triggers block cascading deletes.
            await conn.execute("UPDATE week_plans SET status='open' WHERE program_id=ANY($1::uuid[])", [ids["a"], ids["b"]])
            await conn.execute("DELETE FROM programs WHERE id=ANY($1::uuid[])", [ids["a"], ids["b"]])
            await conn.execute("DELETE FROM teams WHERE id=$1", ids["team_public"])
            await conn.execute("DELETE FROM users WHERE id=ANY($1::uuid[])", [ids[x] for x in ("coach_a", "coach_b", "viewer", "ga")])
        finally:
            await conn.close()

    asyncio.run(setup())
    try:
        from app.pilot import app
        with TestClient(app) as client:
            for _ in range(50):
                if client.get("/ready").status_code == 200:
                    break
                time.sleep(0.1)
            else:
                pytest.fail("database pool did not become ready")
            auth = {name: {"Authorization": f"Bearer {token}"} for name, token in tokens.items()}
            yield client, ids, auth
    finally:
        asyncio.run(cleanup())


def test_expired_revoked_and_nonmember_tokens_fail_closed(tenant_data):
    client, ids, auth = tenant_data
    for name in ("expired", "revoked"):
        assert client.get("/api/v1/vocab", headers=auth[name]).status_code == 401
    spoofed_program = {**auth["coach_a"], "X-Program-ID": str(ids["b"])}
    assert client.get("/api/v1/vocab", headers=spoofed_program).status_code == 403


@pytest.mark.parametrize("kind", ["team", "player"])
def test_entity_aliases_cannot_reference_another_programs_roster(tenant_data, kind):
    client, ids, auth = tenant_data
    for tenant, status in (("b", 422), ("a", 201), ("public", 201)):
        result = client.post("/api/v1/entities", headers=auth["coach_a"], json={
            "kind": kind, "canonical_id": str(ids[f"{kind}_{tenant}"]),
            "source": "other", "external_id": f"security-{kind}-{tenant}",
        })
        assert result.status_code == status, result.text
    missing = client.post("/api/v1/entities", headers=auth["coach_a"], json={
        "kind": kind, "canonical_id": str(uuid.uuid4()), "source": "other", "external_id": "missing",
    })
    assert missing.status_code == 422 and missing.json()["detail"] == "canonical_id_not_found"


def test_week_and_player_references_are_program_scoped(tenant_data):
    client, ids, auth = tenant_data
    result = client.post("/api/v1/week-plans", headers=auth["coach_a"], json={
        "team_id": str(ids["team_b"]), "team_name": "Borrowed", "season": 2026,
        "week": 2, "opponent_name": "Opponent", "side": "offense",
    })
    assert result.status_code == 422
    for suffix in ("call-sheet", "call-rules", "roster-players", "opponent", "self-scout"):
        assert client.get(f"/api/v1/week-plans/{ids['plan_b']}/{suffix}", headers=auth["coach_a"]).status_code == 404
    for tenant, status in (("b", 422), ("a", 201)):
        result = client.post(f"/api/v1/week-plans/{ids['plan_a']}/player-look-evidence", headers=auth["coach_a"], json={
            "player_id": str(ids[f"player_{tenant}"]), "source_type": "practice",
            "event_date": "2026-10-17", "processed_correctly": True,
        })
        assert result.status_code == status, result.text


def test_search_ownership_and_viewer_read_only(tenant_data):
    client, ids, auth = tenant_data
    saved = client.post("/api/v1/play-searches", headers=auth["coach_a"], json={"name": "security search", "query": {"q": "test"}})
    assert saved.status_code == 201, saved.text
    search_id = saved.json()["id"]
    for role, expected in (("coach_b", 404), ("viewer", 403)):
        assert client.delete(f"/api/v1/play-searches/{search_id}", headers=auth[role]).status_code == expected
    assert client.post("/api/v1/play-searches", headers=auth["viewer"], json={"name": "blocked", "query": {}}).status_code == 403
    listed = client.get("/api/v1/play-searches", headers=auth["coach_b"])
    assert search_id not in [row["id"] for row in listed.json()["searches"]]
    assert client.delete(f"/api/v1/play-searches/{search_id}", headers=auth["coach_a"]).status_code == 204


def test_sql_injection_search_remains_literal(tenant_data):
    client, _, auth = tenant_data
    response = client.get("/api/v1/plays", headers=auth["coach_a"], params={"q": "' OR 1=1; DROP TABLE users; --"})
    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert client.get("/api/v1/vocab", headers=auth["coach_a"]).status_code == 200


def test_frozen_week_cannot_be_changed_by_upsert_or_repeat_freeze(tenant_data):
    client, ids, auth = tenant_data
    path = f"/api/v1/week-plans/{ids['plan_a']}"
    first = client.post(path + "/freeze", headers=auth["coach_a"])
    assert first.status_code == 200
    repeated = client.post(path + "/freeze", headers=auth["coach_a"])
    assert repeated.json()["frozen_at"] == first.json()["frozen_at"]
    blocked = client.post("/api/v1/week-plans", headers=auth["coach_a"], json={
        "team_name": f"Team {ids['team_a']}", "team_id": str(ids["team_a"]),
        "season": 2026, "week": 1, "opponent_name": "CHANGED", "side": "offense",
    })
    assert blocked.status_code == 409, blocked.text
    sheet = client.get(path + "/call-sheet", headers=auth["coach_a"]).json()
    assert sheet["week_plan"]["opponent_name"] == "Opponent"
    assert client.post(path + "/call-rules", headers=auth["coach_a"], json={
        "rule_type": "call", "situation": "test", "call_name": "test", "reason": "test",
    }).status_code == 409
    assert client.post(path + "/player-look-evidence", headers=auth["coach_a"], json={
        "player_id": str(ids["player_a"]), "source_type": "practice", "event_date": "2026-10-17", "processed_correctly": True,
    }).status_code == 409
    # The intentional post-freeze outcome workflow remains writable.
    assert client.post(path + "/changed-call", headers=auth["coach_a"], json={
        "changed_call": False, "change_type": "confirmed",
    }).status_code == 201

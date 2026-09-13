from pathlib import Path
from types import SimpleNamespace
import asyncio
import hashlib
import os
import secrets
import uuid

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.wedge import TelestrateBody, router

ROOT = Path(__file__).resolve().parents[1]


def pilot_client() -> TestClient:
    app = FastAPI()
    app.state.db = SimpleNamespace(pool=None)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/plays"),
        ("GET", "/api/v1/entities?kind=play&source=cfbd&external_id=1"),
        ("GET", "/api/v1/plays/00000000-0000-0000-0000-000000000001/ids"),
        ("GET", "/api/v1/plays/00000000-0000-0000-0000-000000000001/clip"),
        ("PUT", "/api/v1/plays/00000000-0000-0000-0000-000000000001/telestrate"),
        ("GET", "/api/v1/play-searches"),
        ("POST", "/api/v1/plays/bulk-tag-votes"),
    ],
)
def test_every_hub_route_rejects_missing_bearer(method, path):
    with pilot_client() as client:
        response = client.request(method, path, json={})
    assert response.status_code == 401
    assert response.json()["detail"] == "bearer_token_required"


def test_telestrate_accepts_only_normalized_coordinates():
    valid = TelestrateBody.model_validate(
        {"strokes": [{"color": "#ff0000", "width": 5, "points": [{"x": 0, "y": 1}]}]}
    )
    assert valid.strokes[0].points[0].x == 0
    with pytest.raises(ValidationError):
        TelestrateBody.model_validate(
            {"strokes": [{"color": "red", "width": 5, "points": [{"x": 1.01, "y": 0.5}]}]}
        )


def test_migration_keeps_global_and_tenant_identities_separate():
    sql = (ROOT / "db/migrations/007_hub_clip_ids.sql").read_text()
    assert "COALESCE(program_id" in sql
    assert "INSERT INTO entity_ids (program_id, kind" in sql
    assert "SELECT NULL, 'play'" in sql
    assert "ON CONFLICT DO NOTHING" in sql


def test_hub_does_not_restore_forbidden_surfaces_or_prompt_tagging():
    pilot = (ROOT / "app/pilot.py").read_text()
    html = (ROOT / "app/web/index.html").read_text()
    assert "LEGACY_PREFIX = \"/api/v1\"" in pilot
    assert "prompt(" not in html
    assert "Open in Hudl" in html
    assert "fm_finder_mode" in html


def test_source_class_filter_is_separate_from_trusted_family():
    wedge = (ROOT / "app/wedge.py").read_text()
    assert 'add("p.source_play_class", source_play_class)' in wedge
    assert 'add("COALESCE(pt.play_family,\'UNKNOWN\')", play_family)' in wedge
    assert "source_play_class and source IDs are public-PBP only" in wedge


def test_ingest_id_hooks_cannot_update_tenant_override():
    for script in ("ingest_cfbd.py", "ingest_nflverse.py"):
        source = (ROOT / "scripts" / script).read_text()
        assert "VALUES (NULL,$1,$2,$3,$4,$5)" in source
        assert "ON CONFLICT DO NOTHING" in source


def test_facets_are_computed_from_the_unpaginated_where_clause():
    source = (ROOT / "app/wedge.py").read_text()
    facet_query = 'GROUP BY {expr} ORDER BY n DESC,value'
    assert facet_query in source
    assert 'total = await conn.fetchval(f"SELECT COUNT(*) {base_from} {where}"' in source
    assert 'select_sql + f" LIMIT ${len(values)+1} OFFSET ${len(values)+2}"' in source


@pytest.mark.skipif(os.getenv("HUB_DB_TEST") != "1", reason="requires migrated PostgreSQL")
def test_database_tenancy_facets_bulk_resolution_and_identity_override():
    database_url = os.environ["DATABASE_URL"]
    ids = {name: uuid.uuid4() for name in ("program_a", "program_b", "user_a", "user_b", "user_ga2")}
    tokens = {name: secrets.token_urlsafe(32) for name in ("a", "b", "ga2")}

    async def setup():
        conn = await asyncpg.connect(database_url)
        try:
            play_id = await conn.fetchval(
                "SELECT id FROM plays WHERE external_source IN ('cfbd','nflverse') ORDER BY id LIMIT 1"
            )
            assert play_id is not None
            await conn.executemany(
                "INSERT INTO programs (id,name,level) VALUES ($1,$2,'college')",
                [(ids["program_a"], "Hub Test A"), (ids["program_b"], "Hub Test B")],
            )
            await conn.executemany(
                "INSERT INTO users (id,email) VALUES ($1,$2)",
                [(ids["user_a"], f"{ids['user_a']}@test.invalid"),
                 (ids["user_b"], f"{ids['user_b']}@test.invalid"),
                 (ids["user_ga2"], f"{ids['user_ga2']}@test.invalid")],
            )
            await conn.executemany(
                "INSERT INTO program_memberships (program_id,user_id,role) VALUES ($1,$2,$3)",
                [(ids["program_a"], ids["user_a"], "coach"),
                 (ids["program_b"], ids["user_b"], "coach"),
                 (ids["program_a"], ids["user_ga2"], "ga")],
            )
            await conn.executemany(
                "INSERT INTO auth_tokens (user_id,token_hash,expires_at) VALUES ($1,$2,now()+interval '1 hour')",
                [(ids["user_a"], hashlib.sha256(tokens["a"].encode()).hexdigest()),
                 (ids["user_b"], hashlib.sha256(tokens["b"].encode()).hexdigest()),
                 (ids["user_ga2"], hashlib.sha256(tokens["ga2"].encode()).hexdigest())],
            )
            await conn.execute(
                """INSERT INTO program_play_tags
                   (program_id,play_id,play_family,formation,motion,coverage_family,personnel)
                   VALUES ($1,$2,'COUNTER','3X1','JET','COVER_3','11')""",
                ids["program_b"], play_id,
            )
            await conn.execute(
                """INSERT INTO play_links (program_id,play_id,provider,url,created_by)
                   VALUES ($1,$2,'hudl','https://example.invalid/program-b',$3)""",
                ids["program_b"], play_id, ids["user_b"],
            )
            await conn.execute(
                """INSERT INTO play_telestrates (program_id,play_id,created_by,strokes)
                   VALUES ($1,$2,$3,'[{"color":"red","width":5,"points":[{"x":0.5,"y":0.5}]}]')""",
                ids["program_b"], play_id, ids["user_b"],
            )
            source_id = await conn.fetchval(
                "SELECT external_id FROM entity_ids WHERE kind='play' AND canonical_id=$1 AND program_id IS NULL LIMIT 1",
                play_id,
            )
            await conn.execute(
                """INSERT INTO entity_ids (program_id,kind,canonical_id,source,external_id,label)
                   VALUES ($1,'play',$2,'other',$3,'tenant override')""",
                ids["program_a"], play_id, f"override-{source_id}",
            )
            return play_id
        finally:
            await conn.close()

    async def cleanup():
        conn = await asyncpg.connect(database_url)
        try:
            await conn.execute("DELETE FROM programs WHERE id=ANY($1::uuid[])", [ids["program_a"], ids["program_b"]])
            await conn.execute("DELETE FROM users WHERE id=ANY($1::uuid[])", [ids["user_a"], ids["user_b"], ids["user_ga2"]])
        finally:
            await conn.close()

    play_id = asyncio.run(setup())
    try:
        from app.pilot import app
        with TestClient(app) as client:
            auth_a = {"Authorization": f"Bearer {tokens['a']}"}
            auth_ga2 = {"Authorization": f"Bearer {tokens['ga2']}"}
            listed = client.get("/api/v1/plays?limit=100", headers=auth_a)
            assert listed.status_code == 200
            body = listed.json()
            assert all(sum(item["n"] for item in body["facets"][facet]) == body["total"] for facet in body["facets"])
            row = next(item for item in body["plays"] if item["id"] == str(play_id))
            assert row["film_url"] is None
            assert row["play_family"] == "UNKNOWN"
            clip = client.get(f"/api/v1/plays/{play_id}/clip", headers=auth_a).json()
            assert clip["film_url"] is None and clip["other_staff_overlays"] == []

            first = client.post(
                "/api/v1/plays/bulk-tag-votes", headers=auth_a,
                json={"play_ids": [str(play_id)], "tags": {"formation": "2X2"}},
            )
            assert first.status_code == 201
            assert first.json()["plays"][0]["tags"]["formation"] == "UNKNOWN"
            second = client.post(
                "/api/v1/plays/bulk-tag-votes", headers=auth_ga2,
                json={"play_ids": [str(play_id)], "tags": {"formation": "2X2"}},
            )
            assert second.status_code == 201
            assert second.json()["plays"][0]["tags"]["formation"] == "2X2"

            source_filtered = client.get("/api/v1/plays?source_play_class=pass", headers=auth_a)
            assert source_filtered.status_code == 200
            assert all(p["play_family"] != "pass" for p in source_filtered.json()["plays"])
    finally:
        asyncio.run(cleanup())

"""Adversarial HTTP tests; database authorization is exercised separately in CI."""
import asyncio
import json
import subprocess
import sys
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.security import MAX_REQUEST_BODY_BYTES, SecurityHeadersMiddleware
from app.wedge import AuthContext, require_auth, router
from app.wedge_extra import router as extra_router

ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def api():
    app = FastAPI()
    app.state.db = SimpleNamespace(pool=None)
    app.include_router(router)
    app.include_router(extra_router)
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES)
    app.add_middleware(SecurityHeadersMiddleware)
    return app


def authenticate(app, role="coach"):
    app.dependency_overrides[require_auth] = lambda: AuthContext(
        user_id=uuid.UUID(ID), program_id=uuid.UUID(ID), email="staff@test.invalid",
        program_name="Test", role=role,
    )


def test_all_pilot_routes_require_bearer_before_database_access(api):
    with TestClient(api) as client:
        for route in [*router.routes, *extra_router.routes]:
            path = route.path
            for name in route.param_convertors:
                path = path.replace("{" + name + "}", ID)
            for method in route.methods:
                result = client.request(method, path, json={})
                assert result.status_code == 401, (method, path, result.text)


@pytest.mark.parametrize("token", ["short", "x" * 1025])
def test_invalid_token_length_rejected_without_database(api, token):
    with TestClient(api) as client:
        response = client.get("/api/v1/vocab", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/v1/play-searches", {"name": "test", "query": {}}),
    ("DELETE", f"/api/v1/play-searches/{ID}", None),
    ("POST", f"/api/v1/plays/{ID}/tag-votes", {"formation": "2X2"}),
    ("PUT", f"/api/v1/plays/{ID}/telestrate", {"strokes": []}),
    ("POST", f"/api/v1/plays/{ID}/link", {"url": "https://example.invalid/clip"}),
    ("POST", "/api/v1/entities", {"kind": "team", "canonical_id": ID, "source": "other", "external_id": "1"}),
    ("POST", f"/api/v1/week-plans/{ID}/freeze", None),
    ("POST", f"/api/v1/week-plans/{ID}/roster-players", {"name": "Test", "position": "QB"}),
])
def test_viewer_mutations_denied_before_database(api, method, path, body):
    authenticate(api, "viewer")
    with TestClient(api) as client:
        assert client.request(method, path, json=body).status_code == 403


@pytest.mark.parametrize("path,body", [
    ("/api/v1/play-searches", {"name": "test", "query": {}, "program_id": ID}),
    (f"/api/v1/plays/{ID}/tag-votes", {"formation": "2X2", "role": "owner"}),
    (f"/api/v1/week-plans/{ID}/roster-players", {"name": "Test", "position": "QB", "program_id": ID}),
    ("/api/v1/plays/bulk-tag-votes", {"play_ids": [ID], "tags": {"formation": "2X2", "resolved_by": ID}}),
])
def test_unknown_write_fields_are_rejected_including_nested_models(api, path, body):
    authenticate(api)
    with TestClient(api) as client:
        response = client.post(path, json=body)
    assert response.status_code == 422
    assert any(error["type"] == "extra_forbidden" for error in response.json()["detail"])


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,test", "http://example.invalid/film", "https://user:password@example.invalid/film"])
def test_unsafe_film_urls_cannot_be_stored(api, url):
    authenticate(api)
    with TestClient(api) as client:
        response = client.post(f"/api/v1/plays/{ID}/link", json={"url": url})
    assert response.status_code == 422


@pytest.mark.parametrize("declared_length", [None, "1"])
def test_chunked_or_underdeclared_bodies_are_bounded_before_handler_completes(declared_length):
    app = FastAPI()
    completed = []

    @app.post("/consume")
    async def consume(request: Request):
        await request.body()
        completed.append(True)
        return {"ok": True}

    wrapped = SecurityHeadersMiddleware(RequestBodyLimitMiddleware(app, max_body_size=1024))

    async def run():
        messages = iter([
            {"type": "http.request", "body": b"x" * 700, "more_body": True},
            {"type": "http.request", "body": b"x" * 700, "more_body": False},
        ])
        sent = []

        async def receive():
            return next(messages, {"type": "http.disconnect"})

        async def send(message):
            sent.append(message)

        headers = [] if declared_length is None else [(b"content-length", declared_length.encode())]
        scope = {"type": "http", "http_version": "1.1", "method": "POST", "path": "/consume",
                 "root_path": "", "query_string": b"", "headers": headers, "scheme": "http"}
        await wrapped(scope, receive, send)
        return sent

    response = asyncio.run(run())
    assert response[0]["status"] == 413
    assert dict(response[0]["headers"])[b"x-content-type-options"] == b"nosniff"
    assert completed == []


def test_declared_oversized_body_is_rejected(api):
    with TestClient(api) as client:
        result = client.post("/api/v1/play-searches", content=b"x" * (MAX_REQUEST_BODY_BYTES + 1))
    assert result.status_code == 413
    assert result.headers["cache-control"] == "no-store"


def test_production_entrypoint_headers_assets_and_fail_closed_health():
    # pilot imports intentionally remove legacy routes from app.main. Isolate it
    # so test collection order cannot change the legacy compatibility tests.
    code = '''
import os
os.environ.pop("DATABASE_URL", None)
from fastapi.testclient import TestClient
from app.pilot import app
@app.get("/_test_failure")
async def failure():
    raise RuntimeError("private-error-marker")
with TestClient(app, raise_server_exceptions=False) as client:
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    assert client.get("/docs").status_code == 404
    assert client.post("/api/v1/models/qb-college-to-nfl", json={}).status_code == 404
    for path in ["/", "/health", "/ready", "/missing", "/api/v1/vocab", "/_test_failure"]:
        result = client.get(path)
        assert result.headers["x-frame-options"] == "DENY"
        assert result.headers["cache-control"] == "no-store"
        assert "script-src 'self'" in result.headers["content-security-policy"]
        assert "strict-transport-security" not in result.headers
        assert "private-error-marker" not in result.text
    root = client.get("/")
    assert '<script src="/assets/pilot.js" defer>' in root.text
    assert "onclick=" not in root.text
    asset = client.get("/assets/pilot.js")
    assert asset.status_code == 200 and "javascript" in asset.headers["content-type"]
    assert "const actions =" in asset.text
    assert client.get("/health", headers={"X-Request-ID": "safe-123"}).headers["x-request-id"] == "safe-123"
    invalid = "bad id " * 100
    assert len(client.get("/health", headers={"X-Request-ID": invalid}).headers["x-request-id"]) == 36
    spoof = client.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert "strict-transport-security" not in spoof.headers
    cross = client.options("/api/v1/plays", headers={"Origin": "https://attacker.invalid", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"})
    assert "access-control-allow-origin" not in cross.headers
with TestClient(app, base_url="https://testserver") as client:
    assert client.get("/health").headers["strict-transport-security"] == "max-age=31536000"
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

import asyncio
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.lieutenant as lieutenant_module
from app.main import app
from scripts.ingest_movement import ingest_rows, load_rows

DB_CONTRACT = os.getenv("RUN_DB_CONTRACT") == "1"
PLAYER_DARIUS = "30000000-0000-0000-0000-000000000002"
PLAYER_JALEN = "30000000-0000-0000-0000-000000000001"
MOVEMENT_FIXTURE = Path("data/fixtures/movement_skillcorner_like.json")


def wait_ready(client: TestClient) -> None:
    for _ in range(40):
        if client.get("/ready").status_code == 200:
            return
        time.sleep(0.05)
    raise AssertionError("database did not become ready for contract test")


def test_health_is_db_independent(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"] == "fieldmind-api"


def test_ready_fails_closed_without_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"


def test_qb_translation_is_transparent_and_bounded(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/models/qb-college-to-nfl",
            json={
                "epa_per_dropback": 0.24,
                "pressure_success_rate": 0.48,
                "turnover_worthy_rate": 0.035,
                "processing_score": 74,
                "sample_dropbacks": 320,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert 0 <= body["translation_score"] <= 100
        assert body["model_status"] == "v1_heuristic_baseline_not_validated"
        assert body["confidence"] == "usable"


@pytest.mark.skipif(not DB_CONTRACT, reason="requires migrated CI Postgres")
def test_lieutenant_insufficient_evidence_when_n_low(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as client:
        wait_ready(client)
        response = client.post(
            "/lieutenant/ask",
            json={
                "question": "What does the play evidence say about his processing?",
                "player_id": PLAYER_DARIUS,
                "min_n": 20,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "insufficient_evidence"
        assert body["evidence"]["n"] == 10
        assert len(body["evidence"]["play_ids"]) == 10
        assert body["decision"].startswith("No grade")


@pytest.mark.skipif(not DB_CONTRACT, reason="requires migrated CI Postgres")
def test_lieutenant_not_configured_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as client:
        wait_ready(client)
        response = client.post(
            "/lieutenant/ask",
            json={
                "question": "What does the play evidence say about his decisions?",
                "player_id": PLAYER_DARIUS,
                "min_n": 8,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "not_configured"
        assert body["evidence"]["n"] == 10
        assert body["evidence"]["play_ids"]


@pytest.mark.skipif(not DB_CONTRACT, reason="requires migrated CI Postgres")
def test_lieutenant_ok_uses_mocked_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-live")

    async def fake_call(question, evidence, api_key):
        assert api_key == "test-key-not-live"
        assert evidence["plays"]
        return {
            "finding": "Decision evidence is mostly stable in this sample.",
            "confidence": "med",
            "decision": "Keep the player in the evidence review set; do not promote this to a draft grade.",
            "falsifier": "A larger sample showing late or incorrect decisions would reverse the finding.",
            "dissent": "The favorite take overstates processing because movement and diagnosis are separate evidence.",
        }

    monkeypatch.setattr(lieutenant_module, "call_claude", fake_call)
    with TestClient(app) as client:
        wait_ready(client)
        response = client.post(
            "/lieutenant/ask",
            json={
                "question": "What does the play evidence say about his decisions?",
                "player_id": PLAYER_DARIUS,
                "min_n": 8,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["confidence"] == "med"
        assert body["evidence"]["n"] == 10
        assert body["dissent"]


class MovementMemoryConnection:
    def __init__(self):
        self.rows = {}

    async def execute(self, sql, *args):
        identity = (str(args[0]), str(args[1]), str(args[2]))
        self.rows[identity] = args[3:]
        return "INSERT 0 1"


def test_movement_ingest_is_idempotent():
    rows = load_rows(MOVEMENT_FIXTURE)
    conn = MovementMemoryConnection()
    first = asyncio.run(ingest_rows(conn, rows))
    second = asyncio.run(ingest_rows(conn, rows))
    assert first == {"ingested": 10, "skipped": 0, "errors": 0}
    assert second == {"ingested": 10, "skipped": 0, "errors": 0}
    assert len(conn.rows) == 10


@pytest.mark.skipif(not DB_CONTRACT, reason="requires migrated CI Postgres")
def test_radar_hidden_returns_fixture_players():
    with TestClient(app) as client:
        wait_ready(client)
        response = client.get("/radar/hidden?min_speed_pct=75")
        assert response.status_code == 200
        body = response.json()
        player_ids = {row["player_id"] for row in body["players"]}
        assert PLAYER_DARIUS in player_ids
        assert PLAYER_JALEN in player_ids
        assert all("movement_summary" in row for row in body["players"])
        assert all("sample_size_flag" in row for row in body["players"])


def test_ask_combine_rejects_non_combine_question(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        response = client.post(
            "/ask/combine",
            json={"question": "Who had the best processing on film?"},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "question_not_about_combine_results"


def test_combine_parser_uses_allowlisted_filters_only():
    parsed = lieutenant_module.parse_combine_question(
        "Show 2026 combine 40-yard dash results under 4.50"
    )
    assert parsed == {
        "event": "40_yard_dash",
        "year": 2026,
        "comparator": "lt",
        "value": 4.5,
    }

from fastapi.testclient import TestClient

from app.main import app


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
                "sample_dropbacks": 320
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert 0 <= body["translation_score"] <= 100
        assert body["model_status"] == "v1_heuristic_baseline_not_validated"
        assert body["confidence"] == "usable"

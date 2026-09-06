# FIELDMIND

FIELDMIND is a football decision system built around one atomic unit: the play. V1 joins opponent/self-scout evidence, player production, scheme-specific cognition evidence, and weekly call rules without trying to replace film capture or create a universal player IQ score.

## V1 included

- Play database with indexed situation filters
- Clip pointer attachment for S3-compatible storage
- Opponent tendency report with minimum-sample guards
- Self-scout explosive/failure report
- Player card with five film-derived cognition traits
- Weekly one-page call-sheet endpoint
- Transparent QB college-to-NFL heuristic baseline
- Railway-safe `/health` and `/ready`
- Structured JSON logging, bounded Postgres pool, reconnect backoff, graceful shutdown
- 20-play fictional seed game

## Stack

- FastAPI / Python 3.12
- Railway Postgres via asyncpg
- S3-compatible object storage for clip bytes
- Docker / Uvicorn

FastAPI was chosen over Next.js for V1 because the core product is data, filtering, football analytics, and Python-native model work. A separate web UI can be added after the decision APIs are stable.

## Local start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
PORT=8000 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Liveness:

```bash
curl http://127.0.0.1:8000/health
```

Expected: HTTP 200 with `{"status":"ok",...}`. This route never depends on Postgres.

Readiness:

```bash
curl -i http://127.0.0.1:8000/ready
```

Without `DATABASE_URL`, HTTP 503 is correct. With a working database, readiness returns 200.

## Database seed

```bash
export DATABASE_URL='postgresql://...'
python scripts/seed.py
```

The seed creates the V1 schema and loads the fictional 20-play demo game in `data/seed_plays.json`.

## Primary API paths

- `GET /health`
- `GET /ready`
- `GET /api/v1/plays`
- `POST /api/v1/plays/{play_id}/clip`
- `POST /api/v1/reports/opponent`
- `GET /api/v1/reports/self-scout`
- `GET /api/v1/players/{player_id}`
- `GET /api/v1/weekly/call-sheet`
- `POST /api/v1/models/qb-college-to-nfl`

OpenAPI is available at `/docs` when the service is running.

## Railway start command

Docker image default:

```bash
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --timeout-keep-alive 5
```

If Railway requires an explicit Docker start override:

```bash
/bin/sh -c "exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 5"
```

`railway.json` is included because it was part of the requested deployment pack. Railway deprecated Config-as-Code in 2026, so new services should mirror those settings in current Railway Infrastructure-as-Code/service settings rather than depend on `railway.json` long-term.

## Product and operating spec

See `docs/PRODUCT_SPEC.md` for the architecture, cognition graph, week-of-game workflow, API contract, example outputs, 12-week plan, competitive kill-sheet, failure risks, and Railway prevention runbook.

## Non-negotiable cognition guardrails

FIELDMIND cognition traits are football-performance evidence. They are not IQ, diagnosis, mental-health assessment, or medical evaluation. Scores must display sample size and confidence and cannot be used as a standalone cut, scholarship, contract, or draft decision.

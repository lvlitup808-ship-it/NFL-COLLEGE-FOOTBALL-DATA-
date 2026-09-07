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

## V1.1 production-data layer

- Checksum-protected, advisory-locked Postgres migrations
- Source provenance on games and plays
- Streaming nflverse NFL play-by-play adapter; seasons are never materialized fully in RAM
- Idempotent deterministic IDs for safe reruns
- Ingest-run audit records with inserted/updated/skipped/error counts
- V1 query benchmark harness with the product latency thresholds
- CI Postgres integration gate covering migration, seed, benchmark, Docker build and health smoke tests

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

## Database lifecycle

Set the database connection once:

```bash
export DATABASE_URL='postgresql://...'
```

Apply schema changes before ingesting data:

```bash
python scripts/migrate.py
```

The migrator uses a Postgres advisory lock so two deploy processes cannot apply migrations concurrently. Applied SQL files are checksum-protected; never edit an applied migration. Add a new migration instead.

Load the fictional 20-play development game:

```bash
python scripts/seed.py
```

## Real NFL data ingest

FIELDMIND can stream the public nflverse play-by-play CSV release directly into Postgres:

```bash
python scripts/ingest_nflverse.py --season 2025
```

Use a bounded test ingest first:

```bash
python scripts/ingest_nflverse.py --season 2025 --max-rows 5000
```

Or normalize a local CSV fixture:

```bash
python scripts/ingest_nflverse.py --season 2025 --url ./play_by_play_2025.csv
```

The adapter only maps evidence present in play-by-play. Coverage, motion, route concepts and other film-only facts are not inferred when the source does not support them. nflverse play-by-play is maintained by the nflverse project and distributed under its stated licensing terms; preserve attribution when using their data.

## Performance gate

Run the same decision-query thresholds used by the product requirements:

```bash
python scripts/benchmark.py --iterations 25 --warmup 3
```

The benchmark records p50, p95 and max latency in `benchmark_runs` and exits non-zero if the p95 threshold fails:

- Play Finder, 20 plays: `< 2000 ms`
- Opponent report: `< 5000 ms`
- Self-scout: `< 5000 ms`

Run this after each production season ingest and after index/query changes.

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

Run `python scripts/migrate.py` as an explicit deploy/one-off operation. Do not put season ingestion in the web-service startup command. Startup must remain fast and independent of data imports.

`railway.json` is included because it was part of the requested deployment pack. Railway deprecated Config-as-Code in 2026, so new services should mirror those settings in current Railway Infrastructure-as-Code/service settings rather than depend on `railway.json` long-term.

## Product and operating specs

- `docs/PRODUCT_SPEC.md`: architecture, cognition graph, week-of-game workflow, API contract, examples, 12-week plan, competitive kill-sheet, risks and Railway runbook.
- `docs/PRODUCTION_DATA.md`: production database, ingest, provenance, benchmark and rollback procedure.

## Non-negotiable cognition guardrails

FIELDMIND cognition traits are football-performance evidence. They are not IQ, diagnosis, mental-health assessment, or medical evaluation. Scores must display sample size and confidence and cannot be used as a standalone cut, scholarship, contract, or draft decision.

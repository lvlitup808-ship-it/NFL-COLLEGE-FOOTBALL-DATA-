# FIELDMIND

FIELDMIND is a week-of-game football decision system built around one atomic unit: the play. The locked pilot turns trusted staff film tags and play evidence into a Thursday call/do-not-call sheet with visible sample size, confidence, supporting plays, and raw evidence of which players have processed the relevant look.

FIELDMIND is not a film-capture competitor, sports-data API company, public CFBD/nflverse explorer, PFF-style grading product, S2-style lab test, live play-caller, betting engine, or draft oracle.

## Locked pilot

Production entrypoint: `app.pilot:app`.

The pilot includes:

- Opaque bearer-token auth and `program_id` tenancy
- Program-scoped film tag votes and coach resolution
- Controlled vocabulary capped at 40 values across play family, formation, motion, coverage family, and personnel
- Two-tagger agreement reporting with an 80% calibration rule
- Play Finder
- Opponent One-Pager with explicit n/confidence states
- Self-Scout
- CALL / DO NOT CALL / IF-THEN decision objects
- Raw player-look evidence; no cognition score UI
- Thursday call-sheet freeze
- Weekly `changed a call` logging
- Customer-authorized Hudl/reference links only; no film scraping or mirror
- Railway-safe `/health` and `/ready`

The complete product contract, controlled vocabulary, pilot script, 90-day build order, risk register, customer interview, and operating runbook are in `docs/WEEKLY_WEDGE_EXECUTION.md`.

## Stack

- FastAPI / Python 3.12
- Railway Postgres via asyncpg
- Docker / Uvicorn
- Plain same-origin pilot web UI; no frontend framework required for the wedge

## Local start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q

export DATABASE_URL='postgresql://...'
python scripts/migrate.py

PORT=8000 uvicorn app.pilot:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000/` for the four pilot screens.

Liveness:

```bash
curl http://127.0.0.1:8000/health
```

`/health` intentionally has no database or external-service dependency.

Readiness:

```bash
curl -i http://127.0.0.1:8000/ready
```

Without `DATABASE_URL`, HTTP 503 is correct. With a working database, readiness returns 200.

## Provision a pilot program/user

After migrations:

```bash
python scripts/provision_pilot_user.py \
  --program-name 'Example University Football' \
  --email 'coach@example.edu' \
  --display-name 'Coach Example' \
  --role owner \
  --days 30
```

The script prints the bearer token once. Only the SHA-256 token hash is stored. Do not commit tokens, place them in URLs, or log them.

Add additional users to the same program with the returned program UUID:

```bash
python scripts/provision_pilot_user.py \
  --program-id '<program-uuid>' \
  --email 'ga@example.edu' \
  --display-name 'GA Example' \
  --role ga \
  --days 30
```

## Database lifecycle

Run migrations explicitly:

```bash
python scripts/migrate.py
```

The migrator uses a Postgres advisory lock and checksum-protects applied SQL. Never edit an applied migration; add a new migration instead.

Migration `003_weekly_wedge.sql` adds pilot tenancy, trusted tag writes, week plans, raw player-look evidence, changed-call logs, and source-PBP guardrails. Migration `004_decision_guard.sql` prevents a CALL/DO NOT CALL rule from becoming approved below the minimum evidence guard.

## Source evidence boundary

CFBD/nflverse ingestion remains an explicit one-off job. It never runs on web startup, `/health`, `/ready`, or normal request paths.

For `cfbd` and `nflverse` rows, the database enforces the locked honesty rule:

- pass/run source classification is preserved as `plays.source_play_class`
- canonical `play_family` is `UNKNOWN`
- formation is `UNKNOWN`
- personnel is `UNKNOWN`
- motion is null
- concept is null
- coverage is null

Those football fields become trusted only through program-scoped human tagging. Do not infer them from PBP text or source heuristics.

Do not redistribute raw CFBD/nflverse feeds. Publishing or selling source data rather than private derived staff decisions requires a fresh rights/terms review.

## College data ingest

Set the server-side credential only in the environment:

```bash
export CFBD_API_KEY='...'
```

Ingest one week:

```bash
python scripts/ingest_cfbd.py --season 2026 --week 1
```

Ingest a bounded range:

```bash
python scripts/ingest_cfbd.py --season 2026 --start-week 1 --end-week 4
```

The CLI requests one week at a time and does not make CFBD availability part of API liveness.

## Existing production-data layer

The repo still contains the earlier production-data foundation:

- source provenance on games and plays
- streaming nflverse adapter
- idempotent deterministic IDs for reruns
- ingest-run audit records
- benchmark harness
- 20-play fictional seed
- structured logging, bounded Postgres pool, reconnect backoff, graceful shutdown

`app/main.py` remains the legacy V1 implementation/reference. The 90-day pilot runs `app.pilot:app`, which removes the legacy global `/api/v1` surfaces before registering the authenticated pilot API. That keeps the QB translation heuristic and cognition-score API out of the pilot without rewriting the stable DB lifecycle and health code.

## Pilot API

- `GET /health`
- `GET /ready`
- `GET /api/v1/me`
- `GET /api/v1/vocab`
- `GET /api/v1/plays`
- `POST /api/v1/plays/{play_id}/tag-votes`
- `POST /api/v1/plays/{play_id}/tag-resolve`
- `GET /api/v1/tag-agreement`
- `POST /api/v1/plays/{play_id}/links`
- `POST /api/v1/week-plans`
- `GET /api/v1/week-plans/{id}/opponent`
- `GET /api/v1/week-plans/{id}/self-scout`
- `POST /api/v1/week-plans/{id}/call-rules`
- `PATCH /api/v1/week-plans/{id}/call-rules/{rule_id}`
- `POST /api/v1/week-plans/{id}/player-look-evidence`
- `POST /api/v1/week-plans/{id}/freeze`
- `GET /api/v1/week-plans/{id}/call-sheet`
- `POST /api/v1/week-plans/{id}/changed-call`

OpenAPI/docs are hidden by default in pilot production. Set `PILOT_HIDE_DOCS=0` only for controlled development.

## Railway

Docker and `railway.json` now start:

```bash
exec uvicorn app.pilot:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --timeout-keep-alive 5
```

Run `python scripts/migrate.py` as a deploy/one-off operation. Never add season ingestion to the web start command.

## Product and operating specs

- `docs/WEEKLY_WEDGE_EXECUTION.md`: locked commercial/product/football execution contract for the pilot
- `docs/PRODUCT_SPEC.md`: earlier V1 architecture and system spec; sections outside the locked pilot are not the current 90-day build order
- `docs/COLLEGE_DATA.md`: CFBD ingestion and source-evidence rules
- `docs/PRODUCTION_DATA.md`: production database, ingest, provenance, benchmark and rollback procedure

## Player-evidence guardrail

FIELDMIND player evidence is football-performance evidence only. It is not IQ, diagnosis, mental-health assessment, neurological/medical evaluation, or a measure of overall intelligence or potential. It cannot be used as a standalone cut, scholarship, roster, contract, recruiting, NIL, transfer, or draft decision. Every interpretation must retain sample size, evidence count, look diversity, source, and as-of date.

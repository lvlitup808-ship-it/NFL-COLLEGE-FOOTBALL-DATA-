# FIELDMIND Production Data Runbook

## Objective

Production data must be traceable, rerunnable, bounded in memory, and measurable against the V1 latency requirements. Ingestion is a data operation, never part of web-service startup.

## Database lifecycle

1. Provision Postgres.
2. Set `DATABASE_URL`.
3. Run `python scripts/migrate.py`.
4. Verify the migrator returns `{"status":"ok"...}`.
5. Start the API.
6. Verify `/health` returns 200 independently of Postgres.
7. Verify `/ready` returns 200 only when Postgres is reachable.

The migration runner takes a Postgres advisory lock before applying changes. Every migration filename and SHA-256 checksum is persisted in `schema_migrations`. Applied migrations are immutable. To change schema, add a new migration.

## Ingestion contract

Every external game/play receives:

- `external_source`
- `external_id`
- deterministic internal UUID

Deterministic IDs make retries idempotent. `ingest_runs` records source URI, season, counts, state, and timestamps.

The web API must never download or parse season files during startup. Large source files are streamed row by row and written in bounded batches.

## NFL source: nflverse

Default source URL pattern:

`https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_<SEASON>.csv`

Dry operational sequence:

```bash
python scripts/migrate.py
python scripts/ingest_nflverse.py --season 2025 --max-rows 5000
python scripts/benchmark.py --iterations 25 --warmup 3
```

Full ingest:

```bash
python scripts/ingest_nflverse.py --season 2025
```

The adapter accepts `pass` and `run` scrimmage plays with valid game, team, quarter, down, distance, and field-position context. Non-scrimmage rows are skipped for the V1 tendency engine.

Derived fields:

- distance: short `<=3`, medium `4-6`, long `>=7`
- backed up: offense is 80-100 yards from goal
- red zone: 0-20 yards from goal
- plus territory: 21-50 yards from goal
- open field: 51-79 yards from goal
- explosive pass: gain `>=20`
- explosive run: gain `>=10`

These are V1 operational defaults, not universal football laws. Team-specific definitions can replace them later without changing source provenance.

The adapter does not fabricate film-only evidence. Coverage, motion, true pressure assignment, route concept, communication, and cognition events remain absent unless another trusted source provides them.

## Attribution

nflverse is an external project. Preserve the attribution and licensing obligations stated by the upstream project when distributing or publishing data derived from it. Re-check upstream terms before commercial redistribution.

## Benchmark gate

Run after:

- full-season ingest
- index change
- query change
- Postgres plan/tier change
- major schema migration

Command:

```bash
python scripts/benchmark.py --iterations 25 --warmup 3
```

Pass/fail thresholds:

- `play_filter_20`: p95 under 2000 ms
- `opponent_report`: p95 under 5000 ms
- `self_scout`: p95 under 5000 ms

Every run is stored in `benchmark_runs`. A failed benchmark exits non-zero and blocks promotion until investigated.

## Railway deployment sequence

Root Cause: A web service that performs migrations or season ingestion on startup can miss Railway health windows, hold locks, exhaust memory, or fail because an external source is unavailable.

Changes Made: Migrations and ingestion are explicit one-off operations. The web service only starts Uvicorn, binds `0.0.0.0:$PORT`, and maintains a bounded Postgres pool. `/health` has no database dependency; `/ready` checks database availability.

Verification:

```bash
python scripts/migrate.py
python scripts/benchmark.py --iterations 25 --warmup 3
curl -fsS https://<service>/health
curl -fsS https://<service>/ready
```

Expected:

- migration status `ok`
- benchmark status `pass`
- `/health` HTTP 200
- `/ready` HTTP 200 after database connectivity is established

Prevention:

- never add ingestion to the Docker CMD
- never edit an applied migration
- keep DB pool bounded
- run production-scale benchmark after each season ingest
- do not store film bytes in Postgres
- keep clip bytes in object storage
- keep source-of-truth data off ephemeral disk
- review failed `ingest_runs` before rerunning
- review p95 trend in `benchmark_runs`
- treat a 30-day soak as unproven until 30 real days have elapsed

## Rollback

Application rollback and schema rollback are separate decisions.

Preferred sequence:

1. Roll the application back to the prior known-good image/commit.
2. Do not automatically reverse a migration.
3. If the migration was additive, leave new columns/tables in place unless they cause an actual issue.
4. For destructive schema changes, require an explicit forward-fix or separately reviewed down migration.
5. Confirm `/health`, `/ready`, and core decision queries after rollback.

Automatic destructive down-migrations are intentionally not supported in V1.1.

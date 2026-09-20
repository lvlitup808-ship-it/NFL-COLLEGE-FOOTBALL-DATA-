# Railway Pilot Deployment

How the FIELDMIND pilot runs on Railway. Every claim below carries its source.
Steps that need a human click in the Railway dashboard are marked **ASK** — an
agent does not click them.

NOT IN THE EVIDENCE: a deployed Railway URL. No service has been observed
running. This document describes how the repository is built to deploy, not a
deployment that happened. [Source: `docs/SHIP_TONIGHT.md` line 3]

## Service shape

One service. Docker build, uvicorn process, no separate frontend.

- Builder is the repository `Dockerfile`, declared in `railway.json`:
  `"builder": "DOCKERFILE"`, `"dockerfilePath": "Dockerfile"`.
  [Source: `railway.json` lines 4-5]
- Base image `python:3.12-slim`; dependencies install from the pinned
  `requirements.lock`, not the ranges in `requirements.txt`, so the deploy
  installs the versions CI tested.
  [Source: `Dockerfile` lines 1, 9-10]
- The container runs as a non-root user.
  [Source: `Dockerfile` line 16]
- Entrypoint is `app.pilot:app`. The `startCommand` in `railway.json`
  **overrides** the Dockerfile `CMD`, so it is the line that actually runs:

```
"startCommand": "/bin/sh -c \"exec uvicorn app.pilot:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --timeout-keep-alive 5\""
```

  [Source: `railway.json` line 8]

  `${PORT:-8000}` and `${WEB_CONCURRENCY:-1}` carry defaults on purpose. Without
  them, an absent `PORT` makes uvicorn read the next argument as the port value
  and exit before serving, which restart-loops until
  `restartPolicyMaxRetries` is spent with nothing in the application log to
  explain it. [Source: `railway.json` lines 8, 12]

  `exec` matters too: it replaces the shell, so uvicorn is PID 1 and receives
  Railway's SIGTERM directly, letting the lifespan shutdown close the database
  pool within `drainingSeconds`. [Source: `railway.json` lines 8, 14;
  `app/main.py` lines 158-171]

**The start command never runs a migration, a seed, or an ingest.** Ingestion is
a one-off job, not part of web start. [Source: `app/pilot.py` lines 3-5]

## Database

Add the Railway Postgres plugin and let it supply `DATABASE_URL` to the web
service as a reference variable. Nothing in this repository creates a database.

- `DATABASE_URL` is read at startup by the application and by every one-off
  script; the scripts exit immediately when it is unset.
  [Source: `app/main.py` line 61; `scripts/migrate.py` lines 20-22;
  `scripts/seed.py` lines 20-22]
- The connection pool is maintained out of band with backoff, so a database
  that is briefly unavailable does not kill the web process.
  [Source: `app/main.py` lines 107-129]

**ASK — provisioning the Postgres plugin and binding `DATABASE_URL` to the web
service are dashboard actions.** An agent drafts them; a human clicks them.

## Health and readiness

Point the Railway healthcheck at `/health`. It is already set:

```
"healthcheckPath": "/health"
```

[Source: `railway.json` line 9]

The split is deliberate:

| Path | Depends on the database | Meaning |
| --- | --- | --- |
| `/health` | No | The process is alive. Railway liveness. |
| `/ready` | Yes | The pool is connected and answers `SELECT 1`. |

- `/health` returns `status`, `service` and `uptime_ms` and touches nothing
  external. [Source: `app/main.py` lines 220-227]
- `/ready` returns `503` with `{"status":"not_ready","database":"disconnected"}`
  when the pool is absent. [Source: `app/main.py` lines 230-234]

Never point the Railway healthcheck at `/ready`: a database blip would then
restart a web process that is otherwise healthy.

## One-off order

Run these as one-off commands against the deployed service, in this order,
after the first successful build and after `DATABASE_URL` is bound.

1. **Migrate.** Applies `db/migrations/` in order and prints the latest applied
   file. Safe to re-run. [Source: `scripts/migrate.py`]

   ```
   python scripts/migrate.py
   ```

2. **Then either seed or ingest — not both, and never both into the same
   pilot database.**

   *Seed* loads the repository's 20 fictional demo plays. Use it for a
   rehearsal, never for a real program. [Source: `scripts/seed.py`;
   `data/seed_plays.json`]

   ```
   python scripts/seed.py
   ```

   *Ingest* loads public play-by-play. Both adapters are idempotent: a second
   run inserts nothing and updates in place.
   [Source: `scripts/ingest_nflverse.py`; `scripts/ingest_cfbd.py`]

   ```
   python scripts/ingest_nflverse.py --season <year> --url <nflverse-url>
   python scripts/ingest_cfbd.py --season <year> --week <n>
   ```

   Ingested play-by-play arrives as source rows and stays that way. A database
   trigger forces `play_family`, `personnel_offense` and `formation` to
   `UNKNOWN` and clears `motion`, `concept` and `coverage` for any row whose
   `external_source` is `cfbd` or `nflverse`, moving `pass`/`run` to
   `source_play_class` instead. Public data cannot become a tendency.
   [Source: `db/migrations/003_weekly_wedge.sql` lines 21-42]

3. **Provision four seats.** One owner, one coach, two GAs — the two-GA rule
   needs two distinct tagger accounts in the same program. The first command
   creates the program and prints its `program_id`; pass that id to the other
   three. Roles are `owner`, `coach`, `ga`, `viewer`.
   [Source: `scripts/provision_pilot_user.py` line 11]

   ```
   python scripts/provision_pilot_user.py --program-name '<Program>' \
     --email '<owner@…>' --display-name '<Owner>' --role owner --days 30
   # then, with the printed program_id:
   python scripts/provision_pilot_user.py --program-id '<program_id>' \
     --email '<coach@…>' --display-name '<Coach>' --role coach --days 30
   python scripts/provision_pilot_user.py --program-id '<program_id>' \
     --email '<ga-a@…>' --display-name '<GA A>' --role ga --days 30
   python scripts/provision_pilot_user.py --program-id '<program_id>' \
     --email '<ga-b@…>' --display-name '<GA B>' --role ga --days 30
   ```

**ASK — running a one-off command against a Railway service is a dashboard or
CLI action.** An agent supplies the exact command; a human runs it.

## Environment variables

| Variable | Required | Where it is used |
| --- | --- | --- |
| `DATABASE_URL` | Yes | App and every one-off script |
| `PORT` | No | Injected by Railway; the start command defaults to 8000 |
| `WEB_CONCURRENCY` | No | Worker count; defaults to 1 |
| `PILOT_HIDE_DOCS` | No | Defaults to `1`, which hides `/docs`, `/redoc` and `/openapi.json` |
| `CFBD_API_KEY` | No | **Ingest only.** See below. |
| `DB_POOL_MAX`, `DB_CONNECT_TIMEOUT_SECONDS`, `LOG_LEVEL` | No | Pool and logging tuning |

[Source: `app/main.py` lines 42, 61, 66-67; `app/pilot.py` line 25;
`railway.json` line 8; `.env.example`]

Leave `PILOT_HIDE_DOCS` unset during the pilot. The OpenAPI surface is hidden
unless it is explicitly set to `0`. [Source: `app/pilot.py` lines 23-28]

### CFBD_API_KEY

Optional, and only for live CFBD ingestion. It is read by the ingest script and
the CFBD adapter, and by nothing else.
[Source: `scripts/ingest_cfbd.py` lines 216-220; `app/ingest/cfbd.py` line 152]

**Do not put `CFBD_API_KEY` in the start command, and do not make the web
service depend on it.** The web process never reads it; adding it to the boot
path couples serving to a third-party credential for no benefit. Set it only on
the one-off ingest invocation, and only when ingesting live rather than from a
fixture.

## Tokens and secrets stay off the repository

Bearer tokens are printed exactly once by the provisioning script and are never
stored in readable form — the database keeps a SHA-256 hash.
[Source: `scripts/provision_pilot_user.py` lines 84-85]

- Never commit a token. `.env` is ignored by git and excluded from the Docker
  build context, so a local secrets file cannot reach an image layer.
  [Source: `.gitignore` line 5; `.dockerignore` lines 2-3]
- Keep seat tokens in whatever the program already uses for shared secrets. The
  repository carries only an example shape.
  [Source: `docs/PILOT_CREDS.example.md`]
- To rotate, re-run provisioning with `--revoke-existing`.
  [Source: `scripts/provision_pilot_user.py`]

## SKIP VERCEL

Do not add Vercel. The UI is served by FastAPI at `/`; there is no separate
frontend to deploy. [Source: `docs/SHIP_TONIGHT.md` lines 87-89]

The application is a long-running container holding a persistent Postgres pool
with a background maintainer task. That shape does not survive a serverless
function boundary, and splitting the single static UI file across a second host
would add a cross-origin surface for one page.
[Source: `app/main.py` lines 57-129; `app/pilot.py` lines 34-40]

## Related

- Local demo path, including Docker Compose: `docs/SHIP_TONIGHT.md`
- Rehearsal script for the four seats: `docs/PILOT_REHEARSAL_CHECKLIST.md`
- Week-of-game contract: `docs/WEEKLY_WEDGE_EXECUTION.md`
- Ingest detail: `docs/PRODUCTION_DATA.md`, `docs/COLLEGE_DATA.md`

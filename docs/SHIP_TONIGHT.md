# Ship Tonight

This is the smallest evidenced demo path: local Docker Compose. A deployed Railway URL is NOT IN THE EVIDENCE.

## Environment

- `DATABASE_URL` — required by migration, seed, provisioning, and the application. Compose supplies the local container value; Railway must supply its Postgres value. [Source: `scripts/migrate.py`; `scripts/seed.py`; `scripts/provision_pilot_user.py`; `app/main.py`]
- `FIELDMIND_TOKEN` — secret bearer token printed once by provisioning and used by the browser or measurement script. Never commit it. [Source: `scripts/provision_pilot_user.py`; `app/wedge.py`]
- `CFBD_API_KEY` — optional for this seeded demo; required only for live CFBD ingestion. [Source: `scripts/ingest_cfbd.py`; `docs/COLLEGE_DATA.md`]

## Exact local commands

Start Postgres:

```bash
docker compose up -d db
```

Apply migrations and load the repository's fictional 20-play seed:

```bash
docker compose run --rm web python scripts/migrate.py
docker compose run --rm web python scripts/seed.py
```

Create the four token-bearing seats. The first command prints the `program_id`; copy it into the export before running the next three commands. Tokens are printed once and must remain outside Git.

```bash
docker compose run --rm web python scripts/provision_pilot_user.py \
  --program-name 'Demo Football Program' \
  --email 'owner@example.invalid' \
  --display-name 'Demo Owner' \
  --role owner \
  --days 7

export FIELDMIND_PROGRAM_ID='<program-uuid-printed-above>'

docker compose run --rm web python scripts/provision_pilot_user.py \
  --program-id "$FIELDMIND_PROGRAM_ID" \
  --email 'coach@example.invalid' \
  --display-name 'Demo Coach' \
  --role coach \
  --days 7

docker compose run --rm web python scripts/provision_pilot_user.py \
  --program-id "$FIELDMIND_PROGRAM_ID" \
  --email 'ga-a@example.invalid' \
  --display-name 'Demo GA A' \
  --role ga \
  --days 7

docker compose run --rm web python scripts/provision_pilot_user.py \
  --program-id "$FIELDMIND_PROGRAM_ID" \
  --email 'ga-b@example.invalid' \
  --display-name 'Demo GA B' \
  --role ga \
  --days 7
```

Start the pilot and open its four-screen UI:

```bash
docker compose up --build -d web
python -m webbrowser http://127.0.0.1:8000/
```

In the UI:

1. Paste the owner's printed token into `Pilot bearer token` and click `Use session`.
2. In Play Finder, clear `Tag state` if needed and click `Find plays`; the seed contains 20 fictional plays. [Source: `data/seed_plays.json`; `app/web/index.html`]
3. Open one play, choose the five controlled tag values, and click `Vote`.
4. Reopen the play and use the authorized film URL field. The UI provides an `Open in Hudl` fallback; Hudl embedding is not claimed. [Source: `app/web/index.html`; `docs/WEEKLY_WEDGE_EXECUTION.md` §6]

Check authenticated Play Finder latency after exporting one printed token:

```bash
export FIELDMIND_TOKEN='<owner-token-printed-once>'
python scripts/measure_pilot.py --base-url http://127.0.0.1:8000
```

Stop the local services:

```bash
docker compose down
```

SKIP VERCEL.

The UI is served by FastAPI at `/`; no separate frontend deployment is required. [Source: `app/pilot.py`]

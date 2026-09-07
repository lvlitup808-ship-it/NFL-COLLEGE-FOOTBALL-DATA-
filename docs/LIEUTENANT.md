# FIELDMIND Lieutenant v1.5

FIELDMIND Lieutenant is a thin evidence evaluator on top of FIELDMIND's first-party plays, movement events, cognition traits, player metadata, and combine results. It accepts vendor-shaped movement/XY-derived summaries; it does not run computer vision or train tracking models inside this repo.

The north-star rule is structural: every lieutenant evaluation resolves to play IDs. If the matching play sample is below the requested minimum, or an athleticism question has no movement evidence, the endpoint returns `insufficient_evidence` and does not call Claude.

## What this is not

- Not SkillCorner and not a replacement for a tracking vendor.
- Not Hawk-Eye or an optical tracking system.
- Not Teamworks or PFF.
- Not an in-house computer-vision training stack.
- Not a validated draft or college-to-NFL prediction model.
- Not a Football IQ, Wonderlic, medical, psychiatric, or diagnostic score.
- Not proof of season-scale latency or a zero-crash production soak.

Movement and processing are separate evidence classes. Fast movement does not imply fast diagnosis or decision-making.

## Environment

Required for database-backed endpoints:

```bash
DATABASE_URL=postgresql://...
PORT=8000
```

Required only when `/lieutenant/ask` has enough evidence to invoke Claude:

```bash
ANTHROPIC_API_KEY=...
```

The API key stays server-side and is never included in application logs. If it is missing, `/lieutenant/ask` returns HTTP 200 with `status: "not_configured"` after retrieving the eligible play evidence.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql://...'
python scripts/migrate.py
python scripts/seed.py
python scripts/ingest_movement.py
PORT=8000 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`python scripts/ingest_movement.py` defaults to `data/fixtures/movement_skillcorner_like.json`. It is safe to run repeatedly because movement identity is `(play_id, player_id, source)`.

## Lieutenant

```bash
curl -sS http://127.0.0.1:8000/lieutenant/ask \
  -H 'content-type: application/json' \
  -d '{
    "question":"Does this player show enough movement speed to call him an athlete and a processor?",
    "player_id":"30000000-0000-0000-0000-000000000002",
    "week":3,
    "min_n":5
  }'
```

The evaluator may only use the retrieved first-party JSON evidence. Claude cannot add web knowledge or famous-player comparisons. The server, not the model, attaches the canonical evidence `play_ids` to the response.

## Hidden radar

```bash
curl -sS 'http://127.0.0.1:8000/radar/hidden?min_speed_pct=75'
```

Radar considers players whose `league_level` is `FCS` or `OTHER`, or whose `scout_visit_flag` is false, then requires max speed or COD to clear the requested percentile within available movement evidence. COD is treated only as a vendor-provided relative field; this repo does not claim a universal cross-vendor COD scale. `production_residual` is returned as null until a first-party residual metric exists.

## Combine natural language

```bash
curl -sS http://127.0.0.1:8000/ask/combine \
  -H 'content-type: application/json' \
  -d '{"question":"Show 2026 combine 40-yard dash results under 4.50"}'
```

This endpoint can query `combine_results` only. It maps recognized combine event/year/value constraints into one static parameterized SQL statement. Questions outside combine data are rejected; no web search or arbitrary SQL is available.

## Reliability boundary

`/health` remains DB-free. `/ready` remains a database readiness probe. Claude is never called from startup, liveness, or readiness. Claude calls are asynchronous and bounded to 20 seconds. Evaluator errors return a non-grade response and do not terminate the uvicorn process. Railway dashboard/service settings remain authoritative; `railway.json` is not treated as the source of truth.

# FIELDMIND College Data

## Source

V1.2 uses the College Football Data REST API (`https://api.collegefootballdata.com`) as the first production college play-by-play adapter.

The historical plays operation is `GET /plays` and requires `year` and `week`. Authentication is server-side bearer authentication. Store the credential only as:

```bash
CFBD_API_KEY=...
```

Never commit the key, expose it in a browser bundle, put it in a URL, or log it.

## Database preparation

```bash
export DATABASE_URL='postgresql://...'
export CFBD_API_KEY='...'
python scripts/migrate.py
```

Migration `002_college_play_evidence.sql` adds:

- `plays.ppa`
- `plays.source_play_type`
- `plays.play_text`

PPA and EPA are intentionally separate. A CFBD PPA value is never written into the `epa` column.

## Ingest one week

```bash
python scripts/ingest_cfbd.py --season 2025 --week 1
```

## Ingest a bounded week range

```bash
python scripts/ingest_cfbd.py --season 2025 --start-week 1 --end-week 15
```

The CLI requests and finishes one week before requesting the next. It never asks CFBD for an entire season in one response.

Postseason example:

```bash
python scripts/ingest_cfbd.py --season 2025 --start-week 1 --end-week 4 --season-type postseason
```

## Evidence rules

Fields accepted directly from CFBD include game/play identity, offense, defense, home/away, period, clock, down, distance, yards to goal, yards gained, source play type, play text, scores, and PPA.

FIELDMIND derives only operational fields needed by the V1 schema:

- play family: conservative pass/run classification from source play type
- distance bucket: short `<=3`, medium `4-6`, long `>=7`
- field zone from yards to goal
- explosive: pass `>=20` yards, run `>=10` yards
- pressure proxy: source play type explicitly identifies a sack
- turnover proxy: source play type explicitly identifies an interception or opponent fumble recovery
- success proxy: `ppa > 0` when PPA exists

The success proxy is tagged `success_proxy_ppa_positive`. It is not represented as a vendor-provided success field.

FIELDMIND does not infer from this feed alone:

- coverage
- route concept
- motion
- offensive personnel
- formation
- communication requirements
- read progression
- cognition traits

Those fields remain null or `UNKNOWN` until film, tracking, practice, or another trusted source supplies evidence.

## Data quality

After ingestion:

```bash
python scripts/data_quality.py
python scripts/benchmark.py --iterations 25 --warmup 3
```

`data_quality.py` hard-fails on missing or duplicate external identities and reports:

- plays by source/season
- EPA coverage
- PPA coverage
- unknown formation rate
- unknown personnel rate
- stale ingest runs

High unknown formation/personnel rates for CFBD are expected until film enrichment exists. They are visible by design.

## Reliability boundary

CFBD availability or quota state must never determine API liveness. The production web service does not call CFBD during startup, `/health`, `/ready`, or ordinary reads. External ingest is an explicit one-off data operation.

If CFBD returns an authorization, quota, transient server, or network error, the ingest run is marked failed and existing database evidence remains available.

## Terms and access

Before production use, verify the current CFBD access tier, quota, and Terms of Use. Access policy can change independently of this repository. Do not commit a credential or redistribute a user's API key.

# Manual Sunday Source-Triage

This is one worker behind one human gate. It checks already-ingested plays for one season, week, and source, stages integer honesty counts in `agent/sunday-triage/report.md`, prints one schema-bound JSON object, and stops. It does not ingest or modify product data.

## Run one manual Sunday

With a live database:

```bash
python scripts/sunday_triage.py \
  --season 2025 \
  --week 1 \
  --source cfbd \
  --retry-count 0 \
  --database-url "$DATABASE_URL"
```

Without a live database, prepare an exported-counts JSON object with non-negative integer values for `n_plays`, `n_unknown_family`, `n_unknown_formation`, `n_missing_external_id`, `n_duplicate_external_id`, and `n_source_family_promotions`; add an `ingest_runs` array of summary objects. Do not place raw source rows in that file.

```bash
python scripts/sunday_triage.py \
  --season 2025 \
  --week 1 \
  --source cfbd \
  --retry-count 0 \
  --counts-json exported-counts.json
```

The no-database report is stamped `ASSUMPTION: no live DB`. `ingest_runs` is read by season and source because the table has no week column. Target plays are selected through `games.week`. If ingest metadata lacks an explicit week key or range, the report says `NOT IN THE EVIDENCE: ingest run week attribution`; it never derives a week from `finished_at`. [FACT — `db/migrations/001_production_provenance.sql`]

UNKNOWN counts read `plays.play_family` and `plays.formation`, not resolved `program_play_tags`. Those play columns exist in this schema and represent source-row defaults for this check. Source evidence and trusted program tags remain separate in the pilot. [FACT — `app/wedge.py`]

Review stdout against `agent/sunday-triage/40-returns.schema.json`, then review `agent/sunday-triage/report.md`. Any invalid JSON, hard failure, invented attribution, raw-row dump, trusted-tag write, or constraints-edit proposal is a rejection.

If the result passes, the human types exactly:

`APPROVE`

The human then copies the report to a new append-only path and does not overwrite an existing file:

```bash
cp agent/sunday-triage/report.md agent/sunday-triage/40-runs/YYYY-MM-DDTHHMM.md
```

This is a gate action, not evidence that a pilot rehearsal occurred. Rehearsal results must be observed and recorded using the controlled checklist. [FACT — `docs/PILOT_REHEARSAL_CHECKLIST.md`]

## Forbidden next shape

- No chatbot or multi-agent swarm.
- No ingest invocation or raw CFBD/nflverse feed dump.
- No `program_play_tags` or `play_tag_votes` write.
- No source `pass`/`run` promotion to trusted `play_family`.
- No tendency claim when `n < 8`.
- No call-sheet freeze or tag resolution.
- No email, tweet, payment, send, publish, or other outbound action.
- No customer, buyer, school, quote, or `customer.md` invention.
- No VoiceStudio, DFS, NFL+ ingest, or live sideline feed.
- No cognition score or QB translation model.
- No executable meta-loop and no worker-authored constraints edit.
- No CI workflow, Railway cron, GitHub Action, or provisioned schedule.

The cadence in `80-ROUTINE.md` is documentation only. Nothing in this change schedules the runner.

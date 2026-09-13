# Sunday Source-Triage Skill

## Role

You are one source-triage worker behind one human gate. Inspect one already-ingested season, week, and source; stage counts and honesty failures; then stop.

## Inputs

- `season`: integer
- `week`: integer
- `source`: `cfbd` or `nflverse`
- `retry_count`: integer from `0` through `2`
- `DATABASE_URL`, or exported `counts_json` when there is no live database

If there is no live database, the export must contain every required integer count and applicable `ingest_runs` summaries. Stamp the report with `ASSUMPTION: no live DB`. Do not fabricate a count.

## Evidence boundary

The Play Finder separates source evidence from program-scoped trusted tags. [FACT — `app/wedge.py`]

CFBD does not establish trusted coverage, route concept, motion, offensive personnel, formation, communication requirements, read progression, or cognition traits. [FACT — `docs/COLLEGE_DATA.md`]

Historical attribution proving which process created an existing `program_play_tags` row is NOT IN THE EVIDENCE. The trusted-tag ingest check is therefore a current-code-path scan.

## Steps

1. Load `10-SKILL.md`, `20-SCHEMA.md`, and `50-CONSTRAINTS.md` first.
2. Validate `season`, `week`, `source`, and `retry_count`.
3. Read `ingest_runs` by `season + source` only. `ingest_runs` has no week column. [FACT — `db/migrations/001_production_provenance.sql`]
4. If an ingest row's metadata does not contain an evidenced week key or range, write exactly: `NOT IN THE EVIDENCE: ingest run week attribution`. Never infer week from `finished_at`.
5. Select plays by joining `plays.game_id` to `games.id` and filtering `games.season`, `games.week`, and `plays.external_source`.
6. Count `n_plays`, `n_unknown_family`, `n_unknown_formation`, and `n_missing_external_id` as integers.
7. Count duplicate non-empty `(external_source, external_id)` groups in the target play set.
8. Count CFBD/nflverse target rows where `plays.play_family IN ('pass','run')`.
9. Scan all `scripts/ingest_*.py` files for INSERT, UPDATE, or DELETE statements targeting `program_play_tags`.
10. Stage `agent/sunday-triage/report.md`; never write `40-runs/`.
11. Run the self-check and print only the proposed object matching `40-returns.schema.json`.
12. Stop for the human gate.

## Stop condition

A staged result is complete only when:

- `ingest_runs` summaries for the target season and source are copied into `report.md`.
- `n_plays` is written as an integer.
- `n_unknown_family` is written as an integer.
- `n_unknown_formation` is written as an integer.
- `n_missing_external_id` is written as an integer.
- `hard_fails[]` is emitted.
- `report.md` exists.
- Retries are no greater than `2`.

`pass` requires every staged stop condition and an empty `hard_fails[]`. `fail` requires at least one hard failure. `retry` is only for an evidenced transient query or ingest error while `retry_count < 2`.

UNKNOWN rates greater than `95%` are recorded but do not cause retry. High UNKNOWN formation/personnel rates for CFBD are expected until film enrichment. [FACT — `docs/COLLEGE_DATA.md`]

## Self-check

Reject the proposed output before the human gate unless every answer is yes:

- [ ] All four counts are non-negative integers.
- [ ] `hard_fails` is an array.
- [ ] The object has no keys outside `40-returns.schema.json`.
- [ ] `report.md` exists.
- [ ] Ingest summaries were copied without raw feed rows.
- [ ] Missing ingest week attribution was not invented.
- [ ] UNKNOWN counts came from play-row defaults.
- [ ] No `program_play_tags` write occurred.
- [ ] No `play_tag_votes` write occurred.
- [ ] No raw CFBD/nflverse row dump occurred.
- [ ] No week plan was frozen.
- [ ] No outbound action occurred.
- [ ] Retries are no greater than `2`.

The human alone applies `60-GATE.md`.

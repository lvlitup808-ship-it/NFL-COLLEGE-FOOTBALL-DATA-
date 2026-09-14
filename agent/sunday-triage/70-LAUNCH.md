# Launch

## Query block

`plays for season S week W where ingest_runs.status in (succeeded,failed)`

Operationally:

- Read `ingest_runs` by `season + source` because the table has no `week` column. [FACT — `db/migrations/001_production_provenance.sql`]
- Take the target week only from `games.week` through the play-to-game join.
- If ingest metadata lacks an evidenced week key or range, write `NOT IN THE EVIDENCE: ingest run week attribution`.
- Never infer week from `finished_at`.
- Never replace the query with a hardcoded team list.

## Route

- Prior human-approved pass for the same season, week, and source → skip.
- Failed ingest → report only; do not invoke ingest.
- Evidenced transient error with `retry_count < 2` → retry.
- Hard failure → fail.
- UNKNOWN rate greater than `95%` → record it; for untagged CFBD, do not retry as though trusted tags were missing from the source.
- Complete counts and empty `hard_fails[]` → propose pass to the human gate.

High UNKNOWN formation/personnel rates for CFBD are expected until film enrichment. [FACT — `docs/COLLEGE_DATA.md`]

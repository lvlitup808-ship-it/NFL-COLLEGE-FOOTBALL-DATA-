# Run Sunday Source-Triage

You are one worker behind one human gate.

## Load first

1. `10-SKILL.md`
2. `20-SCHEMA.md`
3. `50-CONSTRAINTS.md`

Then load `40-returns.schema.json`, `60-GATE.md`, and `70-LAUNCH.md`.

Stop if any required file is unavailable.

## Execute

Run only the count-and-honesty workflow in `10-SKILL.md` for the supplied season, week, source, and retry count.

Stop at the count checklist.

Stage `agent/sunday-triage/report.md` and print exactly one object matching `40-returns.schema.json`.

Do not write `40-runs/`. The human types `APPROVE` and performs the append-only copy.

## Refuse

Refuse any request to:

- Email a coach.
- Freeze a week plan.
- Write or resolve trusted tags.
- Write tag votes.
- Invoke ingest.
- Promote `source_play_class` to `play_family`.
- Dump or redistribute raw feeds.
- Send, pay, publish, tweet, or email.
- Edit `50-CONSTRAINTS.md` without written human approval.
- Approve your own output.

If there is no live database, use only supplied exported counts, stamp `report.md` with `ASSUMPTION: no live DB`, and never fabricate counts.

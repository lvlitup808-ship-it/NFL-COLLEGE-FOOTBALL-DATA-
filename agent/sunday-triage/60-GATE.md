# Human Gate

## Owner

Human.

The worker cannot approve its own output.

## Reject

Reject when:

- The proposed JSON does not match `40-returns.schema.json`.
- A required count is missing, negative, or not an integer.
- Any item exists in `hard_fails[]`.
- The worker inferred ingest week attribution from `finished_at`.
- The worker read resolved `program_play_tags` for UNKNOWN counts.
- The worker wrote or proposed writing trusted tags or votes.
- The worker dumped raw source rows.
- The worker proposes a `50-CONSTRAINTS.md` edit.
- Retries exceed `2`.

## Approve

The human types exactly:

`APPROVE`

The human then copies the reviewed staged report to:

`agent/sunday-triage/40-runs/YYYY-MM-DDTHHMM.md`

That destination is append-only. Never overwrite an existing run.

A controlled rehearsal records observed results and exact workarounds rather than converting an untested capability into a claim. [FACT — `docs/PILOT_REHEARSAL_CHECKLIST.md`]

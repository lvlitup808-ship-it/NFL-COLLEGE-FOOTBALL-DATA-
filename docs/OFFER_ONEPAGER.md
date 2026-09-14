# FIELDMIND Pilot Offer

## What ships

- A six-game-week pilot for three seats. [Source: `docs/WEEKLY_WEDGE_EXECUTION.md` §7]
- Onboarding, program setup, vocabulary calibration, ingest support, agreement reporting, weekly decision surfaces, call-sheet generation, a weekly coordinator debrief, and blocker fixes. [Source: `docs/WEEKLY_WEDGE_EXECUTION.md` §7]
- Authenticated program tenancy, Play Finder, trusted human tags, two-GA agreement, weekly CALL / DO NOT CALL / IF-THEN decisions, evidence play IDs, and Thursday freeze. [Source: `docs/WEEKLY_WEDGE_EXECUTION.md` §§3, 5]
- Customer-authorized film links and normalized telestration coordinates; film remains outside FIELDMIND. [Source: `docs/WEEKLY_WEDGE_EXECUTION.md` §§2, 6]

## What does not ship

- No public data portal or raw CFBD/nflverse feed redistribution. [Source: `README.md`; `docs/WEEKLY_WEDGE_EXECUTION.md` §§2, 6]
- No automated coverage, concept, personnel, formation, motion, or play-family inference from public play-by-play. [Source: `README.md`; `docs/WEEKLY_WEDGE_EXECUTION.md` §§3, 5]
- No film capture, scraping, mirror, or claim that Hudl embedding works. [Source: `README.md`; `docs/WEEKLY_WEDGE_EXECUTION.md` §§2, 6]
- No cognition score, betting workflow, live play calling, recruiting marketplace, draft model, or generic AI chat. [Source: `docs/WEEKLY_WEDGE_EXECUTION.md` §§3, 8]

## Price

`Offer: $3,000 for six game weeks / three seats.` [Source: `docs/WEEKLY_WEDGE_EXECUTION.md` §7]

NOT IN THE EVIDENCE: paid customer price

ASSUMPTION: $3,000 is the working pilot price; the founder must confirm it before using this offer. [Source: `docs/WEEKLY_WEDGE_EXECUTION.md` §7]

## How a program starts

1. Provision one program owner, then add the coach and two GA memberships to the same `program_id`. [Source: `scripts/provision_pilot_user.py`; `README.md`]
2. Run the controlled 20-play rehearsal with authorized film links, blind tagging, Finder verification, and exact blocker notes. [Source: `docs/PILOT_REHEARSAL_CHECKLIST.md`]
3. Create evidence-backed call decisions, verify the `n=8` approval guard, and have the coach freeze the Thursday sheet. [Source: `docs/PILOT_REHEARSAL_CHECKLIST.md`; `docs/WEEKLY_WEDGE_EXECUTION.md` §6]

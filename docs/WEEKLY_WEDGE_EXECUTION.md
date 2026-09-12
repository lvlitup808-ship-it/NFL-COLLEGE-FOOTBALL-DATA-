# FIELDMIND — Locked Week-of-Game Wedge

Status: implementation contract for the 90-day pilot.

## 1. Company line

FIELDMIND is the week-of-game decision layer that turns a staff's own film tags and play evidence into a Thursday call/do-not-call sheet with visible sample size, confidence, and evidence of which players have processed the relevant look.

## 2. Positioning

- Hudl: film remains in Hudl. FIELDMIND does not capture, host, scrape, or recreate the staff's film workflow; it converts trusted staff evidence into weekly decisions.
- PFF: PFF provides grades/data. FIELDMIND answers what this staff should call or remove against this opponent with this personnel.
- CFBD/nflverse: source PBP is factual evidence only. FIELDMIND does not resell raw feeds or infer film-only facts from PBP.
- S2: FIELDMIND does not claim to be a lab cognition test. The pilot stores raw football-performance evidence that a player did or did not process a tagged look.

## 3. Locked MVP

IN: authenticated program tenancy; Play Finder; trusted human tags; two-GA agreement; Opponent One-Pager; Self-Scout; candidate/approved CALL, DO NOT CALL and IF-THEN decisions; evidence play IDs; raw player-look evidence; Thursday freeze; changed-a-call logging; customer-authorized Hudl references.

OUT for 90 days: NFL tracking, draft model, college-to-NFL scoring, public API, betting, live play calling, computer vision, automated coverage/concept/personnel/formation inference, cognition scoring UI, universal grades, recruiting marketplace, mobile app, public raw-data explorer.

The pilot production entrypoint is `app.pilot:app`. It removes the legacy `/api/v1` surfaces, including the QB heuristic/cognition surfaces, before registering the pilot router. `/health` and `/ready` remain from `app/main.py`.

## 4. Controlled vocabulary v0

Rule: if the film/tagger cannot prove the value, use `UNKNOWN`. Two blind taggers calibrate on at least 50 shared plays. Overall field agreement must be >=80%. Any term with at least 10 observed opportunities and <80% agreement is removed from active vocabulary until its definition is rewritten and recalibrated.

### play_family

| Term | Definition | Do not use when | Example |
| --- | --- | --- | --- |
| UNKNOWN | Film does not establish an approved concept. | Never guess from PBP text. | Camera does not show enough of the play. |
| INSIDE_ZONE | Interior zone run with zone combinations and an interior RB read. | Do not use merely because the run hits A/B gap. | Shotgun inside zone weak. |
| OUTSIDE_ZONE | Lateral zone/stretch with bang-bend-bounce read. | Do not use for pin-pull sweep. | Outside zone to TE. |
| DUO | Downhill double-team run with RB generally keying LB movement. | Do not call every no-pull inside run Duo. | 12P Duo weak. |
| POWER | Gap scheme with a puller leading through the point of attack. | Do not use for Counter solely because a guard pulls. | Power O. |
| COUNTER | Misdirection gap scheme with pull action opposite initial flow. | Do not use without clear counter action. | GT Counter. |
| ISO | Lead blocker isolates a second-level defender. | Do not use for every downhill run. | I-formation Iso. |
| DRAW | Pass presentation/pass set precedes delayed run. | Do not use for normal shotgun run. | QB Draw. |
| MESH | Paired shallow crossers form the core concept. | Do not tag random crossing routes as Mesh. | Mesh + sit. |
| STICK | Stick/flat family built around short stick read. | Do not use because one receiver hooks. | Stick-flat. |
| SPACING | Multiple underneath sit/hook routes horizontally stretch zones. | Do not use for generic quick game. | 3-man Spacing. |
| FLOOD | Three-level stretch to one side. | Do not use because QB boots without the three levels. | Boot Flood. |
| FOUR_VERTICALS | Four vertical stems are the primary stress. | Do not use for an isolated two-route shot. | 4 Verts. |
| SCREEN | Designed throw near/behind LOS using invited rush/block release. | Do not tag an ordinary checkdown. | RB middle screen. |

### formation

Priority when multiple labels fit: `BUNCH -> EMPTY -> NUB -> CONDENSED -> 3X1 -> 2X2 -> UNKNOWN`.

| Term | Definition | Do not use when | Example |
| --- | --- | --- | --- |
| UNKNOWN | Structure cannot be established. | Never infer from personnel alone. | Film starts post-snap. |
| 2X2 | Two eligible receivers distributed to each side. | Do not use when one side forms Bunch. | Doubles. |
| 3X1 | Three eligible receivers to one side, one opposite. | Bunch takes precedence. | Trips open. |
| BUNCH | Three receivers tightly grouped. | Do not use for ordinary trips spacing. | Tight bunch right. |
| EMPTY | No RB aligned in a conventional backfield position. | Do not infer from 10 personnel alone. | 3x2 Empty. |
| NUB | Attached TE/tight surface with no detached WR to that side. | Do not use merely because a TE is attached. | Trips opposite nub TE. |
| CONDENSED | Receivers significantly reduced/tight to formation. | Do not use for standard splits. | Condensed 2x2. |

### motion

| Term | Definition | Do not use when | Example |
| --- | --- | --- | --- |
| UNKNOWN | Pre-snap movement cannot be established. | Do not assume NONE. | Clip begins at snap. |
| NONE | No meaningful pre-snap motion/shift. | Do not use when film misses the pre-snap window. | Static 2x2. |
| JET | Fast lateral motion across/near QB at snap. | Do not use for a slow trade. | WR jet. |
| ORBIT | Motion travels behind the backfield/QB on a deeper path. | Do not call every return motion Orbit. | WR orbit behind RB. |
| RETURN | Player motions one direction and returns before/at snap. | Do not use for one-direction Jet. | Return motion to trips. |
| SHIFT | One or more players relocate and become set before snap. | Do not label live-at-snap movement Shift. | TE shifts across formation. |

### coverage_family

| Term | Definition | Do not use when | Example |
| --- | --- | --- | --- |
| UNKNOWN | Coverage cannot be confidently established. | Never infer solely from result or shell. | Camera loses safeties. |
| COVER_0 | Man with no deep middle safety. | Do not use merely because defense blitzes. | Zero pressure. |
| COVER_1 | Man with one post safety. | Do not use if underneath defenders are matching as zone. | 1-Robber is Cover 1 family. |
| COVER_2 | Two-deep family with underneath zone defenders. | Do not infer from two-high shell alone. | Tampa 2 remains Cover 2 family. |
| COVER_3 | Three-deep family. | Do not assume from single-high shell alone. | Buzz/Cloud may resolve to Cover 3. |
| QUARTERS | Four-deep match/quarters family. | Do not tag from two-high shell alone. | Quarters/4-read. |
| COVER_6 | Quarter-quarter-half split-field family. | Do not use for generic split-field coverage. | Quarters one side, Cover 2 opposite. |

### personnel

| Term | Definition | Do not use when | Example |
| --- | --- | --- | --- |
| UNKNOWN | Eligible personnel cannot be established. | Never infer from formation. | Roster/number unclear. |
| 10 | 1 RB, 0 TE, 4 WR. | Do not infer from Empty alone. | 10P Doubles. |
| 11 | 1 RB, 1 TE, 3 WR. | Do not assume because a TE is attached. | 11P Trips. |
| 12 | 1 RB, 2 TE, 2 WR. | Do not guess H-back position without roster confirmation. | 12P Nub. |
| 20 | 2 RB, 0 TE, 3 WR. | Do not call every two-back look 20. | Pony 20P. |
| 21 | 2 RB, 1 TE, 2 WR. | Do not infer from I-formation alone. | Traditional 21P. |

## 5. Data contract

Migration `003_weekly_wedge.sql` adds `users`, `program_memberships`, `auth_tokens`, `play_tag_votes`, `program_play_tags`, `week_plans`, `player_look_evidence`, `changed_call_logs`, and `play_links`; scopes `call_rules` to `program_id` + `week_plan_id`; and adds `plays.source_play_class`.

External `cfbd`/`nflverse` PBP is guarded at the database boundary: source pass/run becomes `source_play_class`; canonical `play_family` becomes `UNKNOWN`; `personnel_offense` and `formation` become `UNKNOWN`; `motion`, `concept`, and `coverage` become null. Staff truth lives in `program_play_tags` instead of the global `plays` row.

Migration `004_decision_guard.sql` prevents a rule from becoming `approved` unless `sample_n >= 8` and confidence is `directional` or `usable`.

Bearer tokens are opaque random values. Only SHA-256 token hashes are persisted. `program_id` is derived from a validated membership. Multi-program users may select a membership with `X-Program-ID`; the header is never trusted without membership validation.

### Pilot API

- `GET /api/v1/me`
- `GET /api/v1/vocab`
- `GET /api/v1/plays`
- `POST /api/v1/plays/{play_id}/tag-votes`
- `POST /api/v1/plays/{play_id}/tag-resolve` (coach/owner)
- `GET /api/v1/tag-agreement`
- `POST /api/v1/plays/{play_id}/links`
- `POST /api/v1/week-plans`
- `GET /api/v1/week-plans/{id}/opponent`
- `GET /api/v1/week-plans/{id}/self-scout`
- `POST /api/v1/week-plans/{id}/call-rules`
- `PATCH /api/v1/week-plans/{id}/call-rules/{rule_id}`
- `POST /api/v1/week-plans/{id}/player-look-evidence`
- `POST /api/v1/week-plans/{id}/freeze`
- `GET /api/v1/week-plans/{id}/call-sheet`
- `POST /api/v1/week-plans/{id}/changed-call`

`/health` remains DB-independent. `/ready` remains the DB readiness check. Ingest remains an explicit one-off job and never runs on web startup.

## 6. Week loop

Sunday (45-60 min): validate previous game; resolve tags; run self-scout; compare last sheet with actual calls; log changed-a-call.

Monday (150-210 min per GA initially): two GAs blind-tag the relevant opponent sample. Target roughly 180 opponent plays from the most relevant three games. Resolve disagreement only after blind entry. Output 5-10 questions, not 40 tendencies.

Tuesday (25-35 min coordinator): turn only qualified evidence into at most 5 CALL, 5 DO NOT CALL, and 5 IF-THEN decisions.

Wednesday (15-25 min): log only practice/player evidence tied to Tuesday's decision questions. No 0-100 cognition score is produced.

Thursday (15 min): remove low-confidence candidates, approve the core menu, review player-look evidence, and freeze the sheet.

Friday (5 min): confirm emergency answers and communication ownership. No new low-confidence tendency is promoted.

Honesty copy:

- No trusted plays: `No trusted plays match this situation.`
- Unresolved film fields: `Plays exist, but the required film tags are unresolved. FIELDMIND will not infer formation, motion, personnel, coverage, or concept from play-by-play.`
- n<8: `INSUFFICIENT — question, not game-plan fact.`
- n=8-19: `DIRECTIONAL — use this to guide film/practice questions, not an automatic check.`
- n>=20: `USABLE — enough evidence to enter staff review. Still not deterministic.`
- Call sheet: `No tendency or call rule becomes actionable below the minimum sample guard.`

## 7. Pilot

Offer: $3,000 for six game weeks / three seats.

FIELDMIND provides onboarding, program setup, vocabulary calibration, ingest support, agreement reporting, weekly decision surfaces, call-sheet generation, a weekly coordinator debrief, and blocker fixes.

Staff provides authorized film/data access, opponent game selection, two blind GA taggers, coordinator approval/rejection, and a weekly answer to one metric: `Did this sheet cause you to add, remove, modify, or keep a call differently than you otherwise would have?`

Success: at least one unprompted Thursday use; at least two genuine changed-call weeks of six; >=80% tag agreement; <=4 GA-hours/week after Week 2; coordinator asks to keep the system for the next opponent.

Kill/rework: zero changed-call events through Week 4; no unprompted Thursday use by Week 5; GA labor >4 hours/person/week after calibration; <80% agreement for two consecutive weeks; staff says Hudl already provides the exact decision; founder interpretation is required every week; required data rights cannot be established.

Do not rescue a failed pilot by adding AI, tracking, recruiting, draft, or betting features.

## 8. 90-day build order

1. Auth/tenancy.
2. Vocabulary calibration and blind agreement.
3. Program-scoped tag writes.
4. Play Finder.
5. Opponent One-Pager.
6. Self-Scout.
7. Week plans and decision objects.
8. Raw player-look evidence.
9. Thursday Call-Sheet + freeze + changed-call log.
10. Dogfood on one real opponent week.
11-13. Six-week pilot and renewal decision.

Forbidden for all 90 days: NFL tracking, draft model work, college-to-NFL model work, public API/data explorer, cognition scoring UI, betting, computer vision, live play calling, recruiting marketplace, mobile app, generic AI chat.

## 9. Risk register

| Risk | Cheapest test | Mitigation |
| --- | --- | --- |
| CFBD terms | Review current tier/ToS before first paid pilot. | Derived private decisions only; do not redistribute raw feed. |
| nflverse/data rights | Inventory every dataset and source-specific license. | Keep NFL data out of the wedge unless rights are documented. |
| Tag quality | Blind-tag 50 real plays before adding analytics. | <80% means term/field is rewritten or removed. |
| Hudl copying | Use customer-authorized references/exports only. | No scraping, bulk copying, or FIELDMIND film mirror. |
| Player-evidence optics | Show raw evidence screen to three coaches and ask what they think it claims. | No score/ranking and mandatory footer. |
| Seasonality | Sell against an immediate opponent week. | If live adoption is impossible, run shadow mode with one coordinator. |

Publishing raw CFBD/nflverse data reopens licensing review. A private derived-output pilot is not permission to redistribute source feeds, Hudl film, broadcast footage, or other third-party assets.

## 10. First customer conversation

1. Walk me through last Thursday from arrival until the call sheet was finished.
2. What part of opponent prep consumes the most GA hours?
3. With four opponent games in Hudl, what tells you a tendency is real enough for the call sheet?
4. Tell me about the last tendency that looked important on film but did not matter on Saturday.
5. How do you distinguish a three-play pattern from something you actually trust?
6. Who owns tags, and how often do two staff members disagree on formation, concept, motion or coverage?
7. When the staff says `they're Cover 3` or `they run Counter here`, where does the evidence live?
8. What makes you take a call out on Wednesday or Thursday?
9. How do you know your player has actually processed the look that call requires?
10. When did film study last change one specific Thursday call?
11. What must be true for you to trust a one-page situation/evidence/call sheet?
12. Which is worth more: saving three GA-hours with zero changed calls, or changing two real calls with zero time saved?

No demo before the workflow is understood.

## 11. Copy-paste artifacts

### Pilot email

Subject: 6-game FIELDMIND pilot

Coach,

I'm building FIELDMIND around one specific problem: by Thursday, your staff has watched the film and built the tendencies, but somebody still has to turn all of that information into a small number of calls you actually trust.

FIELDMIND does not replace Hudl. Your film stays where it is.

For a 6-game pilot, we take your staff's trusted film tags and weekly evidence and produce one Thursday sheet:

Situation -> what the opponent has shown -> sample size/confidence -> CALL or DO NOT CALL -> supporting plays -> which of your players have successfully processed that look.

Every tendency shows the evidence count. If the sample is too small, FIELDMIND labels it as a question rather than presenting it as a fact.

Pilot: 6 game weeks; 3 staff seats; $3,000 total; weekly opponent one-pager; self-scout; Thursday call/do-not-call sheet; player-look evidence; weekly measurement of whether the system actually changed a call.

The success test is simple: does your coordinator use the Thursday sheet, without us prompting him, and does it change a real decision? If it does not, we should not pretend the product worked.

Grant
FIELDMIND

### Call-sheet structure

```
FIELDMIND — THURSDAY CALL SHEET
PROGRAM:
OPPONENT:
WEEK:
SIDE:
FROZEN:
MINIMUM N: 8
TAG AGREEMENT:
EVIDENCE AS OF:

CALL
Situation -> Evidence (n/confidence) -> Call -> Why -> Evidence plays -> Player-look evidence

DO NOT CALL
Situation -> Remove -> Why -> n/confidence -> Better answer -> Evidence plays

IF -> THEN
If -> Evidence n -> Then -> Player/unit requirement -> Backup answer

LOW-N QUESTIONS — NOT GAME-PLAN FACTS

THURSDAY DECISION
Calls added:
Calls removed:
Calls modified:

No tendency or call rule becomes actionable below the minimum sample guard.
```

### Never-claim player footer

`This card describes football-performance evidence from tagged game, practice, or meeting situations. It is not an IQ test, diagnosis, mental-health assessment, neurological or medical evaluation, or measure of a person's overall intelligence or potential. Do not use this evidence as a standalone basis for a cut, scholarship, roster, contract, recruiting, NIL, transfer, or draft decision. Always interpret the evidence with its sample size, evidence count, look diversity, source, and as-of date.`

## 12. Founder questions that change build order

1. Hours/week available to FIELDMIND?
2. Authorized Hudl access at a real program: yes/no?
3. Can the first pilot supply two GAs for a blind 50-play calibration?
4. First five target programs/conferences?
5. CFBD tier and documented commercial interpretation?
6. Standalone company or LVLITUP module?
7. Capital available for the next 90 days?
8. Legal entity that signs and invoices the $3,000 pilot?

## Pilot operations

Apply migrations:

```bash
export DATABASE_URL='postgresql://...'
python scripts/migrate.py
```

Provision the first program owner:

```bash
python scripts/provision_pilot_user.py \
  --program-name 'Example University Football' \
  --email 'coach@example.edu' \
  --display-name 'Coach Example' \
  --role owner \
  --days 30
```

The script prints the bearer token once. Do not commit it or place it in URLs/logs.

Run locally:

```bash
uvicorn app.pilot:app --host 0.0.0.0 --port 8000
```

Open `/` for the four-screen pilot UI. Production Docker/Railway use `app.pilot:app` on this branch.

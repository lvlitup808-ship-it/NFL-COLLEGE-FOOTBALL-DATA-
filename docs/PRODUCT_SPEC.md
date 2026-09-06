# FIELDMIND V1 PRODUCT + SYSTEM SPEC

## 1. Product thesis

FIELDMIND is a football decision system that converts play evidence, weekly preparation, personnel production, and position-specific cognition evidence into call-level decisions. The unit of truth is the play. The product is successful only when an output changes a call, changes who is on the field, changes how the staff prepares for an opponent, or measures whether a player transferred learning from practice to game evidence. It is not a replacement for film capture, a universal player grade, a clinical cognitive test, or a vanity prediction layer.

Decision ownership: [Product/Football] defines the football question and evidence standard. [AI] defines the data contract and scoring method. [SRE] can veto any design that creates an avoidable availability or memory risk.

## 2. Information architecture

System diagram:

```text
Film/Play Tags -----> Play Ingest API ---------> Railway Postgres
      |                     |                         |
      |                     |                         +--> indexed play finder
      |                     |                         +--> tendency aggregates
      |                     |                         +--> player production
      |                     |                         +--> cognition evidence
      |                     |
Clip object key ----------> | -----> S3-compatible object storage
                            |
Practice tags --------------+
Vendor/VR optional ----------+-----> cognition normalization worker (later service)
                                                     |
                                                     v
                                             Player Cognition Graph
                                                     |
                 +-------------------+---------------+------------------+
                 |                   |                                  |
                 v                   v                                  v
           Opponent DNA          Player OS                         Week Loop
                 |                   |                                  |
                 +-------------------+------------------+---------------+
                                                        v
                                              1-page call-sheet memo
```

Data flow: ingest tagged plays; persist play and clip pointer; aggregate opponent and self-scout splits with minimum-sample guards; attach player production and cognition evidence; produce call recommendations only when evidence is above the configured guard; push unresolved low-sample items back to practice as questions rather than facts.

V1 has one FastAPI web service and Railway Postgres. Python model jobs remain in-process only for the transparent QB baseline. Heavy model training becomes a separate worker only after the request path would otherwise block.

## 3. Data model

Program: future tenancy boundary. Key fields: id, name, level.

Team: belongs to program. Key fields: id, program_id, name, season.

Player: belongs to team. Key fields: id, team_id, name, position, class_year, jersey.

Game: joins two teams. Key fields: id, season, week, date, home_team_id, away_team_id.

Play: atomic football unit. Key fields: id, game_id, sequence, quarter, clock, down, distance, distance_bucket, yard_line, field_zone, score_diff, offense, defense, personnel, formation, motion, play_family, concept, coverage, pressure, result_yards, EPA, success, explosive, turnover, quarterback, cognition_events, tags.

Clip: pointer only. Key fields: id, play_id, provider, object_key, start_ms, end_ms. Video is never stored in Postgres and never loaded as a full season into API memory.

CognitionTraitScore: player-by-trait evidence object. Key fields: player_id, position, trait, score, sample_n, evidence_count, confidence, as_of, evidence.

PracticeEvent: transfer evidence. Key fields: player_id, event_date, look_family, rep_number, recognition_ms, decision_correct, communication_correct, pressure_proxy.

CallRule: staff-facing decision. Key fields: opponent, rule_type, situation, call_name, reason, sample_n, priority.

ModelRun: audit record for model inputs and outputs. Key fields: model_name, model_version, entity_type, entity_id, input_snapshot, output_snapshot.

Relationships: Program 1:N Team. Team 1:N Player. Game 1:N Play. Play 0:N Clip. Player 1:N CognitionTraitScore. Player 1:N PracticeEvent. Opponent context 1:N CallRule. ModelRun points to an evaluated entity without owning it.

## 4. Cognition graph spec

The graph measures football processing traits, never general intelligence.

Perceptual search: how efficiently a player finds relevant visual information. Operational inputs: time to first correct coverage/front identification, scan order tags, missed leverage indicators, route/fit recognition latency. Score direction: faster correct recognition raises score; fast wrong recognition does not.

Decision complexity: number and type of viable options processed correctly. Inputs: progression depth, conflict-player count, option-route branches, RPO conflict count, correct terminal choice. Score direction: correct decisions with more live branches receive more evidence weight than binary reads.

Working memory in play: retention of a pre-snap or in-play adjustment after the picture changes. Inputs: check retention, route conversion retention, protection change execution, repeated instruction dependency. Score direction: retained adjustment under changed picture raises score.

Processing under time: performance degradation as time pressure rises. Inputs: pressure arrival proxy, play-clock urgency, 2-minute context, recognition latency, decision correctness. Score is based on the slope from normal to compressed-time conditions, not just raw speed.

Composure/tilt: decision-quality recovery after a negative event. Inputs: next 1-5 comparable decisions after sack, turnover, missed assignment, penalty, or failed conversion. Score direction: rapid return to baseline decision quality raises score. Emotional or psychiatric claims are prohibited.

Learning rate: speed and accuracy change when the same look family repeats across meetings, practice, and games. Inputs: repetition number, recognition time, error recurrence. Score direction: faster correct recognition with declining error recurrence raises score.

Pre-snap vs post-snap delta: difference between recognition before snap and execution after rotation/movement. Inputs: pre-snap ID correctness, post-snap ID correctness, execution result. This separates recognition from adaptation.

Communication load: accuracy when the player must transmit or receive checks. Inputs: audible/check requirement, protection communication, route alert, teammate correction, delay/false-start outcomes.

Scoring approach: each trait is 0-100 only as a position-relative evidence scale. Raw events are normalized within position and task family. Correctness gates speed: a fast incorrect answer cannot score as high processing. Scores are shrunk toward 50 when sample size is small. Repeated identical looks are down-weighted so one scripted drill cannot dominate a trait. Game evidence has the highest weight, then high-fidelity team practice, then optional vendor/VR/tablet evidence. Vendor scores remain separate source features and never overwrite film evidence.

Sample-size rules: n<8 = insufficient, display score only as provisional internal evidence; n=8-19 = directional; n=20-49 = usable with visible confidence; n>=50 = strong only if evidence spans at least three distinct look families and two contexts. A staff member always sees n, evidence count, look diversity, and as-of date next to the score.

Position weights: QB weights perceptual search, decision complexity, processing under time, pre/post-snap delta, and communication load most heavily. OL weights working memory, communication load, post-snap adaptation, and pressure processing. LB/S weights perceptual search, working memory, decision complexity, and communication. WR/RB/TE weights leverage recognition, option-rule retention, post-snap adaptation, and composure. Scores are never compared across positions as if the task demands were identical.

Never-claim list: no IQ claim; no diagnosis; no mental-health inference; no neurological claim; no medical readiness claim; no genetic claim; no race/ethnicity/gender inference; no claim that one score predicts career success; no standalone cut decision; no standalone scholarship decision; no standalone draft decision; no hidden score without sample visibility.

## 5. Week-of-game workflow

Sunday: ingest previous game; attach clips; validate play tags; generate self-scout explosive/failure report; compare last week's plan to what was actually called; mark calls that produced decision stress or communication errors.

Monday: load opponent games; run opponent tendency splits; reject low-n tendencies; identify the 5-10 opponent questions worth answering; build play-finder cutups around those questions.

Tuesday: offensive/defensive staff converts evidence into if-then rules. Every rule contains situation, expected opponent behavior, sample_n, confidence, and the call/answer. Player OS surfaces which players have demonstrated the processing evidence required for each family.

Wednesday: practice the highest-value uncertainty. Tag recognition, communication, and execution. Repeated-look improvement updates learning-rate evidence. Information-overload flag fires when check volume rises while recognition or communication accuracy falls.

Thursday: rerun plan vs practice evidence. Remove calls the unit cannot execute at required speed. Freeze core menu. Generate 1-page call-sheet memo and player-specific trust/do-not-put-him-in-this-call notes.

Friday: short validation. No new low-confidence tendency is promoted into the plan. Confirm emergency answers and communication ownership.

Game day: staff uses the call sheet and attached play evidence. V1 is not live radio and does not automate play calling. Postgame actuals flow back into Sunday ingest.

## 6. V1 schema + API list

Physical schema is in `db/schema.sql`.

GET /health
Response 200: `{"status":"ok","service":"fieldmind-api","uptime_ms":12345}`. No DB dependency.

GET /ready
Response 200: `{"status":"ready","database":"ok"}`. Response 503 when Postgres is unavailable.

GET /api/v1/plays?offense=&defense=&down=&distance_bucket=&field_zone=&personnel=&formation=&play_family=&limit=20
Response: `{"count":20,"plays":[...]}`. Indexed filters target the V1 requirement of 20 results under 2 seconds under expected hobby-tier load.

POST /api/v1/plays/{play_id}/clip
Request: `{"object_key":"games/2026/w3/play-17.mp4","provider":"s3","start_ms":1200,"end_ms":9800}`.
Response 201: clip pointer object.

POST /api/v1/reports/opponent
Request: `{"opponent":"Metro State Panthers","down":3,"distance_bucket":"short","field_zone":"plus","min_n":8}`.
Response: opponent, filters, sample_n, min_n, flagged, sample_status, tendency rows, warning.

GET /api/v1/reports/self-scout?team=ATL%20Tech%20Owls&min_n=8
Response: play families with n, explosives, failures, avg_epa, success_pct, sample_flag.

GET /api/v1/players/{player_id}
Response: player, production, cognition traits with score+n+confidence, guardrails.

GET /api/v1/weekly/call-sheet?opponent=Metro%20State%20Panthers&min_n=8
Response: tendency evidence, do-not-call rules, decision guard.

POST /api/v1/models/qb-college-to-nfl
Request: `{"epa_per_dropback":0.24,"pressure_success_rate":0.48,"turnover_worthy_rate":0.035,"processing_score":74,"sample_dropbacks":320}`.
Response: translation_score, confidence, component scores, explicit unvalidated-model warning. This is a transparent heuristic baseline for one position, QB, not a draft model claim.

## 7. Three example outputs

### Opponent one-pager

OPPONENT: Metro State Panthers
SAMPLE: n=10 offensive plays in demo game. Overall split is directional. No individual play-family split clears n=8; family percentages are not promoted as tendencies.

WHAT THEY HAVE SHOWN
- Quick game: 2/10. Both successful. LOW-N: do not call this a stable tendency.
- Play action: 2/10. Both successful; one explosive and one red-zone TD. LOW-N.
- Pressure answer: tunnel screen produced 13 yards against six-man pressure. One example only.
- 3rd-and-short: snag from bunch converted against five-man pressure. One example only.

WHAT TO TEST THIS WEEK
- Does fast pressure force screen/quick-game answers repeatedly?
- Does 12 personnel continue to produce play-action shots in plus territory?
- Does jet/orbit motion change the run fit or merely dress the same core concepts?

CALL-SHEET STATUS
- No family tendency is strong enough to be treated as deterministic.
- Use these as practice questions until additional games raise n.

### QB mind card

PLAYER: Jalen Mercer, QB
SCOPE: football-performance evidence only. Not IQ. Not clinical.

Perceptual Search — 78/100 | n=46 | usable
Evidence: coverage ID correct on 25/31 charted scan reps; median first-decision recognition 690ms on clean looks.

Decision Complexity — 74/100 | n=39 | usable
Evidence: correct terminal answer on 20/27 tagged multi-option reps; strongest evidence in empty and RPO families.

Working Memory In Play — 71/100 | n=28 | usable
Evidence: retained post-snap adjustment on 16/20 tagged change reps; one documented miss after simulated pressure.

Processing Under Time — 67/100 | n=24 | usable
Evidence: recognition remains functional under pressure but latency increases; two negative decisions against simulated/robber pressure.

Composure/Tilt — 82/100 | n=18 | directional
Evidence: next two charted decisions after turnover were correct; same coverage-family mistake did not repeat in current sample.

TRUST THESE CALLS: defined RPO conflict reads, bunch quick-game pressure answers, boot/flood with clear movement key.
WATCH: empty full-field progression against simulated pressure and robber rotation.

### Do not call this

1. Situation: 3rd-and-2 to 4, plus territory.
Call: slow-developing GT counter.
Reason: front movement plus interior run blitz raises negative-play risk; use a quick edge answer. Evidence n=9.

2. Situation: 2nd-and-7+, empty vs mugged linebackers.
Call: full-field slow mesh progression.
Reason: simulated pressure plus robber rotation has produced the largest processing degradation in the current QB evidence. Use a defined hot, screen, or half-field answer. Evidence n=11 opponent-rule sample plus QB pressure evidence n=24.

3. Situation: any split below the configured n-guard.
Call: tendency-based automatic check.
Reason: the system does not promote low-n patterns into deterministic calls.

## 8. 12-week build plan

Week 1 — foundation. [AI/SRE] FastAPI service, Postgres schema, Dockerfile, Railway health/readiness, structured logs, seed loader, CI smoke tests. Dependency: none.

Week 2 — play ingest. [Product/AI] play CRUD/import contract, validation, clip pointer attach, index benchmarking. Dependency: schema.

Week 3 — play finder. [Product/Football] situation filters, saved searches, 20-play response benchmark. Dependency: ingest.

Week 4 — opponent DNA. [Football/AI] tendency aggregates, n-guards, low-sample warnings, one-pager export contract. Dependency: play finder.

Week 5 — self-scout. [Football] explosive/failure report, play-family efficiency, down-distance leakage. Dependency: stable tags.

Week 6 — player production. [AI/Football] player card production evidence, role/scheme tags, call-family trust data model. Dependency: plays linked to player.

Week 7 — cognition event tagging. [Cognition/Football] event taxonomy, five V1 traits, evidence viewer, prohibited-claim copy. Dependency: film tagging workflow.

Week 8 — cognition scoring. [AI/Cognition] shrinkage, sample confidence, position weighting, audit trail. Dependency: week 7 event quality.

Week 9 — weekly call sheet. [Football/Product] opponent questions, if-then board, do-not-call list, 1-page memo. Dependency: weeks 4-8.

Week 10 — QB college-to-NFL baseline. [AI/Football] transparent feature model, calibration dataset contract, backtest harness, explicit non-validation state. Dependency: clean QB samples.

Week 11 — reliability/performance. [SRE] query plans, pool limits, load test, memory ceiling, SIGTERM drain, failure injection, object-storage streaming rules. Dependency: complete request paths.

Week 12 — acceptance. [All] pass/fail V1 criteria, staff workflow test, security pass, deploy/runbook handoff, soak test begins. The 30-day soak criterion cannot be declared passed until 30 actual days complete.

## 9. Competitive kill-sheet

PFF: public product positioning is deep play-level data, grades, premium statistics, API/programmatic access, and as of September 2026 AI-assisted data questions. FIELDMIND must not compete on generic data volume. Wedge: staff-owned decision objects that join a team's own play tags, opponent rules, player call trust, and cognition evidence into the weekly call sheet.

Hudl: public positioning includes capture, video review, Assist breakdowns, custom tendency reports, Hudl IQ football analytics, recruiting, and tracking. FIELDMIND must assume Hudl remains the film system of record for many programs. Wedge: use clip pointers/integration rather than recreate capture; own the layer that connects tendency evidence to player processing constraints and call/no-call decisions.

S2 Cognition: public positioning explicitly measures split-second visual/cognitive abilities for sports and says it is not IQ. FIELDMIND must not claim to out-test a specialized vendor without validation. Wedge: film-derived and practice-derived cognition evidence tied to the actual scheme, actual opponent looks, actual calls, and learning transfer. Optional S2/vendor scores remain an input, not the decision object.

Catapult: public positioning spans athlete monitoring, American-football video analysis, player performance, and integrated performance workflows. FIELDMIND does not compete on wearables or physical-load monitoring in V1. Wedge: call-level tactical decision support plus scheme-specific cognition evidence.

Defensible combined claim: in the official public product descriptions reviewed for these competitors, none is positioned around one player/play/opponent object that simultaneously carries call tendency evidence, production, scheme-specific processing evidence, sample guards, and a staff-facing trust/do-not-call decision. This is the product wedge; it is not a claim that competitors are technically incapable of building it.

## 10. Seed JSON

`data/seed_plays.json` contains one fictional 20-play game with two teams, two QBs, situation fields, personnel, formation, motion, play family, concept, coverage, pressure, outcome, EPA, success/explosive/turnover flags, cognition events, five QB cognition traits, and three call rules. `scripts/seed.py` applies `db/schema.sql` and loads the seed idempotently.

## 11. This product dies if…

1. Tags are inconsistent across analysts. Mitigation: controlled vocabularies, validation, audit samples, and team-specific tag mapping.
2. Low-n noise is sold as certainty. Mitigation: hard minimum-sample guards and visible n on every inference.
3. Cognition becomes a disguised IQ score. Mitigation: trait-only display, position/task context, prohibited claims, evidence links, no composite intelligence number.
4. Coaches cannot trace a recommendation to plays. Mitigation: every recommendation links to filter context and clip pointers.
5. Staff has to duplicate Hudl workflows. Mitigation: treat existing film systems as source/integration targets; own decisions, not capture.
6. The model outruns validation. Mitigation: version every model, label heuristic baselines, backtest before changing decision authority.
7. Postgres queries degrade as seasons accumulate. Mitigation: indexed situation columns, EXPLAIN checks, bounded page sizes, archival/partition strategy only when data proves need.
8. Film is loaded through API memory. Mitigation: store object keys, stream objects directly, never deserialize seasons of video into the web process.
9. Railway restarts become an operating procedure. Mitigation: liveness/readiness split, reconnect backoff, pool caps, graceful drain, structured failure logs, load/soak testing.
10. Outputs do not change a football decision. Mitigation: every feature acceptance test must name the call, lineup, opponent expectation, player-processing question, or weekly-learning question it changes.

## 12. Complete Railway pack

### Root Cause

There was no existing application in the repository and therefore no runtime/build log evidence from which to identify a historical recurring crash. A specific prior root cause cannot be claimed. The greenfield design removes the highest-probability Railway failure classes: wrong port binding, DB-dependent liveness, startup blocking on external services, unbounded DB pools, missing SIGTERM cleanup, full-film memory loads, ambiguous start command, and unstructured exception handling.

Current-platform constraint: Railway Config-as-Code via `railway.json` is deprecated in 2026; new services cannot opt into it, and legacy use has a December 1, 2026 cutoff. The requested `railway.json` is included as a compatibility artifact, but service settings/current Railway Infrastructure-as-Code must be treated as authoritative for a new deployment.

### Changes Made

Runtime: Python 3.12 + FastAPI + Uvicorn. Bind is `0.0.0.0:$PORT`.

Exact Docker start command: `exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --timeout-keep-alive 5`.

Exact Railway override if used: `/bin/sh -c "exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 5"`.

Liveness: `/health` returns JSON 200 without Postgres, object storage, model worker, or vendor calls.

Readiness: `/ready` checks Postgres with an 800ms query timeout and returns 503 on failure.

Database: asyncpg pool defaults to max 5 connections. Startup is not blocked on DB. A background maintainer reconnects with exponential backoff capped at 30 seconds. Loss of DB makes readiness fail without killing liveness.

Shutdown: FastAPI lifespan receives server shutdown, cancels the DB maintainer, drains/closes the pool, and logs shutdown completion. Uvicorn receives Railway SIGTERM and performs application lifespan shutdown before exit.

Exceptions: Python `sys.excepthook` covers uncaught process-level exceptions and the asyncio loop exception handler covers unobserved async task errors, the Python equivalents of Node `uncaughtException` / `unhandledRejection` handling.

Logs: JSON lines to stdout with timestamp, level, service, event, message, and request id where available.

Storage: Postgres stores clip metadata only. Clip bytes belong in S3-compatible object storage. No source-of-truth data is written to ephemeral container disk.

Environment variable names only: `DATABASE_URL`, `PORT`, `WEB_CONCURRENCY`, `DB_POOL_MAX`, `DB_CONNECT_TIMEOUT_SECONDS`, `LOG_LEVEL`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`.

Budget assumption: Railway Hobby is treated as required once the free/trial limits cannot support the DB, soak, and steady availability target. Cost must be checked against the actual Railway account before purchase rather than hard-coded into application logic.

### Verification

Local:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
PORT=8000 uvicorn app.main:app --host 0.0.0.0 --port 8000
curl -i http://127.0.0.1:8000/health
```

Expected liveness: HTTP 200 and JSON containing `"status":"ok"`.

Without `DATABASE_URL`, `curl -i http://127.0.0.1:8000/ready` must return HTTP 503. This is correct behavior.

With Postgres:

```bash
export DATABASE_URL='postgresql://...'
python scripts/seed.py
curl -i http://127.0.0.1:8000/ready
curl 'http://127.0.0.1:8000/api/v1/plays?offense=ATL%20Tech%20Owls&limit=20'
```

Expected seed output: JSON `{"status":"ok","plays_in_db":20}` on a fresh demo DB. Expected readiness: HTTP 200 with `database:"ok"`.

Performance acceptance: run a load test against the seeded/representative season-size DB. P95 20-play filter response must be <2s. Opponent report must be <5s. `/health` p99 must remain <1s while Postgres is intentionally unavailable. These are measured acceptance criteria, not claims this commit alone can prove.

Railway deploy checklist: create/link service; attach Railway Postgres; set `DATABASE_URL`; ensure service listens on injected `PORT`; set healthcheck path `/health`; use Dockerfile; set restart policy On Failure; use one web worker initially; deploy; confirm `/health`; confirm `/ready`; run schema/seed or migration separately; inspect JSON startup logs; send SIGTERM/redeploy and verify `graceful_shutdown_complete`; inspect memory during play filters; do not call a manual restart a fix.

### Prevention

Crash classification order: port binding -> startup/build -> healthcheck -> resource exhaustion -> concurrency blocking -> external service -> filesystem.

On every incident capture: deploy commit SHA, build log, first 200 runtime log lines, last 200 lines before exit, exit code/signal, memory peak, CPU peak, active DB connections, `/health` behavior, `/ready` behavior, and request path in flight.

Do not add synchronous film parsing to the API request path. Do not add a second web worker until DB connection math is recomputed. Do not increase pool size to hide slow queries. Do not make `/health` call Postgres. Do not write source-of-truth film or model artifacts to local disk. Do not retry external services without bounded exponential backoff. Do not suppress exceptions without structured logs.

Weekly reliability check: verify query latency, error rate, memory peak, DB pool saturation, slow query log, and object-storage error rate. Monthly: restore-test database backup, inspect dependency updates, rerun load baseline. Before each deploy: tests pass, schema change reviewed, health route unchanged or explicitly verified, start command still points to built artifact, no secret values committed.

30-day soak definition: zero process crashes; zero OOM kills; zero healthcheck failures caused by app code; no DB pool exhaustion; p99 `/health` <1s; no request path loads full-season film metadata into RAM. The criterion can only be marked passed after an actual uninterrupted 30-day observation window.

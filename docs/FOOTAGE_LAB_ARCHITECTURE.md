# FIELDMIND Footage Lab — Design Gate 0 (American Football)

**Status:** architecture proposal only. No footage processing code, accuracy claim, or live consumer feature is included in this pull request.

## Why this fits FIELDMIND

FIELDMIND's existing source of truth is the staff-reviewed **play**, linked to authorized film references and scoped by `program_id`. Add a private **Footage Lab** that emits reviewable, provenance-rich movement observations tied to those plays. Keep `app.pilot:app`, original migrations 001–007, program isolation, tag honesty rules, two-tagger review, and the current production API untouched.

The public Railway preview is not an authenticated footage uploader. Raw film will not be exposed via a public repository, a public preview page, or PostgreSQL.

### Coach journeys

- **Head Coach** — see the team's permitted film jobs, coverage/quality reports, and staff-review status.
- **Coordinator** — review a snap-to-end clip, field-calibrated mini-field and spacing/pursuit observations; use observations as coaching evidence, **never** automatic coverage, formation or personnel assignments.
- **Position Coach** — inspect position-specific movement tracks, quality flags and annotated teaching moments tied to a source frame.

An **Evidence Replay** control must link each number (e.g. maximum mph) to source timestamps, calibration landmarks, track continuity, identity votes, derivation/version and reviewer notes. If the evidence fails, hide or mark that number unavailable.

## Pipeline

```text
Authorized video/clip pointer -> program-scoped permission receipt
 -> private storage + queued job (or local offline clip)
 -> [1] stream decoder: actual fps, PTS, resolution
 -> [2] play segmenter: coach confirms snap and end
 -> [3] ground-field grid fit: hashes, numbered yard lines, sidelines
 -> [4] player/official/ball detector (commercially licensed weights)
 -> [5] track segments + ID-switch rejection + team/jersey evidence
 -> [6] ball-carrier/airborne-ball/unknown state
 -> [7] timestamped per-player kinematics
 -> per-play JSON, CSV, optional video overlay
 -> staff review -> source-backed FIELDMIND play evidence
```

**Engine boundary:** An isolated worker handles decoding and ML, not the FastAPI request thread. Film assets live in private object storage or locally, never as blobs in PostgreSQL. Signed URLs are short-lived; every artifact and job is `program_id`-scoped. Preserve uploader rights, data-retention controls, deletion/audit trail, particularly for youth video.

## Geometry (configurable by football level)

Field x coordinate in yards: 0–100 between goal lines, extended −10..110 through end zones. y coordinate: 0..53⅓ from a designated sideline. Record camera orientation and direction of play explicitly.

Hashes measured **from each sideline**:
- NFHS 11-player: **53 ft 4 in**; between hashes **53 ft 4 in**.
- NCAA: **60 ft**; between hashes **40 ft**.
- NFL: **70 ft 9 in**; between hashes **18 ft 6 in**.

References: [2026 NFL rulebook](https://operations.nfl.com/rules-officiating/2026-nfl-rulebook), [NCAA football rules/field diagram](https://www.ncaa.org/championships/playing-rules/football-playing-rules/), [2026 NFHS field diagrams](https://www.nfhs.org/resources/sports/football-field-diagrams-2026).

Each frame is calibrated against sufficient visible field landmarks. Fit homography with RANSAC; report inliers and reprojection error. Absolute x is unresolved if yard-line numbering cannot anchor the line grid. No unverified carry-over of stale camera geometry across pan/cut. Use ground/foot or ankle points, not airborne football projection.

## Stage contracts and honest quality

| Stage | Failure result | Required evidence |
|---|---|---|
| Ingest | invalid file/unknown timing -> no timing metrics | fps/time base, actual PTS, dimensions |
| Segmentation | unconfirmed snap -> no snap-relative metrics | snap/end frames and reviewer status |
| Field calibration | insufficient/ambiguous landmarks -> UNMEASURED location | per-frame transform/error/inliers |
| Detection | occluded player/ball -> nullable detection | detector/model version + confidence |
| Tracking | probable ID swap -> break segment | continuity and switch warnings |
| Identity | unreadable number -> anonymous segment | team, jersey votes, optional roster |
| Ball state | hidden handoff -> UNKNOWN carrier | positive observations only |
| Kinematics | zero dt/outlier/missing calibrated points -> withhold | source frame range, timestamped locations, uncertainty |
| Export | missing source/approval -> unverified record | artifact ID, review status, audit trail |

Per metric: `MEASURED` = calibrated source-supported observation (NOT a ground-truth accuracy guarantee); `ESTIMATED` = documented interpolation or uncertain evidence; `UNMEASURED` = unsupported/null + reason. The UI must default to showing only measured values, with an explainable toggle for estimates.

Tier 1: peak measured speed (mph + source timestamp/position); observed track distance (yards + fraction of visible play, not straight-line displacement); acceleration/deceleration; time to top measured speed from confirmed snap. Clip/field metrics must never use assumed 24 fps, arbitrary 70 px thresholds or a last-known possession fallback. Treat ~24 mph as a *diagnostic* upper sanity gate pending level-specific validation: flag instead of clipping.

Tier 2 **not in first build:** snap reaction/get-off, receiver separation at **verified** catch, snap-to-release, defender proximity proxy (not claimed as verified contact), pursuit closing speed.

Tier 3 **explicitly deferred:** formation/personnel/coverage inference, route family classification, sensor fusion, multiview 3D.

## Original failure evidence to prevent

Based on the user-provided `SPEC.md` and `FINDINGS.md` about the reference **soccer** project, not copied code:

- Ball absent in **472/750** frames (63%) -> use `unknown` ball state rather than interpolated possession.
- Only **67%** of player-frame positions inside one fixed mapped quad -> dynamic, quality-gated football landmark calibration.
- Reported maximum **58.3 km/h** from jitter/ID switches -> reject suspect segment and flag implausible motion; no false measurement.
- Fixed video fps and non-streaming decode -> stream actual timestamped source; constant-memory processing.
- Ball-absent frame 0 crash; 5-frame division-by-zero; tracker cache-only return -> dedicated zero/empty/uncached tests.
- Single-feature camera pan estimate -> robust multi-landmark fit; detect cuts.
- Arbitrary color cluster, hard-coded player ID -> multi-frame jersey/helmet roster votes with hysteresis and transparent unknowns.
- Hard-coded rendering pixel positions -> draw overlays relative to actual image dimensions.
- README claims vs existing code -> ship stage/validation status separately from conceptual scope.

The consultant review referenced inside the uploaded prompt was **not separately attached**, nor were film stills.

## Validation gate (before speed claims)

Provide three authorized sample plays (pre-snap, mid-play, pan) and manually label about five visible athletes per play every ten frames plus field landmarks, snap/end, and identity switches. Tune on one clip and report held-out **yard-coordinate error, mph error, valid-track coverage, calibration failure rate and ID switches** for remaining clips. Include deliberate failures: still person, along-yard-line motion, zero delta time, missing snap, a synthetic camera pan and injected ID swap. Until this runs, report **no measured accuracy**.

## Engineering order (one experienced engineer, indicative)

1. Rights/film-type/CPU-GPU intake and 3-play labeling: 1–3 days.
2. Timestamped bounded-memory decoder and manual snap/end: 2–3 days.
3. Configurable field-grid calibration and quality outputs: 3–6 days.
4. Licensed detector adapter, track segments and evidence reviewer: 4–8 days.
5. Smoothed kinematics/JSON/CSV and honest withheld values: 2–4 days.
6. Held-out validation and FIELDMIND evidence-link contract: 3–5 days.

**Estimate:** 15–29 engineering days, subject to film quality, compute and licenses.

## Commercial license and rights gate

The original reference repository README claims MIT, while the supplied findings report **no root LICENSE file**; do not assume those source files, datasets or weights are commercially licensed. Ultralytics offers **AGPL-3.0 and commercial licensing**; commercial/closed-source use requires a legal review or another appropriately licensed detector. Do not copy source code from the soccer pipeline or redistribute third-party game footage.

## Future schema/API (not implemented)

New, additive tables: `film_assets`, `film_processing_jobs`, `film_play_segments`, `film_track_segments`, `film_metric_observations`, `film_review_events`, `film_artifact_refs`. Add new migration numbers; preserve 001–007.

Proposed authenticated API: `POST /api/film/assets`; `POST /api/film/jobs`; `GET /api/film/jobs/{id}`; `GET /api/film/plays/{id}/tracks`; `POST /api/film/metrics/{id}/review`. None is presently deployed.

**Next input:** three stills from the same play: pre-snap, mid-play, hardest pan. Assess real yard-line/hash/number visibility and choose film type/level **before writing inference code**.

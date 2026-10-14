# Footage Lab Intake 001 — NFL Broadcast Highlight Test

**Status:** tested input source and prototype review only. No AI tracking inference, speed accuracy, or play-call classification. The original 317 MB video and extracted frames stay **out of GitHub**.

## Source checks

The user supplied a 67-minute football highlights MP4 for FIELDMIND Footage Lab proof-of-concept. Container inspection with `ffprobe`:

| Item | Observed |
|---|---|
| Video | H.264, 640×360, 30000/1001 (~29.97) fps |
| Frames | 120,590 |
| Audio | AAC |
| Duration | 4023.693 seconds (~1:07:03.7) |
| File size | 331,769,654 bytes |
| Camera | NFL Ravens broadcast highlights, wide pans mixed with zooms/replays/cuts |

**Source identity, footage redistribution rights, seasons and athlete identities have NOT been independently verified.**

## Sampled camera evidence

- **01:58–02:16** — wide pre-snap-to-action candidate; visible 20, 30, 40 and midfield numbering in portions of the pan; later angle change/replay. Manually confirm snap and end.
- **65:08–65:22** — midfield/field-numbered wide-play candidate, with zoom/camera pan. Edited transitions mean the interval is not guaranteed to be a single continuous play.
- **66:50–66:58** — zoomed formation/action segment with larger uniforms but less field context; useful for comparing identity visibility with spatial calibration.

Five-yard line grid, yard numbers, hashes and sidelines are visible in portions of the wide film; perspective, occlusion, camera cuts and 360p resolution prevent a truthful full-play field calibration at this stage. No full-resolution 1080p All-22, roster or labeled player-ground points were provided.

## Result: evidence gating

| Observation | Status | Reason |
|---|---|---|
| fps/dimensions | observed container metadata | ffprobe |
| NFL/broadcast style | observed image context | Ravens branding and television/edit changes |
| candidate play windows | ESTIMATED | manually selected sampled time ranges |
| exact snap/whistle | UNMEASURED | not annotated at frame precision |
| per-player field x/y | UNMEASURED | no homography fitted or tracked points |
| speed, distance, acceleration | UNMEASURED | requires verified continuous calibrated player tracks |
| identity and ball carrier | UNMEASURED | no validated OCR/roster/ball-state run |

## Prototype available separately

A single-file local **Footage Lab Review** HTML prototype was built and tested outside this repository against a three-second locally cropped video. It opens local footage, jumps to candidate timestamps, records snap/end boundaries, stores timestamped pixel-only field landmark labels, and exports JSON with withheld metrics. It does **not** call AI models or upload the video. Chromium smoke test passed these interactions and no JavaScript page errors appeared. Local file navigation was blocked by this testing environment; the HTML was tested by injecting its complete content into a headless Chromium page and selecting the cropped video.

## Next gate

Obtain ground-truth labels on at least one full, authorized play at source resolution. Confirm snap/end; label fixed field correspondences across several pan positions, player foot locations and identity-switch events. Report withheld measurements until both pixel-to-yard calibration and held-out kinematic error are evaluated.

**Production unchanged:** `app.pilot:app`, Railway backend, member login and private video storage are not modified in this design PR.

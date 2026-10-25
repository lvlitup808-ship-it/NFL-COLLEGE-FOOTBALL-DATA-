# FIELDMIND Tactical Simulator — isolated foundation

This feature branch adds a deterministic, bounded simulation kernel and tests. It does **not** expose unauthenticated endpoints, modify production entrypoints, or change database migrations.

## Reference and originality
Loom Pitch: https://html.moldandyeast.com/a/loom-pitch
The reference index describes a single-file football tactics DSL, graph compiler, 3D playback and agent iteration. This implementation is independently authored; it does not copy source code.

## Included
- Explicit offense/defense actors with yard-based coordinates
- Ordered timed waypoints and fixed-frame interpolation
- Input validation, finite bounds, frame and duration caps
- Geometric speed warnings and deterministic test fixtures

## Not yet included (do not claim completed)
- Browser 3D viewer, interactive play designer, graph compiler, sandboxed JS DSL
- Authenticated API integration, persistence, AI agent, film-based calibration
- Production deployment and browser end-to-end tests

## Architecture for next iteration
1. Add authenticated program-scoped `/api/v1/tactics` endpoints using existing wedge dependencies.
2. Add an AST-validated declarative DSL compiled to waypoint graphs. Never execute arbitrary user JavaScript on the server.
3. Implement a WebGL/Three.js field and playback controls as a separate UI surface.
4. Add agent tool calls restricted to validated play edits, simulation and diff review; require coach approval for writes.
5. Add unit, integration, adversarial authorization and Playwright browser tests.
6. Keep all tactical results labeled hypothetical until calibrated against authorized film evidence.

## Run
`python -m pytest -q tests/test_tactics_engine.py`

## Guardrails
Do not infer formation, motion, personnel, coverage or play family from raw play-by-play data. No athlete cognition scoring. Preserve the locked FIELDMIND pilot and the existing production entrypoint `app.pilot:app`.

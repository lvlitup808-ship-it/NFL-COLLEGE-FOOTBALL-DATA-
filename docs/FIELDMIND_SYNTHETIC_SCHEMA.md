# FIELDMIND synthetic scenario v1 — frozen contract

Version discriminator: `fieldmind-synthetic-v1`. This is synthetic planning data, never verified game evidence.

JSON object: `{"version":"fieldmind-synthetic-v1","synthetic":true,"name":"...","players":[...]}`.
The Studio currently requires exactly 14 players, ordered p1–p14. Each player has a nonempty name (maximum 80 characters), `id` p1 through p14, finite `x` and `y` between 0 and 100, and `routes` (array of at most 200 waypoints). Each waypoint has finite `x` and `y` between 0 and 100. Coordinates are normalized synthetic-field coordinates, not GPS, pixels, or observed footage coordinates.

Imports are atomic: reject malformed, oversized (>1 MiB), incorrectly versioned, or non-synthetic data without replacing the current routes. Export is JSON. Future schema changes must use a new version string and an explicit migration; never reinterpret this version silently.

The persistence API is program-scoped using existing Bearer token and X-Program-ID authentication. Do not use this schema to claim tracking, video calibration, or verified football observations.

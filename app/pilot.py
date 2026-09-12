"""Pilot entrypoint for the locked week-of-game wedge.

Imports the stable V1 app for DB lifecycle/health and replaces legacy /api/v1
surfaces with authenticated, program-scoped pilot routes. Health/readiness stay
unchanged and ingestion remains a one-off job.
"""
import os

from app.main import app
from app.wedge import router as wedge_router

# The 90-day pilot must not expose the legacy global read paths, cognition score
# surface, QB translation heuristic, or unauthenticated clip write path.
LEGACY_PREFIX = "/api/v1"
app.router.routes = [
    route
    for route in app.router.routes
    if not (
        getattr(route, "path", "").startswith(LEGACY_PREFIX)
        or (
            os.getenv("PILOT_HIDE_DOCS", "1") == "1"
            and getattr(route, "path", "") in {"/docs", "/redoc", "/openapi.json"}
        )
    )
]

app.include_router(wedge_router)

"""Pilot entrypoint for the locked week-of-game wedge.

Imports the stable V1 app for DB lifecycle/health and replaces legacy /api/v1
surfaces with authenticated, program-scoped pilot routes. Health/readiness stay
unchanged and ingestion remains a one-off job.
"""
import os
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.main import app
from app.security import MAX_REQUEST_BODY_BYTES, SecurityHeadersMiddleware
from app.wedge import router as wedge_router
from app.wedge_extra import router as wedge_extra_router

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
app.include_router(wedge_extra_router)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES)
app.add_middleware(SecurityHeadersMiddleware)

WEB_INDEX = Path(__file__).with_name("web") / "index.html"


@app.get("/", include_in_schema=False)
async def pilot_ui():
    return FileResponse(WEB_INDEX)


@app.get("/assets/pilot.js", include_in_schema=False)
async def pilot_script():
    # Explicit file route: no user-controlled filesystem path.
    return FileResponse(WEB_INDEX.with_name("pilot.js"), media_type="text/javascript")

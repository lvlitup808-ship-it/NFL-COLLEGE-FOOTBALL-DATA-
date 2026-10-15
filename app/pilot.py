"""Pilot entrypoint for the locked week-of-game wedge.

Imports the stable V1 app for DB lifecycle/health and replaces legacy /api/v1
surfaces with authenticated, program-scoped pilot routes. Health/readiness stay
unchanged and ingestion remains a one-off job.
"""
import os
from pathlib import Path

from fastapi.responses import FileResponse

from app.main import app
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

WEB_DIR = Path(__file__).with_name("web")
WEB_INDEX = WEB_DIR / "index.html"
FAVICON = WEB_DIR / "favicon.svg"


@app.get("/", include_in_schema=False)
async def pilot_ui():
    return FileResponse(WEB_INDEX)


# Browsers probe /favicon.ico even when the page links the SVG; without an answer
# they fall back to a blurry default globe in the tab.
@app.get("/favicon.svg", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(FAVICON, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

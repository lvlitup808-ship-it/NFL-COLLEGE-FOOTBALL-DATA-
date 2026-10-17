"""HTTP controls for the same-origin, bearer-authenticated pilot."""
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The pilot accepts JSON metadata, not video uploads. Count streamed bytes too.
MAX_REQUEST_BODY_BYTES = 1024 * 1024


def security_headers(scope: Scope) -> dict[str, str]:
    headers = {
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'self'; script-src-attr 'none'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "media-src https:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        ),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cache-Control": "no-store",
    }
    # Trust only the ASGI scheme set by the server's configured trusted proxy.
    # Never read a client-supplied X-Forwarded-Proto here.
    if scope.get("scheme") == "https":
        headers["Strict-Transport-Security"] = "max-age=31536000"
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).update(security_headers(scope))
            await send(message)

        await self.app(scope, receive, send_secured)

"""Request-ID propagation and structured access logging (pure ASGI, so it also wraps errors)."""

import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.stdlib.get_logger("glideup.access")

REQUEST_ID_HEADER = "x-request-id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_QUIET_PATHS = {"/healthz", "/readyz", "/metrics"}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        # Accept a caller's id only if it looks sane; never log attacker-controlled junk.
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if scope["path"] not in _QUIET_PATHS:
                logger.info(
                    "http_request",
                    method=scope["method"],
                    path=scope["path"],
                    status=status_code,
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                )
            structlog.contextvars.clear_contextvars()


_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    # The API only serves JSON; docs pages get a relaxed policy below.
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
]
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
_TOO_LARGE = b'{"error":{"code":"payload_too_large","message":"Request body is too large"}}'


class SecurityHeadersMiddleware:
    """Hardening headers on every response, and a request body size limit (413)."""

    def __init__(self, app: ASGIApp, *, max_body: int, max_upload: int, hsts: bool) -> None:
        self.app = app
        self.max_body = max_body
        self.max_upload = max_upload
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        limit = self.max_upload if path.rstrip("/").endswith("/resumes") else self.max_body
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > limit:
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": _TOO_LARGE})
            return
        docs = path.startswith(_DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS:
                    if docs and name == b"content-security-policy":
                        continue  # Swagger UI loads its own scripts
                    if name.decode() not in headers:
                        headers.append(name.decode(), value.decode())
                if self.hsts:
                    headers.append(_HSTS[0].decode(), _HSTS[1].decode())
            await send(message)

        await self.app(scope, receive, send_with_headers)

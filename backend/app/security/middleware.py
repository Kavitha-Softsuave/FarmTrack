"""Pure-ASGI middleware: request id, access log (+ last-resort 500), security headers, request body size limit.

Stack order (outermost first): SecurityHeaders -> RequestId -> AccessLog -> BodySizeLimit -> CORS -> routes. AccessLog sits inside
RequestId and SecurityHeaders so even the 500 it produces carries the request id and the security headers.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from app.security.errors import error_body
from app.security.logging import request_id_var

logger = logging.getLogger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_NO_CSP_PREFIXES = ("/admin/", "/docs", "/redoc", "/openapi.json")     # server-rendered admin pages and Swagger need scripts


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


async def _send_json(send: Send, status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> None:
    payload = json.dumps(body).encode()
    raw = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    raw += [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": raw})
    await send({"type": "http.response.body", "body": payload})


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, b"x-request-id")
        request_id = incoming if incoming and _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)


class AccessLogMiddleware:
    """Logs method, path, status and duration (never the query string or body); turns an unhandled error into a clean 500."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_logged(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_logged)
        except Exception:
            logger.exception("unhandled error method=%s path=%s", scope["method"], scope["path"])
            if response_started:
                raise
            await _send_json(send_logged, 500, error_body(
                "internal_error", "Something went wrong. Please try again.",
                {"request_id": scope.get("state", {}).get("request_id")}))
        finally:
            logger.info("request", extra={"method": scope["method"], "path": scope["path"], "status": status,
                                          "duration_ms": round((time.perf_counter() - started) * 1000, 1)})


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {k.lower() for k, _ in headers}
                wanted = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                }
                if not path.startswith("/audio/"):
                    wanted[b"cache-control"] = b"no-store"
                if not path.startswith(_NO_CSP_PREFIXES):
                    wanted[b"content-security-policy"] = b"default-src 'none'; frame-ancestors 'none'"
                if self.hsts:
                    wanted[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                headers.extend((k, v) for k, v in wanted.items() if k not in present)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _BodyTooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    """Reject oversized requests before the multipart parser spools them to disk (Content-Length and streamed bytes).

    FastAPI turns any error raised while it reads the body into its own 400, so once the limit is crossed this middleware
    replaces whatever the application answers with the 413.
    """

    def __init__(self, app: ASGIApp, max_bytes: int, other_max_bytes: int = 1024 * 1024) -> None:
        self.app = app
        self.max_bytes = max_bytes                  # photo uploads (multipart)
        self.other_max_bytes = other_max_bytes      # every other body (JSON and forms are tiny)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        multipart = (_header(scope, b"content-type") or "").lower().startswith("multipart/form-data")
        limit = self.max_bytes if multipart else self.other_max_bytes
        declared = _header(scope, b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reject(send, limit)
            return
        received = 0
        exceeded = False
        rejected = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLargeError
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal rejected
            if not exceeded:
                await send(message)
            elif not rejected:                                   # answer 413 once, swallow the application's own response
                rejected = True
                await self._reject(send, limit)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _BodyTooLargeError:
            if not rejected:
                await self._reject(send, limit)

    async def _reject(self, send: Send, limit: int) -> None:
        await _send_json(send, 413, error_body("payload_too_large", f"The upload is larger than {max(limit // (1024 * 1024), 1)} MB.",
                                               {"max_bytes": limit}))

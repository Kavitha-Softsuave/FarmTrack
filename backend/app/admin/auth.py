"""Cookie session and CSRF protection for the server-rendered admin pages.

Login: the operator posts the admin API key once; the server answers with a signed, expiring session cookie (HttpOnly,
SameSite=Strict, Secure in prod, path /admin). The key itself is never stored in the cookie or rendered in a page.
Forms carry a CSRF token derived from the session (HMAC), and the Origin header must match the Host when the browser sends it.
The session key is derived from SECRET_KEY and ADMIN_API_KEY, so rotating either one signs everybody out.
Settings come from `app.state.settings` (set by create_app) and fall back to get_settings().
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import Depends, Form, HTTPException, Request

from app.config import Settings, get_settings

COOKIE_NAME = "ft_admin"
COOKIE_PATH = "/admin"
SESSION_SECONDS = 8 * 3600
LOGIN_FAILURES = 5
LOGIN_WINDOW_SECONDS = 300
MAX_TRACKED_ADDRESSES = 10_000


def settings_of(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


@dataclass(frozen=True)
class AdminSession:
    nonce: str
    expires: int


def _sign(settings: Settings, text: str) -> str:
    key = hashlib.sha256(f"farmtrack-admin|{settings.secret_key}|{settings.admin_api_key}".encode()).digest()
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()


def key_matches(settings: Settings, candidate: str) -> bool:
    return hmac.compare_digest(candidate.encode(), settings.admin_api_key.encode())


def issue_session(settings: Settings, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + SESSION_SECONDS)
    payload = f"{expires}.{secrets.token_hex(16)}"
    return f"{payload}.{_sign(settings, payload)}"


def read_session(settings: Settings, cookie: str | None, now: float | None = None) -> AdminSession | None:
    if not cookie:
        return None
    payload, _, signature = cookie.rpartition(".")
    if not payload or not hmac.compare_digest(signature.encode(), _sign(settings, payload).encode()):
        return None
    expires_text, _, nonce = payload.partition(".")
    if not expires_text.isdigit() or not nonce:
        return None
    if int(expires_text) < (time.time() if now is None else now):
        return None
    return AdminSession(nonce=nonce, expires=int(expires_text))


def csrf_token(settings: Settings, session: AdminSession) -> str:
    return _sign(settings, f"csrf|{session.nonce}")


# ------------------------------------------------------------------------------------------------- brute-force guard
class LoginThrottle:
    """Blocks an address after LOGIN_FAILURES failed logins within the window (process-local, like the other limiters)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, who: str) -> deque[float]:
        hits = self._failures[who]
        cutoff = self._clock() - LOGIN_WINDOW_SECONDS
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def blocked(self, who: str) -> bool:
        with self._lock:
            blocked = len(self._recent(who)) >= LOGIN_FAILURES
            if not self._failures[who]:
                del self._failures[who]
            return blocked

    def fail(self, who: str) -> None:
        with self._lock:
            self._recent(who).append(self._clock())
            if len(self._failures) > MAX_TRACKED_ADDRESSES:        # many different source addresses: forget the expired ones
                cutoff = self._clock() - LOGIN_WINDOW_SECONDS
                for key in [k for k, v in self._failures.items() if not v or v[-1] <= cutoff]:
                    del self._failures[key]
                while len(self._failures) > MAX_TRACKED_ADDRESSES:
                    del self._failures[next(iter(self._failures))]

    def reset(self, who: str | None = None) -> None:
        with self._lock:
            if who is None:
                self._failures.clear()
            else:
                self._failures.pop(who, None)


login_throttle = LoginThrottle()


# ------------------------------------------------------------------------------------------------- dependencies
def optional_session(request: Request) -> AdminSession | None:
    return read_session(settings_of(request), request.cookies.get(COOKIE_NAME))


def require_session(session: AdminSession | None = Depends(optional_session)) -> AdminSession:
    if session is None:
        raise HTTPException(status_code=303, detail="login required", headers={"Location": "/admin/login"})
    return session


def check_origin(request: Request) -> None:
    """Browsers send Origin on form posts: refuse one that is not this site."""
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "cross-origin request refused")


def csrf_protect(request: Request, session: AdminSession = Depends(require_session), csrf: str = Form("")) -> AdminSession:
    check_origin(request)
    if not hmac.compare_digest(csrf.encode(), csrf_token(settings_of(request), session).encode()):
        raise HTTPException(403, "form expired or invalid: reload the page and try again")
    return session

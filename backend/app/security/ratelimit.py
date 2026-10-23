"""In-memory sliding-window rate limiting.

PRODUCTION NOTE: state lives in this process only. With more than one worker or replica each process counts separately, so the
effective limit is multiplied and a restart resets it. Production should back these limiters with Redis (same `hit` contract).
Client IPs behind a reverse proxy need uvicorn's --proxy-headers/--forwarded-allow-ips so `request.client` is the real client;
many farmers share one carrier-grade NAT address, so the per-IP limits are deliberately generous and the per-phone limits strict.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from app.security.errors import ApiError


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after: float = 0.0


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = 50_000) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> RateDecision:
        """Record one attempt for `key` unless the window is full. Denied attempts are not recorded."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            cutoff = now - self.window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return RateDecision(False, max(hits[0] + self.window - now, 0.0))
            hits.append(now)
            if len(self._hits) > self._max_keys:
                self._sweep(cutoff)
            return RateDecision(True)

    def peek(self, key: str) -> RateDecision:
        """Is the window for `key` already full? Records nothing (use it to refuse BEFORE a secret is compared)."""
        now = self._clock()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return RateDecision(True)
            cutoff = now - self.window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return RateDecision(False, max(hits[0] + self.window - now, 0.0))
            return RateDecision(True)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _sweep(self, cutoff: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[key]
        while len(self._hits) > self._max_keys:          # still full of live keys: drop the oldest-inserted
            del self._hits[next(iter(self._hits))]


def enforce(limiter: SlidingWindowLimiter, key: str, message: str = "Too many requests. Please wait and try again.") -> None:
    decision = limiter.hit(key)
    if not decision.allowed:
        wait = max(int(decision.retry_after) + 1, 1)
        raise ApiError(429, "rate_limited", message, {"retry_after_seconds": wait}, headers={"Retry-After": str(wait)})


def enforce_open(limiter: SlidingWindowLimiter, key: str, message: str = "Too many requests. Please wait and try again.") -> None:
    """Like `enforce` but only checks (records nothing): for limiters that count FAILURES, so that once the window is full
    even the right secret is refused and the limit cannot be out-guessed."""
    decision = limiter.peek(key)
    if not decision.allowed:
        wait = max(int(decision.retry_after) + 1, 1)
        raise ApiError(429, "rate_limited", message, {"retry_after_seconds": wait}, headers={"Retry-After": str(wait)})


@dataclass
class RateLimiters:
    otp_phone: SlidingWindowLimiter
    otp_ip: SlidingWindowLimiter
    verify_ip: SlidingWindowLimiter
    refresh_ip: SlidingWindowLimiter
    admin_fail_ip: SlidingWindowLimiter
    ask_farmer: SlidingWindowLimiter
    scan_farmer: SlidingWindowLimiter
    # WRONG verification codes per phone number, over all of its code requests (the per-code attempt cap alone lets an attacker
    # who may request 3 codes per 15 minutes keep guessing for ever)
    verify_phone_fail: SlidingWindowLimiter = field(default_factory=lambda: SlidingWindowLimiter(10, 3600.0))
    # Password login: every attempt per IP, and only the WRONG passwords per (lower-cased) username, so a right password cannot
    # out-guess the limit and a real farmer's good logins never use up the budget.
    login_ip: SlidingWindowLimiter = field(default_factory=lambda: SlidingWindowLimiter(20, 600.0))
    login_user_fail: SlidingWindowLimiter = field(default_factory=lambda: SlidingWindowLimiter(8, 600.0))

    @classmethod
    def default(cls) -> RateLimiters:
        ten_min, fifteen_min = 600.0, 900.0
        return cls(
            otp_phone=SlidingWindowLimiter(3, fifteen_min),       # OTP SMS per phone: the real brute-force and SMS-cost guard
            otp_ip=SlidingWindowLimiter(60, fifteen_min),
            verify_ip=SlidingWindowLimiter(120, fifteen_min),
            refresh_ip=SlidingWindowLimiter(120, ten_min),
            admin_fail_ip=SlidingWindowLimiter(10, ten_min),      # failed X-Admin-Key attempts per IP
            ask_farmer=SlidingWindowLimiter(20, ten_min),         # LLM cost guard
            scan_farmer=SlidingWindowLimiter(30, ten_min),        # vision/LLM cost guard
        )

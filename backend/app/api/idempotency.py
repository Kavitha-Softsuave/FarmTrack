"""`Idempotency-Key` support for the create routes the mobile offline queue may replay (scan, spray log, expert request).

The app sends one random key (a UUID) per queued action and reuses it on every retry. The first request stores the key on the
row it creates; a replay by the same farmer returns that row's stored response (same ids, 200, header `Idempotent-Replayed: true`)
and does not create a second row, call the vision models or the LLM again, or write to Zoho again. Keys are per farmer: another
farmer sending the same key does not collide.

Two layers guard against two requests carrying the same key at the same time (a retry that arrives while the first is still being
processed): an in-process lock per (route, farmer, key) makes the second one wait and then replay, and the database's unique index
on (farmer_id, client_request_id) is the backstop across processes (the loser rolls back and returns the stored row).
"""
from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Header

from app.security.errors import ApiError

HEADER_NAME = "Idempotency-Key"
REPLAY_HEADER = "Idempotent-Replayed"
MAX_KEY_LENGTH = 80                              # the width of the client_request_id columns
KEY_RE = re.compile(rf"^[A-Za-z0-9._:-]{{8,{MAX_KEY_LENGTH}}}$")

HEADER_DESCRIPTION = (
    "Optional. A random string (a UUID is ideal, 8 to 80 characters of A-Z a-z 0-9 . _ : -) that identifies this one action. "
    "Send the same key when the app retries after a lost response or from its offline queue: the server then returns the "
    "original result (same ids, 200, header `Idempotent-Replayed: true`) and never creates a second record, repeats the analysis "
    "or writes to Zoho twice. Keys are scoped to the logged-in farmer. A key identifies the first request only: reusing it for "
    "different content returns the first result."
)


def idempotency_key(
    key: str | None = Header(default=None, alias=HEADER_NAME, description=HEADER_DESCRIPTION, examples=["0b8f3a52-6f0e-4a57-9d5d-0c1c7d6a9f10"]),
) -> str | None:
    """FastAPI dependency: the validated key, or None when the header is absent or blank."""
    if key is None or not key.strip():
        return None
    key = key.strip()
    if not KEY_RE.match(key):
        raise ApiError(400, "invalid_idempotency_key",
                       f"{HEADER_NAME} must be 8 to {MAX_KEY_LENGTH} characters: letters, digits and . _ : -")
    return key


class KeyedLocks:
    """One lock per name, created on demand and forgotten when nobody uses it any more."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, tuple[threading.Lock, int]] = {}

    @contextmanager
    def hold(self, name: str) -> Iterator[None]:
        with self._guard:
            lock, users = self._locks.get(name, (threading.Lock(), 0))
            self._locks[name] = (lock, users + 1)
        try:
            with lock:
                yield
        finally:
            with self._guard:
                lock, users = self._locks[name]
                if users <= 1:
                    del self._locks[name]
                else:
                    self._locks[name] = (lock, users - 1)


_locks = KeyedLocks()


@contextmanager
def serialised(scope: str, farmer_id: str, key: str | None) -> Iterator[None]:
    """Run the body alone for this (route, farmer, key); a no-op without a key."""
    if key is None:
        yield
        return
    with _locks.hold(f"{scope}:{farmer_id}:{key}"):
        yield

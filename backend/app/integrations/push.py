"""Push notification providers. LogPushProvider is the default (dev, tests, demo); FcmPushProvider is an UNTESTED skeleton
for Firebase Cloud Messaging HTTP v1 (service-account JWT, RS256).
"""
from __future__ import annotations

import importlib.util
import json
import logging
import time
from pathlib import Path

import httpx
import jwt

from app.integrations.errors import IntegrationError, NotConfigured

log = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105  public Google endpoint, not a secret


def _has_cryptography() -> bool:
    return importlib.util.find_spec("cryptography") is not None


def _redact(token: str) -> str:
    return f"***{token[-4:]}" if len(token) > 8 else "***"


class LogPushProvider:
    """Writes one redacted log line per push (no body text, no full token) and reports success."""

    def send(self, token: str, title: str, body: str, data: dict[str, str] | None = None) -> bool:
        log.info("push (log provider) device=%s title=%r body_chars=%d data_keys=%s", _redact(token), title, len(body),
                 sorted(data or {}))
        return True


class FcmPushProvider:
    """FCM HTTP v1. UNTESTED against Firebase. Needs a service-account JSON file (settings.fcm_credentials_file) and the
    `cryptography` package (PyJWT RS256). Without either, construction raises NotConfigured."""

    def __init__(self, credentials_file: str | None, client: httpx.Client | None = None, clock=time.time) -> None:  # noqa: ANN001
        if not credentials_file:
            raise NotConfigured("FCM push selected (PUSH_PROVIDER=fcm) but FCM_CREDENTIALS_FILE is not set")
        if not _has_cryptography():
            raise NotConfigured("FCM push needs the 'cryptography' package for RS256 signing: pip install cryptography")
        try:
            info = json.loads(Path(credentials_file).read_text(encoding="utf-8"))
            self._email: str = info["client_email"]
            self._private_key: str = info["private_key"]
            self._project: str = info["project_id"]
            self._token_uri: str = info.get("token_uri", DEFAULT_TOKEN_URI)
        except (OSError, ValueError, KeyError) as exc:
            raise NotConfigured(f"FCM credentials file is unreadable or incomplete: {type(exc).__name__}") from exc
        self._http = client or httpx.Client(timeout=10.0)
        self._clock = clock
        self._access: str | None = None
        self._access_expires = 0.0

    def _access_token(self) -> str:
        now = self._clock()
        if self._access and now < self._access_expires - 60:
            return self._access
        assertion = jwt.encode({"iss": self._email, "scope": FCM_SCOPE, "aud": self._token_uri, "iat": int(now), "exp": int(now) + 3600},
                               self._private_key, algorithm="RS256")
        resp = self._http.post(self._token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
        token = resp.json().get("access_token") if resp.status_code == 200 else None
        if not token:
            raise IntegrationError(f"FCM token request refused (HTTP {resp.status_code})")
        self._access, self._access_expires = token, now + 3300
        return token

    def send(self, token: str, title: str, body: str, data: dict[str, str] | None = None) -> bool:
        message = {"token": token, "notification": {"title": title, "body": body},
                   "data": {k: str(v) for k, v in (data or {}).items()}, "android": {"priority": "high"}}
        try:
            resp = self._http.post(f"https://fcm.googleapis.com/v1/projects/{self._project}/messages:send",
                                   headers={"Authorization": f"Bearer {self._access_token()}"}, json={"message": message})
        except (httpx.HTTPError, IntegrationError) as exc:
            log.warning("fcm push failed device=%s: %s", _redact(token), type(exc).__name__)
            return False
        if resp.status_code != 200:
            log.warning("fcm push refused device=%s http=%d", _redact(token), resp.status_code)
            return False
        return True

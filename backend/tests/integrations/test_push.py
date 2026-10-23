import json
import logging

import httpx
import pytest

from app.integrations import push
from app.integrations.errors import NotConfigured
from app.integrations.push import FcmPushProvider, LogPushProvider
from app.interfaces import PushProvider


def test_log_provider_returns_true_and_logs_a_redacted_line(caplog):
    provider = LogPushProvider()
    assert isinstance(provider, PushProvider)
    with caplog.at_level(logging.INFO, logger="app.integrations.push"):
        assert provider.send("fcm-token-SECRET-1234", "Rain alert", "Spray again within 7 days for Dinesh", {"alert_id": "a1"}) is True
    text = caplog.text
    assert "Rain alert" in text and "***1234" in text
    assert "SECRET" not in text and "Dinesh" not in text and "fcm-token" not in text
    assert "alert_id" in text


def test_log_provider_short_token_is_fully_hidden(caplog):
    with caplog.at_level(logging.INFO, logger="app.integrations.push"):
        LogPushProvider().send("abc", "t", "b")
    assert "abc" not in caplog.text.replace("title", "")


def test_fcm_requires_a_credentials_file():
    with pytest.raises(NotConfigured, match="FCM_CREDENTIALS_FILE"):
        FcmPushProvider(None)


def test_fcm_requires_the_cryptography_package(monkeypatch, tmp_path):
    monkeypatch.setattr(push, "_has_cryptography", lambda: False)
    with pytest.raises(NotConfigured, match="cryptography"):
        FcmPushProvider(str(tmp_path / "sa.json"))


def test_fcm_rejects_unreadable_or_incomplete_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(push, "_has_cryptography", lambda: True)
    with pytest.raises(NotConfigured, match="unreadable"):
        FcmPushProvider(str(tmp_path / "missing.json"))
    incomplete = tmp_path / "sa.json"
    incomplete.write_text(json.dumps({"client_email": "x@y"}), encoding="utf-8")
    with pytest.raises(NotConfigured, match="incomplete"):
        FcmPushProvider(str(incomplete))


class Fcm:
    """Records requests; signing is stubbed because the test environment has no `cryptography` (the real path is untested)."""

    def __init__(self, send_status=200):
        self.requests: list[httpx.Request] = []
        self.send_status = send_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "ya29.test", "expires_in": 3600})
        return httpx.Response(self.send_status, json={"name": "projects/p/messages/1"})


@pytest.fixture
def provider_factory(monkeypatch, tmp_path):
    monkeypatch.setattr(push, "_has_cryptography", lambda: True)
    monkeypatch.setattr(push.jwt, "encode", lambda payload, key, algorithm: f"signed:{algorithm}:{payload['iss']}")
    creds = tmp_path / "sa.json"
    creds.write_text(json.dumps({"client_email": "svc@proj.iam", "private_key": "KEY", "project_id": "proj-1"}), encoding="utf-8")

    def make(transport: Fcm, clock=lambda: 1000.0) -> FcmPushProvider:
        return FcmPushProvider(str(creds), client=httpx.Client(transport=httpx.MockTransport(transport)), clock=clock)

    return make


def test_fcm_sends_a_v1_message(provider_factory):
    fcm = Fcm()
    assert provider_factory(fcm).send("device-token", "Title", "Body", {"alert_id": 7}) is True
    token_req, send_req = fcm.requests
    assert b"assertion=signed%3ARS256%3Asvc%40proj.iam" in token_req.content
    assert str(send_req.url) == "https://fcm.googleapis.com/v1/projects/proj-1/messages:send"
    assert send_req.headers["authorization"] == "Bearer ya29.test"
    message = json.loads(send_req.content)["message"]
    assert message["token"] == "device-token"
    assert message["notification"] == {"title": "Title", "body": "Body"}
    assert message["data"] == {"alert_id": "7"}


def test_fcm_reuses_the_access_token_until_it_expires(provider_factory):
    fcm, now = Fcm(), [1000.0]
    provider = provider_factory(fcm, clock=lambda: now[0])
    provider.send("t", "a", "b")
    provider.send("t", "a", "b")
    assert [r.url.host for r in fcm.requests].count("oauth2.googleapis.com") == 1
    now[0] += 4000
    provider.send("t", "a", "b")
    assert [r.url.host for r in fcm.requests].count("oauth2.googleapis.com") == 2


def test_fcm_refusal_returns_false_without_raising(provider_factory, caplog):
    with caplog.at_level(logging.WARNING, logger="app.integrations.push"):
        assert provider_factory(Fcm(send_status=404)).send("device-token-1234", "a", "b") is False
    assert "device-token" not in caplog.text and "***1234" in caplog.text


def test_fcm_token_refusal_returns_false(provider_factory):
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_grant"})

    provider = provider_factory(refuse)
    assert provider.send("t", "a", "b") is False

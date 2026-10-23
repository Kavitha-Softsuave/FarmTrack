"""Idempotency-Key on the create routes (scan, spray log, expert request): the mobile offline queue replays them."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.api.idempotency import KeyedLocks
from app.db.models import AuditLogRow, ExpertRequestRow, ReviewTaskRow, ScanRow, SprayLogRow
from app.db.session import session_scope
from app.services.scan_service import ScanService
from app.services.spray_service import SprayService
from tests.imaging import photo_files

KEY = "0b8f3a52-6f0e-4a57-9d5d-0c1c7d6a9f10"
REPLAY = "Idempotent-Replayed"


def post_scan(client, auth, key=KEY, **form):
    headers = {**auth, **({"Idempotency-Key": key} if key else {})}
    return client.post("/v1/scans", files=photo_files(1), data=form, headers=headers)


def post_spray(client, auth, key=KEY, **body):
    headers = {**auth, **({"Idempotency-Key": key} if key else {})}
    return client.post("/v1/spray-logs", json={"crop_id": "Apple", "product_id": "P012", **body}, headers=headers)


def post_expert(client, auth, key=KEY, **body):
    headers = {**auth, **({"Idempotency-Key": key} if key else {})}
    return client.post("/v1/expert-requests", json={"message": "please call", **body}, headers=headers)


def count(model) -> int:
    with session_scope() as db:
        return db.scalar(select(func.count()).select_from(model)) or 0


def stored_photos(fake_container) -> list:
    return [p for p in (fake_container.settings.storage_dir / "photos").rglob("*") if p.is_file()]


# ------------------------------------------------------------------------------------------------ scans
def test_replaying_a_scan_returns_the_original_without_repeating_any_work(api_client, auth, fake_container):
    first = post_scan(api_client, auth)
    again = post_scan(api_client, auth)
    assert first.status_code == 200 and again.status_code == 200
    assert again.json() == first.json() and again.json()["id"] == first.json()["id"]
    assert again.json()["advice"]["id"] == first.json()["advice"]["id"]
    assert REPLAY not in first.headers and again.headers[REPLAY] == "true"
    assert count(ScanRow) == 1 and len(stored_photos(fake_container)) == 1
    assert len(fake_container.crop_identifier.calls) == 1 and len(fake_container.disease_classifier.calls) == 1   # no second model run
    assert len(fake_container.composer.calls) == 1
    assert len(fake_container.zoho.diagnoses) == 1                                                    # no second Zoho write


def test_the_replayed_scan_shows_what_happened_to_it_since(api_client, auth, fake_container):
    from app.domain.types import CropResult

    fake_container.crop_identifier.result = CropResult(crop_id="Apple", confidence=0.3, needs_confirmation=True, source="stub")
    first = post_scan(api_client, auth).json()
    assert first["status"] == "confirm_crop"
    api_client.post(f"/v1/scans/{first['id']}/crop", json={"crop_id": "Apple"}, headers=auth)
    replay = post_scan(api_client, auth).json()
    assert replay["id"] == first["id"] and replay["status"] != "confirm_crop"                           # the stored, current result


def test_scans_without_a_key_or_with_different_keys_are_separate(api_client, auth):
    ids = {post_scan(api_client, auth, key=None).json()["id"], post_scan(api_client, auth, key=None).json()["id"],
           post_scan(api_client, auth, key="a" * 16).json()["id"], post_scan(api_client, auth, key="b" * 16).json()["id"]}
    assert len(ids) == 4 and count(ScanRow) == 4


def test_two_farmers_may_use_the_same_key(api_client, auth, login):
    mine = post_scan(api_client, auth)
    theirs = post_scan(api_client, login("+910000000002"))
    assert mine.json()["id"] != theirs.json()["id"] and REPLAY not in theirs.headers
    assert count(ScanRow) == 2
    with session_scope() as db:
        assert {r.farmer_id for r in db.scalars(select(ScanRow))} == {"F001", "F002"}
        assert {r.client_request_id for r in db.scalars(select(ScanRow))} == {KEY}
    assert post_scan(api_client, login("+910000000002")).json()["id"] == theirs.json()["id"]        # and each replays its own


def test_a_replay_does_not_use_the_rate_limit_or_read_the_upload(api_client, auth, api_app):
    from app.security.ratelimit import RateLimiters, SlidingWindowLimiter

    limiters = RateLimiters.default()
    limiters.scan_farmer = SlidingWindowLimiter(1, 600)
    api_app.state.limiters = limiters
    assert post_scan(api_client, auth).status_code == 200
    assert post_scan(api_client, auth, key="c" * 16).status_code == 429
    assert [post_scan(api_client, auth).status_code for _ in range(3)] == [200, 200, 200]            # replays are free


@pytest.mark.parametrize("key", ["short", "x" * 81, "has space in it!", "emoji-é-key-12345"])
def test_a_malformed_key_is_refused(api_client, auth, key):
    response = api_client.post("/v1/scans", files=photo_files(1), headers={**auth, "Idempotency-Key": key.encode("utf-8")})
    assert response.status_code == 400 and response.json()["code"] == "invalid_idempotency_key"
    assert count(ScanRow) == 0


@pytest.mark.parametrize("path,kwargs", [("/v1/scans", {"files": photo_files(1)}), ("/v1/spray-logs", {"json": {"crop_id": "Apple", "product_id": "P012"}}),
                                         ("/v1/expert-requests", {"json": {"message": "x"}})])
def test_login_comes_before_the_key_check(api_client, path, kwargs):
    response = api_client.post(path, headers={"Idempotency-Key": "bad"}, **kwargs)
    assert response.status_code == 401 and response.json()["code"] == "not_authenticated"


def test_a_blank_key_means_no_key(api_client, auth):
    first = api_client.post("/v1/scans", files=photo_files(1), headers={**auth, "Idempotency-Key": "  "})
    second = api_client.post("/v1/scans", files=photo_files(1), headers={**auth, "Idempotency-Key": "  "})
    assert first.status_code == second.status_code == 200 and first.json()["id"] != second.json()["id"]


def test_a_scan_that_lost_the_race_returns_the_winner_and_leaves_nothing_behind(api_client, auth, fake_container, monkeypatch):
    winner = post_scan(api_client, auth)
    photos_before = stored_photos(fake_container)
    real, calls = ScanService.find_by_request_id, {"n": 0}

    def lookup(self, farmer, key):                                   # the first lookup (before the work) misses: a true race
        calls["n"] += 1
        return None if calls["n"] == 1 else real(self, farmer, key)

    monkeypatch.setattr(ScanService, "find_by_request_id", lookup)
    loser = post_scan(api_client, auth)
    assert loser.status_code == 200 and loser.json()["id"] == winner.json()["id"]
    assert count(ScanRow) == 1 and count(ReviewTaskRow) == 0
    assert stored_photos(fake_container) == photos_before                                          # the loser's photo was removed
    assert len(fake_container.zoho.diagnoses) == 1                                                  # and it never wrote to Zoho
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(AuditLogRow).where(AuditLogRow.action == "scan.evaluated")) == 1


def test_simultaneous_uploads_with_one_key_run_the_pipeline_once(api_client, auth, fake_container):
    original = fake_container.disease_classifier.classify

    def slow(images, crop_id):
        time.sleep(0.4)
        return original(images, crop_id)

    fake_container.disease_classifier.classify = slow
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: post_scan(api_client, auth), range(3)))
    assert [r.status_code for r in responses] == [200, 200, 200]
    assert len({r.json()["id"] for r in responses}) == 1
    assert sum(1 for r in responses if r.headers.get(REPLAY) == "true") == 2
    assert len(fake_container.disease_classifier.calls) == 1 and count(ScanRow) == 1
    assert len(stored_photos(fake_container)) == 1


# ------------------------------------------------------------------------------------------------ spray logs
def test_replaying_a_spray_log_returns_the_original_and_writes_nothing_twice(api_client, auth, fake_container):
    first = post_spray(api_client, auth)
    again = post_spray(api_client, auth)
    assert first.status_code == again.status_code == 200
    assert again.json() == first.json() and again.headers[REPLAY] == "true" and REPLAY not in first.headers
    assert count(SprayLogRow) == 1 and len(fake_container.zoho.spray_writes) == 1
    assert len(fake_container.rules.spray_checks) == 1
    assert len(api_client.get("/v1/spray-logs", headers=auth).json()) == 1


def test_a_replayed_spray_log_keeps_its_warnings_and_speech(api_client, auth, fake_container):
    first = post_spray(api_client, auth, product_id=None, free_text="Local mix").json()
    again = post_spray(api_client, auth, product_id=None, free_text="Local mix").json()
    assert first["warnings"][0]["code"] == "PRODUCT_NOT_RECOGNISED"
    assert again == first and again["spoken"]["text"]["en"].endswith(first["warnings"][0]["text"]["en"])


def test_spray_keys_are_per_farmer_and_separate_from_scan_keys(api_client, auth, login):
    mine = post_spray(api_client, auth)
    theirs = post_spray(api_client, login("+910000000002"))
    scan = post_scan(api_client, auth)                                                              # the same key on another route
    assert mine.json()["id"] != theirs.json()["id"] and REPLAY not in theirs.headers and REPLAY not in scan.headers
    assert count(SprayLogRow) == 2


def test_a_spray_log_that_lost_the_race_returns_the_winner(api_client, auth, fake_container, monkeypatch):
    winner = post_spray(api_client, auth)
    monkeypatch.setattr(SprayService, "find_by_request_id", lambda self, farmer, key: None)
    loser = post_spray(api_client, auth)
    assert loser.status_code == 200 and loser.json()["id"] == winner.json()["id"]
    assert count(SprayLogRow) == 1 and len(fake_container.zoho.spray_writes) == 1


def test_simultaneous_spray_logs_with_one_key_create_one_entry(api_client, auth, fake_container):
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: post_spray(api_client, auth), range(4)))
    assert len({r.json()["id"] for r in responses}) == 1 and count(SprayLogRow) == 1
    assert len(fake_container.zoho.spray_writes) == 1


def test_spray_validation_errors_do_not_consume_the_key(api_client, auth):
    bad = post_spray(api_client, auth, product_id="P999")
    assert bad.status_code == 422
    assert post_spray(api_client, auth).status_code == 200 and count(SprayLogRow) == 1


# ------------------------------------------------------------------------------------------------ expert requests
def test_replaying_an_expert_request_creates_nothing_new(api_client, auth):
    scan = post_scan(api_client, auth, key="s" * 16).json()
    first = post_expert(api_client, auth, scan_id=scan["id"])
    again = post_expert(api_client, auth, scan_id=scan["id"])
    assert first.status_code == again.status_code == 200 and again.json() == first.json()
    assert again.headers[REPLAY] == "true" and REPLAY not in first.headers
    assert count(ExpertRequestRow) == 1 and count(ReviewTaskRow) == 1


def test_expert_request_keys_are_per_farmer(api_client, auth, login):
    mine, theirs = post_expert(api_client, auth), post_expert(api_client, login("+910000000002"))
    assert mine.json()["id"] != theirs.json()["id"] and count(ExpertRequestRow) == 2


def test_an_expert_request_that_lost_the_race_returns_the_winner(api_client, auth, monkeypatch):
    from app.api.routes import ask

    winner = post_expert(api_client, auth)
    real, calls = ask._request_by_key, {"n": 0}

    def lookup(db, farmer_id, key):                                  # the first lookup (before the insert) misses: a true race
        calls["n"] += 1
        return None if calls["n"] == 1 else real(db, farmer_id, key)

    monkeypatch.setattr(ask, "_request_by_key", lookup)
    loser = post_expert(api_client, auth)
    assert loser.status_code == 200 and loser.json()["id"] == winner.json()["id"] and loser.headers[REPLAY] == "true"
    assert count(ExpertRequestRow) == 1


# ------------------------------------------------------------------------------------------------ contract
def test_cors_allows_the_idempotency_key_header(api_client):
    response = api_client.options("/v1/spray-logs", headers={"Origin": "https://app.example.org", "Access-Control-Request-Method": "POST",
                                                            "Access-Control-Request-Headers": "idempotency-key, authorization"})
    assert response.status_code == 200
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("path", ["/v1/scans", "/v1/spray-logs", "/v1/expert-requests"])
def test_the_header_is_documented_on_the_create_routes(api_app, path):
    operation = api_app.openapi()["paths"][path]["post"]
    parameter = next(p for p in operation["parameters"] if p["name"] == "Idempotency-Key")
    assert parameter["in"] == "header" and parameter.get("required", False) is False
    assert "same ids" in parameter["description"] and "Idempotency-Key" in operation["description"]
    assert "400" in operation["responses"]


def test_other_routes_do_not_take_the_header(api_app):
    paths = api_app.openapi()["paths"]
    assert not any(p["name"] == "Idempotency-Key" for p in paths["/v1/ask"]["post"].get("parameters", []))


# ------------------------------------------------------------------------------------------------ the lock helper
def test_keyed_locks_serialise_the_same_name_and_forget_unused_names():
    locks, order, inside = KeyedLocks(), [], threading.Event()

    def worker(tag, hold):
        with locks.hold("k"):
            order.append(f"{tag}-in")
            if hold:
                inside.set()
                time.sleep(0.2)
            order.append(f"{tag}-out")

    first = threading.Thread(target=worker, args=("a", True))
    first.start()
    inside.wait(2)
    second = threading.Thread(target=worker, args=("b", False))
    second.start()
    first.join(), second.join()
    assert order == ["a-in", "a-out", "b-in", "b-out"]
    assert locks._locks == {}
    with locks.hold("x"), locks.hold("y"):                                                          # different names do not block
        assert set(locks._locks) == {"x", "y"}

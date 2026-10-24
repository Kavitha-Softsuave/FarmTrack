"""The backend half of "photos taken offline are sent when the phone is online again".

The app queues each scan with one Idempotency-Key, its photo time (`taken_at`) and `offline=true`, and sends it later, possibly more
than once. These tests cover: replay twice, replay with old timestamps, a wrong phone clock, different content under one key, duplicate
and large photos, an exhausted rate limit, and fetching the result later (by id, in the list, and by key when the response was lost).
"""
import io

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.db.models import ScanRow
from app.db.session import session_scope
from tests.imaging import make_jpeg, photo_files

KEY = "5d1c2b9e-0f3a-4c7e-8a41-2b6f9d0e7a13"
REPLAY = "Idempotent-Replayed"


def send(client, auth, key=KEY, files=None, **form):
    headers = {**auth, **({"Idempotency-Key": key} if key else {})}
    return client.post("/v1/scans", files=files or photo_files(1), data=form, headers=headers)


def scan_rows() -> list[ScanRow]:
    with session_scope() as db:
        rows = list(db.scalars(select(ScanRow).order_by(ScanRow.id)))
        db.expunge_all()
        return rows


# ------------------------------------------------------------------------------------------------ the offline flag and times
def test_offline_scan_keeps_the_photo_time_and_the_flag(api_client, auth):
    body = send(api_client, auth, taken_at="2026-05-10T16:30:00+05:30", offline="true").json()
    assert body["offline"] is True and body["taken_at"] == "2026-05-10T16:30:00+05:30"
    assert body["created_at"] == "2026-05-12T08:00:00+05:30"            # evaluated on arrival (the demo clock)
    row = scan_rows()[0]
    assert row.offline is True and row.taken_at is not None


def test_a_live_scan_has_no_photo_time_and_is_not_offline(api_client, auth):
    body = send(api_client, auth).json()
    assert body["offline"] is False and body["taken_at"] is None
    assert scan_rows()[0].offline is False


def test_a_photo_time_without_a_zone_is_read_as_indian_time(api_client, auth):
    assert send(api_client, auth, taken_at="2026-05-11T09:00:00", offline="true").json()["taken_at"] == "2026-05-11T09:00:00+05:30"


def test_a_time_in_another_zone_is_converted(api_client, auth):
    assert send(api_client, auth, taken_at="2026-05-11T03:30:00+00:00").json()["taken_at"] == "2026-05-11T09:00:00+05:30"


@pytest.mark.parametrize("taken_at", ["2031-01-01T00:00:00+05:30", "2020-01-01T00:00:00+05:30", "2026-05-14T09:00:00+05:30"])
def test_a_wrong_phone_clock_never_loses_the_photo(api_client, auth, taken_at):
    response = send(api_client, auth, taken_at=taken_at, offline="true")
    assert response.status_code == 200 and response.json()["taken_at"] is None and response.json()["offline"] is True


def test_a_photo_that_waited_many_days_is_accepted(api_client, auth):
    response = send(api_client, auth, taken_at="2026-04-14T10:00:00+05:30", offline="true")      # 28 days before the demo clock
    assert response.status_code == 200 and response.json()["taken_at"] == "2026-04-14T10:00:00+05:30"


def test_an_unreadable_time_is_still_a_clear_400(api_client, auth):
    assert send(api_client, auth, taken_at="last tuesday").status_code == 400


# ------------------------------------------------------------------------------------------------ replay
def test_replaying_twice_gives_one_scan_and_identical_answers(api_client, auth):
    first = send(api_client, auth, taken_at="2026-05-10T16:30:00+05:30", offline="true")
    second = send(api_client, auth, taken_at="2026-05-10T16:30:00+05:30", offline="true")
    third = send(api_client, auth, taken_at="2026-05-10T16:30:00+05:30", offline="true")
    assert [first.status_code, second.status_code, third.status_code] == [200, 200, 200]
    assert second.json() == first.json() == third.json()
    assert REPLAY not in first.headers and second.headers[REPLAY] == third.headers[REPLAY] == "true"
    assert len(scan_rows()) == 1


def test_a_replay_with_old_timestamps_and_other_content_returns_the_first_result(api_client, auth):
    first = send(api_client, auth, taken_at="2026-05-10T16:30:00+05:30", offline="true")
    other = send(api_client, auth, files=photo_files(2, color=(200, 20, 20)), taken_at="2026-04-01T08:00:00+05:30", offline="false")
    assert other.status_code == 200 and other.headers[REPLAY] == "true"
    assert other.json() == first.json() and other.json()["photos"] == 1
    assert len(scan_rows()) == 1 and scan_rows()[0].taken_at is not None


def test_a_queue_of_different_photos_makes_separate_scans_in_any_order(api_client, auth):
    keys = [f"queue-item-{i:04d}-aaaa" for i in range(4)]
    first_pass = [send(api_client, auth, key=k, files=photo_files(1, color=(40 * i + 10, 90, 90)), offline="true") for i, k in enumerate(keys)]
    second_pass = [send(api_client, auth, key=k, offline="true") for k in reversed(keys)]       # the whole queue sent again
    assert len({r.json()["id"] for r in first_pass}) == 4
    assert [r.json()["id"] for r in reversed(second_pass)] == [r.json()["id"] for r in first_pass]
    assert len(scan_rows()) == 4


def test_the_same_picture_under_two_keys_is_two_scans(api_client, auth):
    """The server cannot tell a deliberate second scan from a copy, so only the key identifies an action."""
    one = send(api_client, auth, key="same-photo-key-0001")
    two = send(api_client, auth, key="same-photo-key-0002")
    assert one.json()["id"] != two.json()["id"] and len(scan_rows()) == 2


def test_one_photo_sent_twice_in_one_scan_is_kept_twice(api_client, auth):
    content = make_jpeg()
    files = [("photos", ("a.jpg", content, "image/jpeg")), ("photos", ("b.jpg", content, "image/jpeg"))]
    assert send(api_client, auth, files=files).json()["photos"] == 2


def test_a_rate_limited_upload_does_not_use_up_its_key(api_client, auth, api_app):
    from app.security.ratelimit import RateLimiters, SlidingWindowLimiter

    limiters = RateLimiters.default()
    limiters.scan_farmer = SlidingWindowLimiter(1, 600)
    api_app.state.limiters = limiters
    assert send(api_client, auth, key="first-queued-key-1").status_code == 200
    blocked = send(api_client, auth, key="second-queued-key-2")
    assert blocked.status_code == 429 and len(scan_rows()) == 1
    limiters.scan_farmer = SlidingWindowLimiter(5, 600)                       # the window has passed
    retried = send(api_client, auth, key="second-queued-key-2")
    assert retried.status_code == 200 and REPLAY not in retried.headers and len(scan_rows()) == 2


def test_a_failed_upload_does_not_use_up_its_key(api_client, auth):
    bad = send(api_client, auth, files=[("photos", ("x.jpg", b"not an image at all" * 20, "image/jpeg"))])
    assert bad.status_code == 400
    assert send(api_client, auth).status_code == 200 and len(scan_rows()) == 1


# ------------------------------------------------------------------------------------------------ large photos
def test_a_large_photo_from_a_modern_phone_is_accepted_and_shrunk(api_client, auth, api_settings):
    rng_image = Image.effect_noise((4000, 3000), 40).convert("RGB")                 # about 12 MP, noisy so it compresses badly
    buffer = io.BytesIO()
    rng_image.save(buffer, format="JPEG", quality=90)
    raw = buffer.getvalue()
    assert 1_000_000 < len(raw) <= api_settings.max_upload_mb * 1024 * 1024
    body = send(api_client, auth, files=[("photos", ("big.jpg", raw, "image/jpeg"))], offline="true").json()
    assert body["photos"] == 1
    stored = next((api_settings.storage_dir / "photos").rglob("*.jpg"))
    with Image.open(stored) as image:
        assert max(image.size) <= 2048


def test_a_photo_over_the_limit_is_413_and_nothing_is_stored(api_client, auth, monkeypatch, api_settings):
    big = b"\xff\xd8\xff" + b"0" * (api_settings.max_upload_mb * 1024 * 1024 + 10)
    response = send(api_client, auth, files=[("photos", ("huge.jpg", big, "image/jpeg"))])
    assert response.status_code == 413 and scan_rows() == []


# ------------------------------------------------------------------------------------------------ fetching the result later
def test_the_result_of_an_offline_scan_can_be_fetched_by_id_list_and_key(api_client, auth):
    created = send(api_client, auth, taken_at="2026-05-10T16:30:00+05:30", offline="true").json()
    by_id = api_client.get(f"/v1/scans/{created['id']}", headers=auth)
    by_key = api_client.get(f"/v1/scans/by-request/{KEY}", headers=auth)
    listed = api_client.get("/v1/scans", headers=auth).json()["items"]
    assert by_id.json() == by_key.json() == created and listed == [created]
    assert by_key.json()["offline"] is True and by_key.json()["advice"] is not None


def test_a_key_that_never_arrived_is_a_clean_404(api_client, auth):
    for key in ("never-uploaded-key-1", "x", "bad key with spaces"):
        response = api_client.get(f"/v1/scans/by-request/{key}", headers=auth)
        assert response.status_code == 404 and response.json()["code"] == "scan_not_found"


def test_lookup_by_key_needs_a_login(api_client, auth):
    send(api_client, auth)
    assert api_client.get(f"/v1/scans/by-request/{KEY}").status_code == 401


def test_the_lookup_does_no_work(api_client, auth, fake_container):
    send(api_client, auth)
    calls = (len(fake_container.crop_identifier.calls), len(fake_container.composer.calls))
    api_client.get(f"/v1/scans/by-request/{KEY}", headers=auth)
    assert (len(fake_container.crop_identifier.calls), len(fake_container.composer.calls)) == calls


def test_old_rows_without_the_new_columns_still_read(api_client, auth):
    created = send(api_client, auth).json()
    with session_scope() as db:
        row = db.get(ScanRow, created["id"])
        row.taken_at, row.offline = None, None
        result = dict(row.result)
        result.pop("taken_at", None)
        result.pop("offline", None)
        row.result = result
        assert db.scalar(select(func.count()).select_from(ScanRow)) == 1
    again = api_client.get(f"/v1/scans/{created['id']}", headers=auth).json()
    assert again["offline"] is False and again["taken_at"] is None

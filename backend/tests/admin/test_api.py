from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.admin.clock_store import restore_demo_clock
from app.api.deps import require_admin
from app.clock import IST, get_clock
from app.config import get_settings
from app.db.models import (
    AlertRow,
    AppSettingRow,
    AuditLogRow,
    ProductOverrideRow,
    ReviewTaskRow,
    ScanRow,
    as_ist,
)
from tests.admin.conftest import seed, seed_review
from tests.integrations.fakes import NOW, FakeRules, farmer_row, risk

BASE = "/admin/api/v1"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


def audit_actions(db) -> list[str]:
    db.expire_all()
    return [a for a in db.scalars(select(AuditLogRow.action).order_by(AuditLogRow.at))]


# ------------------------------------------------------------------------------------------------- guard
@pytest.mark.parametrize("method,path", [
    ("get", "/review-tasks"), ("post", "/review-tasks/t1/resolve"), ("get", "/settings/demo-clock"), ("put", "/settings/demo-clock"),
    ("get", "/products"), ("patch", "/products/P001"), ("get", "/farmers"), ("get", "/alerts"), ("post", "/alerts/run-now"),
    ("get", "/audit"), ("get", "/photos/scan1/0"),
])
def test_every_admin_api_route_is_behind_require_admin(app, client, method, path):
    def refuse():
        raise HTTPException(401, "no key")

    app.dependency_overrides[require_admin] = refuse
    response = getattr(client, method)(BASE + path, **({"json": {}} if method in ("post", "put", "patch") else {}))
    assert response.status_code == 401


def test_openapi_lists_the_api_but_not_the_pages(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/admin/api/v1/alerts/run-now" in paths and "/admin/api/v1/review-tasks" in paths
    assert not any(p.startswith("/admin/") and "/api/" not in p for p in paths)
    assert "/admin/api/v1/photos/{scan_id}/{index}" not in paths


# ------------------------------------------------------------------------------------------------- review tasks
def test_list_review_tasks(client, db):
    seed_review(db)
    body = client.get(f"{BASE}/review-tasks").json()
    assert len(body) == 1
    task = body[0]
    assert task["id"] == "t1" and task["status"] == "open" and task["scan_id"] == "scan1"
    assert task["farmer_id"] == "F901" and task["farmer_name"] == "Test Farmer F901"
    assert task["crop_guess"] == "Apple" and task["reason"] == "Alternaria or Marssonina"
    assert task["photo_urls"] == ["/admin/api/v1/photos/scan1/0"]
    assert [c["disease_id"] for c in task["disease_candidates"]] == ["Apple___Apple_scab"]      # the malformed candidate is skipped
    assert task["disease_candidates"][0]["confidence"] == 0.61
    assert task["created_at"].startswith("2026-05-12T08:00:00") and task["resolution_note"] is None


def test_open_queue_is_oldest_first_and_filters_work(client, db):
    seed_review(db, "t_new", "s_new")
    seed_review(db, "t_old", "s_old")
    old = db.get(ReviewTaskRow, "t_old")
    old.created_at = NOW - timedelta(days=2)
    db.get(ReviewTaskRow, "t_new").status = "resolved"
    db.commit()
    assert [t["id"] for t in client.get(f"{BASE}/review-tasks").json()] == ["t_old"]
    assert [t["id"] for t in client.get(f"{BASE}/review-tasks?status=resolved").json()] == ["t_new"]
    assert [t["id"] for t in client.get(f"{BASE}/review-tasks?status=all").json()] == ["t_new", "t_old"]
    assert len(client.get(f"{BASE}/review-tasks?status=all&limit=1").json()) == 1
    assert client.get(f"{BASE}/review-tasks?status=bogus").status_code == 422


def test_resolve_review_task(client, db):
    seed_review(db)
    response = client.post(f"{BASE}/review-tasks/t1/resolve", json={
        "confirmed_crop": "Apple", "confirmed_disease": "Apple___Marssonina_blotch", "note": "Blotch, protectant spray advised"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved" and body["resolution_note"] == "Blotch, protectant spray advised"
    db.expire_all()
    task = db.get(ReviewTaskRow, "t1")
    assert task.status == "resolved" and as_ist(task.resolved_at) == NOW
    assert task.resolution["confirmed_disease"] == "Apple___Marssonina_blotch" and task.resolution["release_advice"] is False
    assert audit_actions(db) == ["review.resolve"]
    assert client.get(f"{BASE}/review-tasks").json() == []


def test_resolve_errors(client, db):
    seed_review(db)
    assert client.post(f"{BASE}/review-tasks/nope/resolve", json={}).status_code == 404
    assert client.post(f"{BASE}/review-tasks/t1/resolve", json={"confirmed_disease": "Not_A_Disease"}).status_code == 422
    assert client.post(f"{BASE}/review-tasks/t1/resolve", json={"release_advice": True}).status_code == 422
    assert client.post(f"{BASE}/review-tasks/t1/resolve", json={"note": "x" * 501}).status_code == 422
    assert client.post(f"{BASE}/review-tasks/t1/resolve", json={"note": "done"}).status_code == 200
    assert client.post(f"{BASE}/review-tasks/t1/resolve", json={"note": "again"}).status_code == 409


def test_release_advice_calls_the_injected_hook(app, client, db):
    seed_review(db)
    calls = []

    def hook(session, task, body):
        calls.append((task.id, body.confirmed_disease, body.confirmed_crop))
        return True

    app.state.release_advice = hook
    response = client.post(f"{BASE}/review-tasks/t1/resolve", json={"confirmed_disease": "Apple___Apple_scab", "release_advice": True})
    assert response.status_code == 200 and calls == [("t1", "Apple___Apple_scab", None)]
    db.expire_all()
    assert db.get(ReviewTaskRow, "t1").resolution["release_status"] == "released"


@pytest.mark.parametrize("behaviour", ["false", "raises"])
def test_failed_release_keeps_the_task_open(app, client, db, behaviour):
    seed_review(db)

    def hook(session, task, body):
        if behaviour == "raises":
            raise RuntimeError("rules engine down")
        return False

    app.state.release_advice = hook
    response = client.post(f"{BASE}/review-tasks/t1/resolve", json={"confirmed_disease": "Apple___Apple_scab", "release_advice": True})
    assert response.status_code == 502
    db.expire_all()
    assert db.get(ReviewTaskRow, "t1").status == "open" and audit_actions(db) == []


def test_release_without_a_hook_still_resolves_and_says_so(client, db):
    seed_review(db)
    assert client.post(f"{BASE}/review-tasks/t1/resolve", json={"confirmed_crop": "Apple", "release_advice": True}).status_code == 200
    db.expire_all()
    assert db.get(ReviewTaskRow, "t1").resolution["release_status"] == "not_configured"


def test_hook_is_not_called_unless_release_is_requested(app, client, db):
    seed_review(db)
    app.state.release_advice = lambda *a: pytest.fail("must not be called")
    assert client.post(f"{BASE}/review-tasks/t1/resolve", json={"confirmed_crop": "Apple"}).status_code == 200


# ------------------------------------------------------------------------------------------------- photos
def test_photo_is_served_with_safe_headers(client, db):
    seed_review(db)
    path = get_settings().storage_dir / "photos" / "F901" / "scan1_0.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(JPEG)
    response = client.get(f"{BASE}/photos/scan1/0")
    assert response.status_code == 200 and response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, no-store" and response.headers["x-content-type-options"] == "nosniff"


def test_photo_route_refuses_traversal_missing_and_non_image_files(client, db):
    storage = get_settings().storage_dir
    storage.mkdir(parents=True, exist_ok=True)
    (storage.parent / "secret.jpg").write_bytes(JPEG)
    (storage / "notes.txt").write_text("not a photo")
    seed_review(db, photo_paths=["../secret.jpg", "notes.txt", "missing.jpg", "/etc/passwd"])
    for index in range(4):
        assert client.get(f"{BASE}/photos/scan1/{index}").status_code == 404, index
    assert client.get(f"{BASE}/photos/scan1/9").status_code == 404
    assert client.get(f"{BASE}/photos/scan1/-1").status_code == 404
    assert client.get(f"{BASE}/photos/unknown/0").status_code == 404


# ------------------------------------------------------------------------------------------------- demo clock
def test_get_demo_clock(client):
    body = client.get(f"{BASE}/settings/demo-clock").json()
    assert body["fixed"] is True and body["now"].startswith("2026-05-12T08:00:00")


def test_put_demo_clock_applies_persists_and_audits(client, db, container):
    response = client.put(f"{BASE}/settings/demo-clock", json={"now": "2026-07-12T09:00:00+05:30"})
    assert response.status_code == 200
    assert response.json()["fixed"] is True and response.json()["now"].startswith("2026-07-12T09:00:00")
    assert container.clock.now() == datetime(2026, 7, 12, 9, 0, tzinfo=IST)
    db.expire_all()
    assert db.get(AppSettingRow, "demo_clock").value == {"now": "2026-07-12T09:00:00+05:30"}
    assert client.get(f"{BASE}/settings/demo-clock").json()["now"].startswith("2026-07-12T09:00:00")
    assert audit_actions(db) == ["clock.set"]


def test_naive_demo_clock_is_india_time(client, container):
    client.put(f"{BASE}/settings/demo-clock", json={"now": "2026-03-30T20:00:00"})
    assert container.clock.now() == datetime(2026, 3, 30, 20, 0, tzinfo=IST)


def test_clearing_the_demo_clock_returns_to_real_time_and_survives_a_restart(client, db, container):
    client.put(f"{BASE}/settings/demo-clock", json={"now": "2026-07-12T09:00:00+05:30"})
    response = client.put(f"{BASE}/settings/demo-clock", json={"now": None})
    assert response.json()["fixed"] is False
    assert abs(container.clock.now() - datetime.now(IST)) < timedelta(minutes=1)
    db.expire_all()
    assert db.get(AppSettingRow, "demo_clock").value == {"now": None}
    assert get_clock().is_fixed is True                                       # the process default (DEMO_CLOCK setting)
    assert restore_demo_clock() is True
    assert get_clock().is_fixed is False                                      # the stored 'real clock' wins after a restart


def test_demo_clock_is_restored_after_a_restart(client, db):
    client.put(f"{BASE}/settings/demo-clock", json={"now": "2026-07-12T09:00:00+05:30"})
    assert get_clock().now() == datetime(2026, 5, 12, 8, 0, tzinfo=IST)       # the global clock still has the settings default
    assert restore_demo_clock() is True
    assert get_clock().now() == datetime(2026, 7, 12, 9, 0, tzinfo=IST)


def test_restore_without_a_stored_value_changes_nothing(db):
    assert restore_demo_clock() is False
    assert get_clock().now() == datetime(2026, 5, 12, 8, 0, tzinfo=IST)


def test_clock_endpoints_use_the_global_clock_without_a_container(app, client):
    del app.state.container
    assert client.get(f"{BASE}/settings/demo-clock").json()["now"].startswith("2026-05-12T08:00:00")


# ------------------------------------------------------------------------------------------------- products
def test_list_products_from_the_master_file(client):
    products = client.get(f"{BASE}/products").json()
    assert len(products) == 97 and all(p["enabled"] for p in products)
    first = products[0]
    assert first["product_id"] == "P001" and first["crop"] == "Apple" and first["active_ingredient"] == "Captan"
    assert first["targets"] == ["Apple___Apple_scab"] and first["dose_text"] == "600 g/200L" and first["waiting_period_days"] is None
    assert first["ban_status"] == "proposed_ban_2020_draft_still_registered"
    assert next(p for p in products if p["product_id"] == "P002")["waiting_period_days"] == 21


def test_products_can_be_filtered_by_crop(client):
    assert len(client.get(f"{BASE}/products?crop=Apple").json()) == 68
    assert len(client.get(f"{BASE}/products?crop=tomato").json()) == 13
    assert client.get(f"{BASE}/products?crop=Banana").json() == []


def test_patch_product_disables_and_enables(client, db):
    response = client.patch(f"{BASE}/products/P001", json={"enabled": False, "note": "agronomist asked"})
    assert response.status_code == 200 and response.json()["enabled"] is False
    row = db.get(ProductOverrideRow, "P001")
    db.refresh(row)
    assert row.enabled is False and row.note == "agronomist asked" and as_ist(row.updated_at) == NOW
    listed = {p["product_id"]: p["enabled"] for p in client.get(f"{BASE}/products").json()}
    assert listed["P001"] is False and listed["P002"] is True
    assert client.patch(f"{BASE}/products/P001", json={"enabled": True}).json()["enabled"] is True
    db.refresh(row)
    assert row.enabled is True and row.note == "agronomist asked"          # a missing note keeps the old one
    assert audit_actions(db) == ["product.disable", "product.enable"]


def test_patch_unknown_product_is_404(client):
    assert client.patch(f"{BASE}/products/P999", json={"enabled": False}).status_code == 404
    assert client.patch(f"{BASE}/products/P001", json={}).status_code == 422


# ------------------------------------------------------------------------------------------------- farmers, alerts, audit
def test_list_farmers_with_last_scan(client, db):
    seed_review(db, "t1", "s1", "F901")
    seed(db, farmer_row("F902", language="hi", primary_crop="Potato"))
    db.add(ScanRow(id="s1b", farmer_id="F901", created_at=NOW + timedelta(days=1), status="ok", photo_paths=[], result={}))
    db.commit()
    farmers = {f["id"]: f for f in client.get(f"{BASE}/farmers").json()}
    assert set(farmers) == {"F901", "F902"}
    assert farmers["F901"]["last_scan_at"].startswith("2026-05-13T08:00:00") and farmers["F902"]["last_scan_at"] is None
    assert farmers["F902"]["language"] == "hi" and farmers["F902"]["primary_crop"] == "Potato" and farmers["F901"]["village"] == "Jubbal"
    assert "phone" not in str(farmers) and len(client.get(f"{BASE}/farmers?limit=1").json()) == 1


def test_run_now_creates_alerts_lists_them_and_is_idempotent(client, db, container):
    seed(db, farmer_row("F901"), farmer_row("F902", station_id="ST01"))
    container.rules = FakeRules([risk("scab_infection_risk", "red", episode="2026-05-04")])
    first = client.post(f"{BASE}/alerts/run-now").json()
    assert first["created"] == 2 and {a["farmer_id"] for a in first["alerts"]} == {"F901", "F902"}
    assert first["alerts"][0]["level"] == "red" and first["alerts"][0]["title"]["hi"]
    assert client.post(f"{BASE}/alerts/run-now").json() == {"created": 0, "alerts": []}
    listed = client.get(f"{BASE}/alerts").json()
    assert len(listed) == 2 and {a["dedupe_key"] for a in listed} == {"scab:ST05:2026-05-04:red", "scab:ST01:2026-05-04:red"}
    assert [a["farmer_id"] for a in client.get(f"{BASE}/alerts?farmer_id=F902").json()] == ["F902"]
    assert len(client.get(f"{BASE}/alerts?limit=1").json()) == 1
    assert audit_actions(db) == ["alerts.run_now", "alerts.run_now"]
    db.expire_all()
    assert db.scalar(select(AlertRow.pushed_at)) is None


def test_run_now_without_a_container_is_503(app, client):
    del app.state.container
    assert client.post(f"{BASE}/alerts/run-now").status_code == 503


def test_audit_list_is_newest_first(client, db):
    client.patch(f"{BASE}/products/P001", json={"enabled": False})
    client.put(f"{BASE}/settings/demo-clock", json={"now": "2026-07-12T09:00:00+05:30"})
    entries = client.get(f"{BASE}/audit").json()
    assert [e["action"] for e in entries] == ["clock.set", "product.disable"]
    assert entries[1]["entity"] == "product" and entries[1]["entity_id"] == "P001" and entries[0]["actor"] == "admin"
    assert entries[0]["at"].endswith("Z") or "+00:00" in entries[0]["at"]
    assert len(client.get(f"{BASE}/audit?limit=1").json()) == 1

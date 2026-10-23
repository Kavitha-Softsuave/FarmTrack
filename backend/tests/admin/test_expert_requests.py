"""Staff view of the farmers' 'ask a farm expert' requests, including the ones without a scan (no review task)."""
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import require_admin
from app.db.models import AuditLogRow, ExpertRequestRow, ReviewTaskRow
from tests.admin.conftest import seed, seed_review
from tests.admin.test_pages import XSS, csrf_from, login
from tests.integrations.fakes import NOW, farmer_row

BASE = "/admin/api/v1"
PAGE = "/admin/expert-requests"


def request_row(request_id="r1", farmer_id="F901", **values) -> ExpertRequestRow:
    defaults = {"id": request_id, "farmer_id": farmer_id, "status": "open", "created_at": NOW, "message": "My apple leaves are curling"}
    return ExpertRequestRow(**{**defaults, **values})


@pytest.fixture
def authed(client):
    login(client)
    return client


# ------------------------------------------------------------------------------------------------- the API
def test_the_api_is_behind_the_admin_key(app, client):
    def refuse():
        raise HTTPException(401, "no key")

    app.dependency_overrides[require_admin] = refuse
    assert client.get(f"{BASE}/expert-requests").status_code == 401
    assert client.post(f"{BASE}/expert-requests/r1/resolve", json={}).status_code == 401


def test_a_request_without_a_scan_is_listed_with_farmer_crop_text_and_date(client, db):
    seed(db, farmer_row("F901", primary_crop="Tomato"), request_row())
    [item] = client.get(f"{BASE}/expert-requests").json()
    assert item["id"] == "r1" and item["status"] == "open" and item["scan_id"] is None and item["review_task_id"] is None
    assert item["farmer_id"] == "F901" and item["farmer_name"] == "Test Farmer F901"
    assert item["crop"] == "Tomato"                                                         # the farmer's main crop
    assert item["message"] == "My apple leaves are curling" and item["created_at"].startswith("2026-05-12T08:00:00")
    assert item["resolved_at"] is None and item["resolution_note"] is None


def test_the_crop_comes_from_the_request_then_the_scan_then_the_farmer(client, db):
    seed(db, farmer_row("F901", primary_crop="Tomato"))
    seed_review(db, scan_id="scan1", crop_id="Potato")
    seed(db, request_row("with-crop", crop_id="Maize"), request_row("with-scan", scan_id="scan1"), request_row("plain"))
    crops = {r["id"]: r["crop"] for r in client.get(f"{BASE}/expert-requests?status=all").json()}
    assert crops == {"with-crop": "Maize", "with-scan": "Potato", "plain": "Tomato"}


def test_a_request_about_a_scan_points_to_its_review_task(client, db):
    seed_review(db)
    seed(db, request_row(scan_id="scan1"))
    [item] = client.get(f"{BASE}/expert-requests").json()
    assert item["scan_id"] == "scan1" and item["review_task_id"] == "t1"


def test_status_filter_order_and_limit(client, db):
    seed(db, farmer_row("F901"),
         request_row("old", created_at=NOW - timedelta(days=2)), request_row("new", created_at=NOW),
         request_row("done", created_at=NOW - timedelta(days=1), status="resolved"))
    assert [r["id"] for r in client.get(f"{BASE}/expert-requests").json()] == ["old", "new"]              # open: first in, first out
    assert [r["id"] for r in client.get(f"{BASE}/expert-requests?status=resolved").json()] == ["done"]
    assert [r["id"] for r in client.get(f"{BASE}/expert-requests?status=all").json()] == ["new", "done", "old"]
    assert [r["id"] for r in client.get(f"{BASE}/expert-requests?limit=1").json()] == ["old"]
    assert client.get(f"{BASE}/expert-requests?status=bogus").status_code == 422


def test_resolving_records_the_note_the_time_and_an_audit_entry(client, db):
    seed(db, farmer_row("F901"), request_row())
    response = client.post(f"{BASE}/expert-requests/r1/resolve", json={"note": "Called the farmer, advised pruning."})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved" and body["resolution_note"] == "Called the farmer, advised pruning."
    assert body["resolved_at"].startswith("2026-05-12T08:00:00")
    db.expire_all()
    row = db.get(ExpertRequestRow, "r1")
    assert row.status == "resolved" and row.resolution == {"note": "Called the farmer, advised pruning.", "via": "admin"}
    audit = db.scalars(select(AuditLogRow).where(AuditLogRow.action == "expert_request.resolve")).one()
    assert audit.entity == "expert_request" and audit.entity_id == "r1" and audit.detail == {"has_note": True}
    assert client.get(f"{BASE}/expert-requests").json() == []                                # no longer in the open list


def test_a_note_is_optional(client, db):
    seed(db, farmer_row("F901"), request_row())
    assert client.post(f"{BASE}/expert-requests/r1/resolve", json={}).json()["resolution_note"] is None


def test_unknown_closed_and_oversized_requests_are_refused(client, db):
    seed(db, farmer_row("F901"), request_row("closed", status="resolved"), request_row())
    assert client.post(f"{BASE}/expert-requests/zzz/resolve", json={}).status_code == 404
    assert client.post(f"{BASE}/expert-requests/closed/resolve", json={}).status_code == 409
    assert client.post(f"{BASE}/expert-requests/r1/resolve", json={"note": "n" * 501}).status_code == 422
    db.expire_all()
    assert db.get(ExpertRequestRow, "r1").status == "open"


def test_resolving_the_review_task_of_a_scan_also_answers_the_farmers_request(client, db):
    seed_review(db)
    seed(db, request_row("about-scan", scan_id="scan1"), request_row("other-question"))
    assert client.post(f"{BASE}/review-tasks/t1/resolve", json={"note": "It is scab"}).status_code == 200
    db.expire_all()
    answered, other = db.get(ExpertRequestRow, "about-scan"), db.get(ExpertRequestRow, "other-question")
    assert answered.status == "resolved" and answered.resolution["via"] == "review_task" and answered.resolution["note"] == "It is scab"
    assert answered.resolution["review_task_id"] == "t1" and other.status == "open"
    assert db.get(ReviewTaskRow, "t1").status == "resolved"


def test_the_endpoints_are_in_the_openapi_description(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "get" in paths[f"{BASE}/expert-requests"] and "post" in paths[f"{BASE}/expert-requests/{{request_id}}/resolve"]


# ------------------------------------------------------------------------------------------------- the page
def test_the_page_needs_a_session(client):
    for path in (PAGE, f"{PAGE}?status=all"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/admin/login"
    response = client.post(f"{PAGE}/r1/resolve", data={"note": "x"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin/login"


def test_the_page_lists_requests_with_a_form_to_close_each(authed, db):
    seed(db, farmer_row("F901"), request_row())
    response = authed.get(PAGE)
    html = response.text
    assert response.status_code == 200 and "Expert requests" in html and "Test Farmer F901" in html and "My apple leaves are curling" in html
    assert "No photo" in html and 'action="/admin/expert-requests/r1/resolve"' in html and 'name="note"' in html
    assert 'name="csrf"' in html and 'aria-current="page">Expert requests' in html                      # in the navigation too
    assert response.headers["content-security-policy"].startswith("default-src 'none'") and "unsafe-inline" not in response.headers["content-security-policy"]
    assert 'aria-current="page">Open' in html


def test_the_page_filters_and_has_an_empty_state(authed, db):
    assert "No expert requests in this view." in authed.get(PAGE).text
    seed(db, farmer_row("F901"), request_row(status="resolved", resolution={"note": "Phoned him"}, resolved_at=NOW))
    assert "No expert requests in this view." in authed.get(PAGE).text
    closed = authed.get(f"{PAGE}?status=resolved").text
    assert "My apple leaves are curling" in closed and "Phoned him" in closed and "/resolve" not in closed
    assert "My apple leaves are curling" in authed.get(f"{PAGE}?status=all").text
    assert 'aria-current="page">Open' in authed.get(f"{PAGE}?status=bogus").text                      # an unknown filter shows the open queue


def test_a_request_about_a_scan_links_to_the_review_queue(authed, db):
    seed_review(db)
    seed(db, request_row(scan_id="scan1"))
    html = authed.get(PAGE).text
    assert "About scan" in html and "scan1" in html and 'href="/admin/review"' in html and "No photo" not in html


def test_closing_a_request_from_the_page(authed, db):
    seed(db, farmer_row("F901"), request_row())
    token = csrf_from(authed, PAGE)
    response = authed.post(f"{PAGE}/r1/resolve", data={"csrf": token, "note": "  Phoned him  "}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"{PAGE}?ok=request_closed"
    db.expire_all()
    assert db.get(ExpertRequestRow, "r1").resolution == {"note": "Phoned him", "via": "admin"}
    assert "Expert request closed." in authed.get(f"{PAGE}?ok=request_closed").text
    again = authed.post(f"{PAGE}/r1/resolve", data={"csrf": token}, follow_redirects=False)
    assert again.headers["location"] == f"{PAGE}?err=request_already_closed"
    missing = authed.post(f"{PAGE}/zzz/resolve", data={"csrf": token}, follow_redirects=False)
    assert missing.headers["location"] == f"{PAGE}?err=not_found"


def test_closing_needs_a_valid_csrf_token_and_the_same_origin(authed, db):
    seed(db, farmer_row("F901"), request_row())
    assert authed.post(f"{PAGE}/r1/resolve", data={"csrf": "wrong", "note": "x"}, follow_redirects=False).status_code == 403
    assert authed.post(f"{PAGE}/r1/resolve", data={"note": "x"}, follow_redirects=False).status_code == 403
    token = csrf_from(authed, PAGE)
    foreign = authed.post(f"{PAGE}/r1/resolve", data={"csrf": token}, headers={"Origin": "https://evil.example"}, follow_redirects=False)
    assert foreign.status_code == 403
    db.expire_all()
    assert db.get(ExpertRequestRow, "r1").status == "open"


def test_an_oversized_note_is_refused_by_the_page(authed, db):
    seed(db, farmer_row("F901"), request_row())
    token = csrf_from(authed, PAGE)
    response = authed.post(f"{PAGE}/r1/resolve", data={"csrf": token, "note": "n" * 501}, follow_redirects=False)
    assert response.headers["location"] == f"{PAGE}?err=request_invalid"
    assert "Keep it under 500 characters." in authed.get(f"{PAGE}?err=request_invalid").text
    db.expire_all()
    assert db.get(ExpertRequestRow, "r1").status == "open"


def test_texts_from_farmers_are_escaped(authed, db):
    seed(db, farmer_row("F901", name="<i>Ravi</i>"), request_row(message=XSS, crop_id="<b>x</b>"))
    html = authed.get(PAGE).text
    assert XSS not in html and "<i>Ravi</i>" not in html and "<b>x</b>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "&lt;i&gt;Ravi&lt;/i&gt;" in html


def test_the_dashboard_counts_open_requests(authed, db):
    import re

    seed(db, farmer_row("F901"), request_row("a"), request_row("b"), request_row("c", status="resolved"))
    assert re.search(r"Open expert requests</dt><dd>2<", authed.get("/admin/dashboard").text)
    assert 'href="/admin/expert-requests"' in authed.get("/admin/dashboard").text


def test_the_page_shows_a_request_without_text(authed, db):
    seed(db, farmer_row("F901"), request_row(message=None))
    assert "(no text)" in authed.get(PAGE).text

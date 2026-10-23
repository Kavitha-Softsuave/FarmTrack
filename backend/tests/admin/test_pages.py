import re
from datetime import datetime

import pytest
from sqlalchemy import select

from app.admin import auth
from app.clock import IST
from app.config import get_settings
from app.db.models import AlertRow, AppSettingRow, AuditLogRow, ProductOverrideRow, ReviewTaskRow
from tests.admin.conftest import ADMIN_KEY, SECRET, seed, seed_review
from tests.integrations.fakes import NOW, FakeRules, farmer_row, make_settings, risk

PAGES = ["/admin/dashboard", "/admin/review", "/admin/farmers", "/admin/products", "/admin/alerts", "/admin/clock", "/admin/audit"]
XSS = "<script>alert(1)</script>"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


def login(client) -> None:
    response = client.post("/admin/login", data={"admin_key": ADMIN_KEY}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin/dashboard"


def csrf_from(client, path: str) -> str:
    html = client.get(path).text
    match = re.search(r'name="csrf" value="([0-9a-f]+)"', html)
    assert match, f"no csrf field on {path}"
    return match.group(1)


@pytest.fixture
def authed(client):
    login(client)
    return client


# ------------------------------------------------------------------------------------------------- login and session
@pytest.mark.parametrize("path", [*PAGES, "/admin/photos/scan1/0"])
def test_pages_redirect_to_login_when_signed_out(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin/login"


@pytest.mark.parametrize("path,data", [("/admin/logout", {}), ("/admin/alerts/run-now", {}), ("/admin/clock", {"now": "2026-05-01T08:00"}),
                                       ("/admin/products/P001/toggle", {"enabled": "0"}), ("/admin/review/t1/resolve", {})])
def test_posts_redirect_to_login_when_signed_out(client, path, data):
    response = client.post(path, data=data, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin/login"


def test_root_redirects_by_session_state(client):
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/admin/login"
    login(client)
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/admin/dashboard"
    assert client.get("/admin/login", follow_redirects=False).headers["location"] == "/admin/dashboard"


def test_login_page_and_security_headers(client):
    response = client.get("/admin/login")
    assert response.status_code == 200 and 'type="password"' in response.text and '<html lang="en">' in response.text
    headers = response.headers
    assert headers["cache-control"] == "no-store" and headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY" and headers["referrer-policy"] == "no-referrer"
    csp = headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src" not in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp


def test_wrong_key_is_refused_without_a_cookie(client):
    response = client.post("/admin/login", data={"admin_key": "nope"}, follow_redirects=False)
    assert response.status_code == 401 and "not correct" in response.text and "set-cookie" not in response.headers
    assert client.post("/admin/login", data={}, follow_redirects=False).status_code == 401


def test_session_cookie_flags_and_content(client):
    response = client.post("/admin/login", data={"admin_key": ADMIN_KEY}, follow_redirects=False)
    cookie = response.headers["set-cookie"]
    lowered = cookie.lower()
    assert "httponly" in lowered and "samesite=strict" in lowered and "path=/admin" in lowered and "max-age=" in lowered
    assert "secure" not in lowered.replace("samesite", "")                    # test environment is not prod
    value = cookie.split(";")[0].split("=", 1)[1]
    assert ADMIN_KEY not in cookie and SECRET not in cookie
    assert auth.read_session(get_settings(), value) is not None


def test_session_cookie_is_secure_in_production(client, monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()
    response = client.post("/admin/login", data={"admin_key": ADMIN_KEY}, follow_redirects=False)
    assert "; secure" in response.headers["set-cookie"].lower()


def test_the_apps_own_settings_take_precedence_over_the_environment(app, client, tmp_path):
    app.state.settings = make_settings(tmp_path, admin_api_key="app-level-key", secret_key="app-level-secret")
    assert client.post("/admin/login", data={"admin_key": ADMIN_KEY}).status_code == 401
    assert client.post("/admin/login", data={"admin_key": "app-level-key"}, follow_redirects=False).status_code == 303
    assert client.get("/admin/dashboard").status_code == 200


def test_login_is_throttled_after_repeated_failures(client):
    for _ in range(auth.LOGIN_FAILURES):
        assert client.post("/admin/login", data={"admin_key": "bad"}).status_code == 401
    blocked = client.post("/admin/login", data={"admin_key": ADMIN_KEY}, follow_redirects=False)
    assert blocked.status_code == 429 and "set-cookie" not in blocked.headers
    auth.login_throttle.reset()
    assert client.post("/admin/login", data={"admin_key": ADMIN_KEY}, follow_redirects=False).status_code == 303


def test_throttle_window_expires():
    now = [0.0]
    throttle = auth.LoginThrottle(clock=lambda: now[0])
    for _ in range(auth.LOGIN_FAILURES):
        throttle.fail("1.2.3.4")
    assert throttle.blocked("1.2.3.4") and not throttle.blocked("5.6.7.8")
    now[0] += auth.LOGIN_WINDOW_SECONDS + 1
    assert not throttle.blocked("1.2.3.4")


def test_forged_tampered_and_expired_cookies_are_rejected(client):
    for bad in ("garbage", "1.2.3", ".", "9999999999.abc.deadbeef", auth.issue_session(get_settings(), now=0.0), auth.issue_session(get_settings())[:-3] + "000"):
        client.cookies.clear()
        client.cookies.set(auth.COOKIE_NAME, bad, path="/admin")
        assert client.get("/admin/dashboard", follow_redirects=False).status_code == 303, bad
    forged = auth.issue_session(get_settings())
    payload, _, _ = forged.rpartition(".")
    client.cookies.clear()
    client.cookies.set(auth.COOKIE_NAME, f"{payload}.{'0' * 64}", path="/admin")
    assert client.get("/admin/dashboard", follow_redirects=False).status_code == 303


def test_rotating_the_admin_key_signs_everybody_out(client, monkeypatch):
    login(client)
    assert client.get("/admin/dashboard", follow_redirects=False).status_code == 200
    monkeypatch.setenv("ADMIN_API_KEY", "a-new-admin-key")
    get_settings.cache_clear()
    assert client.get("/admin/dashboard", follow_redirects=False).status_code == 303


def test_logout_needs_csrf_and_clears_the_session(authed):
    assert authed.post("/admin/logout", data={}, follow_redirects=False).status_code == 403
    token = csrf_from(authed, "/admin/dashboard")
    response = authed.post("/admin/logout", data={"csrf": token}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin/login"
    assert authed.get("/admin/dashboard", follow_redirects=False).status_code == 303


# ------------------------------------------------------------------------------------------------- pages render
def test_every_page_renders_accessibly_and_without_secrets(authed, db):
    seed_review(db)
    for path in PAGES:
        response = authed.get(path)
        assert response.status_code == 200, path
        html = response.text
        assert '<html lang="en">' in html and '<main id="main">' in html and 'class="skip"' in html and "<title>" in html
        assert 'aria-current="page"' in html and "<h1>" in html
        assert ADMIN_KEY not in html and SECRET not in html, path
        assert "<script" not in html.lower(), path                           # the pages need no JavaScript
        assert response.headers["content-security-policy"].startswith("default-src 'none'")
        for field in re.findall(r'<input[^>]+id="([^"]+)"', html):
            assert f'for="{field}"' in html, f"{path}: input {field} has no label"


def test_dashboard_shows_counts_clock_and_recent_items(authed, db, container):
    seed_review(db)
    container.rules = FakeRules([risk("scab_infection_risk", "red", episode="2026-05-04")])
    authed.post("/admin/alerts/run-now", data={"csrf": csrf_from(authed, "/admin/alerts")})
    html = authed.get("/admin/dashboard").text
    assert "12 May 2026 08:00" in html and "fixed by the admin" in html
    assert re.search(r"Open review tasks</dt><dd>1<", html) and re.search(r"Farmers</dt><dd>1<", html)
    assert "scab_infection_risk" in html and "alerts.run_now" in html


def test_stylesheet_is_public(client):
    response = client.get("/admin/static/admin.css")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/css") and "--accent" in response.text


# ------------------------------------------------------------------------------------------------- csrf
def test_state_changing_posts_need_the_csrf_token(authed, db):
    seed_review(db)
    posts = [("/admin/products/P001/toggle", {"enabled": "0"}), ("/admin/clock", {"now": "2026-07-12T09:00", "action": "set"}),
             ("/admin/alerts/run-now", {}), ("/admin/review/t1/resolve", {"note": "x"})]
    for path, data in posts:
        assert authed.post(path, data=data, follow_redirects=False).status_code == 403, path
        assert authed.post(path, data={**data, "csrf": "0" * 64}, follow_redirects=False).status_code == 403, path
    db.expire_all()
    assert db.get(ProductOverrideRow, "P001") is None and db.get(ReviewTaskRow, "t1").status == "open"
    assert db.get(AppSettingRow, "demo_clock") is None and db.scalar(select(AlertRow.id)) is None
    assert db.scalar(select(AuditLogRow.id)) is None


def test_a_token_from_another_session_is_refused(client, db):
    login(client)
    token = csrf_from(client, "/admin/products")
    client.cookies.clear()
    login(client)                                                              # a new session has a new nonce, hence a new token
    response = client.post("/admin/products/P001/toggle", data={"enabled": "0", "csrf": token}, follow_redirects=False)
    assert response.status_code == 403


def test_cross_origin_posts_are_refused_even_with_a_valid_token(authed, db):
    token = csrf_from(authed, "/admin/products")
    data = {"enabled": "0", "csrf": token}
    evil = authed.post("/admin/products/P001/toggle", data=data, headers={"origin": "https://evil.example"}, follow_redirects=False)
    assert evil.status_code == 403
    same = authed.post("/admin/products/P001/toggle", data=data, headers={"origin": "http://testserver"}, follow_redirects=False)
    assert same.status_code == 303
    assert authed.post("/admin/login", data={"admin_key": ADMIN_KEY}, headers={"origin": "https://evil.example"}).status_code == 403


# ------------------------------------------------------------------------------------------------- output escaping
def test_user_controlled_text_is_escaped_everywhere(authed, db, container):
    seed(db, farmer_row("F901", name=XSS, village='"><img src=x onerror=alert(1)>'))
    seed_review(db, crop_id=XSS)
    task = db.get(ReviewTaskRow, "t1")
    task.reason = f"{XSS} <b>bold</b>"
    db.commit()
    item = risk("scab_infection_risk", "red", episode="2026-05-04")
    item.title.en = XSS
    item.text.en = '<img src=x onerror="alert(2)">'
    container.rules = FakeRules([item])
    token = csrf_from(authed, "/admin/alerts")
    authed.post("/admin/alerts/run-now", data={"csrf": token})
    authed.post("/admin/products/P001/toggle", data={"enabled": "0", "note": XSS, "csrf": token})
    for path in ("/admin/farmers", "/admin/review", "/admin/alerts", "/admin/products", "/admin/audit", "/admin/dashboard"):
        html = authed.get(path).text
        assert XSS not in html and "<img src=x" not in html and "<b>bold</b>" not in html, path
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in authed.get("/admin/farmers").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &lt;b&gt;bold&lt;/b&gt;" in authed.get("/admin/review").text
    assert "&lt;img src=x onerror=&#34;alert(2)&#34;&gt;" in authed.get("/admin/alerts").text


def test_query_parameters_are_never_reflected(authed):
    html = authed.get(f"/admin/review?ok={XSS}&err={XSS}&status={XSS}").text
    assert "alert(1)" not in html and 'class="flash' not in html
    assert "Review task resolved." in authed.get("/admin/review?ok=resolved").text
    flash = authed.get("/admin/alerts?ok=alerts_run&n=3").text
    assert "Alert run finished: 3 new alerts." in flash and 'role="status"' in flash
    assert "Alert run finished: 3" not in authed.get("/admin/alerts?ok=alerts_run&n=3<b>").text
    error = authed.get("/admin/clock?err=bad_time").text
    assert 'role="alert"' in error and "could not be read" in error
    assert authed.get("/admin/products?crop=" + XSS).text.count("selected") == 0


# ------------------------------------------------------------------------------------------------- review queue
def test_review_page_shows_the_task_with_photos_and_a_resolve_form(authed, db):
    seed_review(db)
    html = authed.get("/admin/review").text
    assert "Scan scan1" in html and "Test Farmer F901" in html and "Alternaria or Marssonina" in html
    assert 'src="/admin/photos/scan1/0"' in html and 'alt="Photo 1 of 1 for scan scan1"' in html
    assert "Apple scab (Apple___Apple_scab), 61%" in html
    assert 'action="/admin/review/t1/resolve"' in html and 'name="confirmed_disease"' in html and 'name="release_advice"' in html
    assert '<option value="Apple___Apple_scab">' in html and '<option value="Apple">' in html
    assert "No review tasks" not in html


def test_review_status_filter_and_empty_state(authed, db):
    assert "No review tasks in this view." in authed.get("/admin/review").text
    seed_review(db)
    db.get(ReviewTaskRow, "t1").status = "resolved"
    db.commit()
    assert "Scan scan1" not in authed.get("/admin/review").text
    assert "Scan scan1" in authed.get("/admin/review?status=resolved").text and "Scan scan1" in authed.get("/admin/review?status=all").text
    assert 'aria-current="page">All' in authed.get("/admin/review?status=all").text


def test_photo_page_route_serves_images_to_a_signed_in_admin(authed, db):
    seed_review(db)
    path = get_settings().storage_dir / "photos" / "F901" / "scan1_0.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(JPEG)
    response = authed.get("/admin/photos/scan1/0")
    assert response.status_code == 200 and response.content == JPEG and response.headers["content-type"] == "image/jpeg"
    assert authed.get("/admin/photos/scan1/3").status_code == 404


def test_resolving_through_the_form(authed, db):
    seed_review(db)
    token = csrf_from(authed, "/admin/review")
    response = authed.post("/admin/review/t1/resolve", follow_redirects=False, data={
        "csrf": token, "confirmed_crop": "Apple", "confirmed_disease": "Apple___Marssonina_blotch", "note": "  looks like blotch  "})
    assert response.status_code == 303 and response.headers["location"] == "/admin/review?ok=resolved"
    db.expire_all()
    task = db.get(ReviewTaskRow, "t1")
    assert task.status == "resolved" and task.resolution["note"] == "looks like blotch"
    assert db.scalar(select(AuditLogRow.action)) == "review.resolve"
    again = authed.post("/admin/review/t1/resolve", data={"csrf": token}, follow_redirects=False)
    assert again.headers["location"] == "/admin/review?err=already_resolved"


@pytest.mark.parametrize("data,err", [({"confirmed_disease": "Made_Up"}, "invalid"), ({"note": "x" * 501}, "invalid"),
                                      ({"release_advice": "1"}, "invalid")])
def test_resolve_form_errors_become_flash_messages(authed, db, data, err):
    seed_review(db)
    token = csrf_from(authed, "/admin/review")
    response = authed.post("/admin/review/t1/resolve", data={"csrf": token, **data}, follow_redirects=False)
    assert response.headers["location"] == f"/admin/review?err={err}"
    assert authed.post("/admin/review/zzz/resolve", data={"csrf": token}, follow_redirects=False).headers["location"].endswith("not_found")


def test_release_checkbox_calls_the_hook_and_a_failure_keeps_the_task_open(app, authed, db):
    seed_review(db)
    calls = []
    app.state.release_advice = lambda session, task, body: calls.append(task.id) or False
    token = csrf_from(authed, "/admin/review")
    response = authed.post("/admin/review/t1/resolve", follow_redirects=False,
                           data={"csrf": token, "confirmed_disease": "Apple___Apple_scab", "release_advice": "1"})
    assert response.headers["location"] == "/admin/review?err=release_failed" and calls == ["t1"]
    db.expire_all()
    assert db.get(ReviewTaskRow, "t1").status == "open"


# ------------------------------------------------------------------------------------------------- farmers and products
def test_farmers_page_lists_farmers_without_phone_numbers(authed, db):
    seed(db, farmer_row("F901"), farmer_row("F902", language="hi", primary_crop="Potato"))
    html = authed.get("/admin/farmers").text
    assert "Test Farmer F901" in html and "Potato" in html and "2 farmers" in html
    assert "+91" not in html and "phone" in html.lower()                      # only the caption mentions phones


def test_products_page_lists_the_master_and_filters_by_crop(authed):
    html = authed.get("/admin/products").text
    assert html.count('action="/admin/products/P') == 97 and "97 products" in html
    apple = authed.get("/admin/products?crop=Apple").text
    assert apple.count('action="/admin/products/P') == 68 and '<option value="Apple" selected>' in apple
    assert authed.get("/admin/products?crop=Banana").text.count('action="/admin/products/P') == 97      # unknown crop is ignored


def test_toggling_a_product_through_the_form(authed, db):
    token = csrf_from(authed, "/admin/products")
    response = authed.post("/admin/products/P001/toggle", follow_redirects=False,
                           data={"csrf": token, "enabled": "0", "note": "agronomist said stop", "crop": "Apple"})
    assert response.status_code == 303 and response.headers["location"] == "/admin/products?ok=product_updated&crop=Apple"
    db.expire_all()
    row = db.get(ProductOverrideRow, "P001")
    assert row.enabled is False and row.note == "agronomist said stop"
    html = authed.get("/admin/products?crop=Apple&ok=product_updated").text
    assert "Product setting saved." in html and 'class="badge disabled">Disabled' in html and "agronomist said stop" in html
    assert ">Enable P001<" in html and ">Disable P002<" in html
    back = authed.post("/admin/products/P001/toggle", data={"csrf": token, "enabled": "1"}, follow_redirects=False)
    assert back.status_code == 303
    db.expire_all()
    assert db.get(ProductOverrideRow, "P001").enabled is True
    assert authed.post("/admin/products/P999/toggle", data={"csrf": token, "enabled": "0"},
                       follow_redirects=False).headers["location"].startswith("/admin/products?err=not_found")


# ------------------------------------------------------------------------------------------------- alerts, clock, audit
def test_alerts_page_run_now_and_log(authed, db, container):
    seed(db, farmer_row("F901"))
    container.rules = FakeRules([risk("scab_infection_risk", "red", episode="2026-05-04")])
    token = csrf_from(authed, "/admin/alerts")
    response = authed.post("/admin/alerts/run-now", data={"csrf": token}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin/alerts?ok=alerts_run&n=1"
    html = authed.get("/admin/alerts").text
    assert "scab_infection_risk title" in html and "F901" in html and 'class="badge red"' in html
    again = authed.post("/admin/alerts/run-now", data={"csrf": token}, follow_redirects=False)
    assert again.headers["location"] == "/admin/alerts?ok=alerts_run&n=0"
    assert [a for a in db.scalars(select(AuditLogRow.action))] == ["alerts.run_now", "alerts.run_now"]


def test_run_now_without_a_container_shows_a_message(app, authed):
    del app.state.container
    token = csrf_from(authed, "/admin/alerts")
    response = authed.post("/admin/alerts/run-now", data={"csrf": token}, follow_redirects=False)
    assert response.headers["location"] == "/admin/alerts?err=no_container"


def test_run_now_failure_is_reported_not_raised(authed, container):
    class Broken:
        def snapshot(self, *a):
            raise RuntimeError("x")

        def evaluate_risks(self, *a):
            raise RuntimeError("x")

    container.settings = None                                                  # run_once itself fails on the first line
    token = csrf_from(authed, "/admin/alerts")
    response = authed.post("/admin/alerts/run-now", data={"csrf": token}, follow_redirects=False)
    assert response.headers["location"] == "/admin/alerts?err=failed"


def test_clock_page_sets_and_clears_the_demo_clock(authed, db, container):
    html = authed.get("/admin/clock").text
    assert 'value="2026-05-12T08:00"' in html and "a time fixed by the admin" in html
    token = csrf_from(authed, "/admin/clock")
    response = authed.post("/admin/clock", data={"csrf": token, "now": "2026-07-12T09:30", "action": "set"}, follow_redirects=False)
    assert response.headers["location"] == "/admin/clock?ok=clock_set"
    assert container.clock.now() == datetime(2026, 7, 12, 9, 30, tzinfo=IST)
    db.expire_all()
    assert db.get(AppSettingRow, "demo_clock").value == {"now": "2026-07-12T09:30:00+05:30"}
    assert 'value="2026-07-12T09:30"' in authed.get("/admin/clock").text
    authed.post("/admin/clock", data={"csrf": token, "action": "real"}, follow_redirects=False)
    assert container.clock.is_fixed is False and "the real time" in authed.get("/admin/clock").text
    db.expire_all()
    assert db.get(AppSettingRow, "demo_clock").value == {"now": None}


@pytest.mark.parametrize("bad", ["", "yesterday", "2026-13-45T99:99", "<script>"])
def test_bad_clock_input_changes_nothing(authed, container, bad):
    token = csrf_from(authed, "/admin/clock")
    response = authed.post("/admin/clock", data={"csrf": token, "now": bad, "action": "set"}, follow_redirects=False)
    assert response.headers["location"] == "/admin/clock?err=bad_time"
    assert container.clock.now() == NOW


def test_audit_page_shows_admin_actions(authed):
    token = csrf_from(authed, "/admin/products")
    authed.post("/admin/products/P001/toggle", data={"csrf": token, "enabled": "0"})
    html = authed.get("/admin/audit").text
    assert "product.disable" in html and "P001" in html and "&#34;note&#34;" not in html

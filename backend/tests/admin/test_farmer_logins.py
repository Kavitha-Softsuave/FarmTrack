"""Admin: set a farmer's login, create a farmer (API and pages). Passwords are stored hashed and never echoed or audited."""
import pytest
from sqlalchemy import select

from app.api.deps import require_admin
from app.db.models import AuditLogRow, FarmerRow, RefreshTokenRow
from app.security.passwords import verify_password
from tests.admin.conftest import seed
from tests.admin.test_pages import csrf_from, login
from tests.integrations.fakes import NOW, farmer_row

BASE = "/admin/api/v1"
PAGE = "/admin/farmers"
SECRET_PASSWORD = "s3cret-pass-ZZ"
NEW_FARMER = {"name": "Kamla Devi", "phone": "98765 43210", "language": "en", "district": "Shimla", "village": "Jubbal",
              "primary_crop": "Apple", "other_crops": ["Potato", "Apple", " "], "phenology_band": "B2", "elevation_m": 2050,
              "username": "Kamla.Devi", "password": SECRET_PASSWORD}


@pytest.fixture
def authed(client):
    login(client)
    return client


def fresh(db, farmer_id: str) -> FarmerRow:
    db.expire_all()
    row = db.get(FarmerRow, farmer_id)
    assert row is not None
    return row


def audit(db, action: str) -> list[AuditLogRow]:
    db.expire_all()
    return list(db.scalars(select(AuditLogRow).where(AuditLogRow.action == action)))


# ------------------------------------------------------------------------------------------------- set login: API
def test_set_login_is_behind_the_admin_key(app, client, db):
    from fastapi import HTTPException

    def refuse():
        raise HTTPException(401, "no key")

    app.dependency_overrides[require_admin] = refuse
    assert client.post(f"{BASE}/farmers/F901/login", json={}).status_code == 401
    assert client.post(f"{BASE}/farmers", json={}).status_code == 401


def test_set_login_stores_a_lower_case_name_and_only_a_hash(client, db):
    seed(db, farmer_row("F901"))
    response = client.post(f"{BASE}/farmers/F901/login", json={"username": "  Dinesh.S ", "password": SECRET_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "F901" and body["username"] == "dinesh.s" and body["has_login"] is True
    assert SECRET_PASSWORD not in response.text and "password" not in body
    row = fresh(db, "F901")
    assert row.username == "dinesh.s" and row.password_hash != SECRET_PASSWORD and SECRET_PASSWORD not in row.password_hash
    assert row.password_hash.startswith("pbkdf2_sha256$") and verify_password(SECRET_PASSWORD, row.password_hash)


def test_set_login_is_audited_without_the_password(client, db):
    seed(db, farmer_row("F901"))
    client.post(f"{BASE}/farmers/F901/login", json={"username": "dinesh.s", "password": SECRET_PASSWORD})
    [entry] = audit(db, "farmer.set_login")
    assert entry.entity == "farmer" and entry.entity_id == "F901"
    assert entry.detail["username"] == "dinesh.s"
    assert SECRET_PASSWORD not in str(entry.detail) and "password" not in entry.detail


def test_a_duplicate_username_is_a_409_and_changes_nothing(client, db):
    seed(db, farmer_row("F901"), farmer_row("F902"))
    assert client.post(f"{BASE}/farmers/F901/login", json={"username": "taken.name", "password": "password-1"}).status_code == 200
    clash = client.post(f"{BASE}/farmers/F902/login", json={"username": "TAKEN.name", "password": "password-2"})
    assert clash.status_code == 409
    assert fresh(db, "F902").username is None and fresh(db, "F902").password_hash is None
    assert verify_password("password-1", fresh(db, "F901").password_hash)


def test_a_farmer_may_keep_their_own_username_and_change_the_password(client, db):
    seed(db, farmer_row("F901"))
    client.post(f"{BASE}/farmers/F901/login", json={"username": "same.name", "password": "password-1"})
    again = client.post(f"{BASE}/farmers/F901/login", json={"username": "same.name", "password": "password-2"})
    assert again.status_code == 200
    assert verify_password("password-2", fresh(db, "F901").password_hash)


@pytest.mark.parametrize("body", [
    {"username": "ab", "password": "password-1"}, {"username": "a" * 41, "password": "password-1"},
    {"username": "has space", "password": "password-1"}, {"username": "bad/name", "password": "password-1"},
    {"username": "good.name", "password": "12345"}, {"username": "good.name", "password": ""}, {"username": "good.name"},
    {"password": "password-1"}, {"username": "good.name", "password": "x" * 129}])
def test_invalid_values_are_a_422(client, db, body):
    seed(db, farmer_row("F901"))
    assert client.post(f"{BASE}/farmers/F901/login", json=body).status_code == 422
    assert fresh(db, "F901").username is None and audit(db, "farmer.set_login") == []


def test_a_six_character_password_with_no_other_rule_is_accepted(client, db):
    seed(db, farmer_row("F901"))
    assert client.post(f"{BASE}/farmers/F901/login", json={"username": "good.name", "password": "aaaaaa"}).status_code == 200


def test_set_login_for_an_unknown_farmer_is_a_404(client):
    assert client.post(f"{BASE}/farmers/NOPE/login", json={"username": "good.name", "password": "password-1"}).status_code == 404


def test_a_reset_ends_the_farmers_open_sessions(client, db):
    seed(db, farmer_row("F901"), farmer_row("F902"))
    seed(db, RefreshTokenRow(id="rt1", farmer_id="F901", token_hash="h1", device_id="p1", expires_at=NOW, revoked=False),
         RefreshTokenRow(id="rt2", farmer_id="F902", token_hash="h2", device_id="p2", expires_at=NOW, revoked=False))
    client.post(f"{BASE}/farmers/F901/login", json={"username": "good.name", "password": "password-1"})
    db.expire_all()
    assert db.get(RefreshTokenRow, "rt1").revoked is True and db.get(RefreshTokenRow, "rt2").revoked is False


def test_the_farmer_list_shows_the_login_state_but_never_a_hash(client, db):
    seed(db, farmer_row("F901"), farmer_row("F902"))
    client.post(f"{BASE}/farmers/F901/login", json={"username": "good.name", "password": "password-1"})
    listed = {f["id"]: f for f in client.get(f"{BASE}/farmers").json()}
    assert listed["F901"]["has_login"] is True and listed["F901"]["username"] == "good.name"
    assert listed["F902"]["has_login"] is False and listed["F902"]["username"] is None
    assert "pbkdf2" not in client.get(f"{BASE}/farmers").text


# ------------------------------------------------------------------------------------------------- create farmer: API
def test_create_farmer_saves_the_record_with_a_login(client, db):
    seed(db, farmer_row("F901"))
    response = client.post(f"{BASE}/farmers", json=NEW_FARMER)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == "F902" and body["username"] == "kamla.devi" and body["has_login"] is True
    assert SECRET_PASSWORD not in response.text
    row = fresh(db, "F902")
    assert (row.name, row.phone, row.language, row.district, row.village) == ("Kamla Devi", "+919876543210", "en", "Shimla", "Jubbal")
    assert row.primary_crop == "Apple" and row.crops == ["Apple", "Potato"]
    assert (row.phenology_band, row.elevation_m, row.username) == ("B2", 2050.0, "kamla.devi")
    assert verify_password(SECRET_PASSWORD, row.password_hash) and row.created_at is not None


def test_the_first_farmer_of_an_empty_database_is_f001(client, db):
    assert client.post(f"{BASE}/farmers", json=NEW_FARMER).json()["id"] == "F001"


def test_create_farmer_needs_only_the_small_required_set(client, db):
    minimal = {"name": "A", "phone": "+919876500001", "primary_crop": "Apple", "username": "minimal.user", "password": "password-1"}
    response = client.post(f"{BASE}/farmers", json=minimal)
    assert response.status_code == 201
    row = fresh(db, response.json()["id"])
    assert row.language == "hi" and row.crops == ["Apple"] and row.district is None and row.elevation_m is None


def test_create_farmer_is_audited_without_the_password(client, db):
    client.post(f"{BASE}/farmers", json=NEW_FARMER)
    [entry] = audit(db, "farmer.create")
    assert entry.detail["username"] == "kamla.devi"
    assert SECRET_PASSWORD not in str(entry.detail) and "9876543210" not in str(entry.detail)


def test_create_farmer_with_a_taken_username_is_a_409(client, db):
    seed(db, farmer_row("F901", username="kamla.devi"))
    assert client.post(f"{BASE}/farmers", json=NEW_FARMER).status_code == 409
    assert len(list(db.scalars(select(FarmerRow)))) == 1


def test_create_farmer_with_a_taken_phone_is_a_409(client, db):
    seed(db, farmer_row("F901", phone="+919876543210"))
    assert client.post(f"{BASE}/farmers", json=NEW_FARMER).status_code == 409
    assert len(list(db.scalars(select(FarmerRow)))) == 1


@pytest.mark.parametrize("change", [
    {"username": "no"}, {"password": "short"}, {"phone": "abc"}, {"phone": "1234"}, {"name": ""}, {"name": "   "},
    {"language": "fr"}, {"primary_crop": ""}, {"elevation_m": -5}, {"elevation_m": 99999}, {"phenology_band": "B3B3B3"},
    {"district": "d" * 61}, {"other_crops": ["c" * 41]}, {"other_crops": ["a"] * 11}])
def test_create_farmer_rejects_invalid_values(client, db, change):
    assert client.post(f"{BASE}/farmers", json={**NEW_FARMER, **change}).status_code == 422
    assert list(db.scalars(select(FarmerRow))) == []


# ------------------------------------------------------------------------------------------------- the farmers page
def test_the_farmers_page_has_a_set_login_form_per_farmer_and_a_create_form(authed, db):
    seed(db, farmer_row("F901"), farmer_row("F902"))
    html = authed.get(PAGE).text
    assert 'action="/admin/farmers/F901/login"' in html and 'action="/admin/farmers/F902/login"' in html
    assert 'action="/admin/farmers"' in html and "Create farmer" in html
    assert html.count('type="password"') == 3 and 'autocomplete="new-password"' in html
    assert "+91000" not in html                                                   # phone numbers stay hidden on this page


def test_the_page_shows_the_username_and_never_a_hash_or_password(authed, db):
    seed(db, farmer_row("F901"))
    authed.post(f"{BASE}/farmers/F901/login", json={"username": "good.name", "password": SECRET_PASSWORD})
    html = authed.get(PAGE).text
    assert 'value="good.name"' in html and "Login set" in html
    assert SECRET_PASSWORD not in html and "pbkdf2" not in html


def test_set_login_through_the_page(authed, db):
    seed(db, farmer_row("F901"))
    token = csrf_from(authed, PAGE)
    response = authed.post("/admin/farmers/F901/login", data={"csrf": token, "username": "Good.Name", "password": SECRET_PASSWORD},
                           follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"{PAGE}?ok=login_saved"
    assert fresh(db, "F901").username == "good.name" and verify_password(SECRET_PASSWORD, fresh(db, "F901").password_hash)
    assert "Login saved" in authed.get(f"{PAGE}?ok=login_saved").text
    assert SECRET_PASSWORD not in str([e.detail for e in audit(db, "farmer.set_login")])


def test_set_login_through_the_page_needs_the_csrf_token(authed, db):
    seed(db, farmer_row("F901"))
    for data in ({"username": "good.name", "password": "password-1"},
                 {"csrf": "0" * 64, "username": "good.name", "password": "password-1"}):
        assert authed.post("/admin/farmers/F901/login", data=data, follow_redirects=False).status_code == 403
    assert fresh(db, "F901").username is None


def test_set_login_through_the_page_refuses_a_foreign_origin(authed, db):
    seed(db, farmer_row("F901"))
    token = csrf_from(authed, PAGE)
    response = authed.post("/admin/farmers/F901/login", data={"csrf": token, "username": "good.name", "password": "password-1"},
                           headers={"origin": "https://evil.example"}, follow_redirects=False)
    assert response.status_code == 403 and fresh(db, "F901").username is None


def test_set_login_through_the_page_when_signed_out(client, db):
    seed(db, farmer_row("F901"))
    response = client.post("/admin/farmers/F901/login", data={"username": "good.name", "password": "password-1"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin/login"
    assert fresh(db, "F901").username is None


@pytest.mark.parametrize("data,err", [({"username": "no", "password": "password-1"}, "login_invalid"),
                                      ({"username": "good.name", "password": "short"}, "login_invalid"),
                                      ({"username": "taken.one", "password": "password-1"}, "username_taken")])
def test_set_login_page_errors_come_back_as_a_flash(authed, db, data, err):
    seed(db, farmer_row("F901"), farmer_row("F902", username="taken.one"))
    token = csrf_from(authed, PAGE)
    response = authed.post("/admin/farmers/F901/login", data={"csrf": token, **data}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"{PAGE}?err={err}"
    assert fresh(db, "F901").username is None


def test_set_login_page_for_an_unknown_farmer(authed):
    token = csrf_from(authed, PAGE)
    response = authed.post("/admin/farmers/NOPE/login", data={"csrf": token, "username": "good.name", "password": "password-1"},
                           follow_redirects=False)
    assert response.headers["location"] == f"{PAGE}?err=not_found"


def test_create_farmer_through_the_page(authed, db):
    token = csrf_from(authed, PAGE)
    form = {"csrf": token, "name": "Kamla Devi", "phone": "+919876543210", "language": "en", "district": "Shimla", "village": "Jubbal",
            "primary_crop": "Apple", "other_crops": "Potato, Tomato", "phenology_band": "B2", "elevation_m": "2050",
            "username": "Kamla.Devi", "password": SECRET_PASSWORD}
    response = authed.post(PAGE, data=form, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"{PAGE}?ok=farmer_created"
    row = fresh(db, "F001")
    assert row.username == "kamla.devi" and row.crops == ["Apple", "Potato", "Tomato"] and row.elevation_m == 2050.0
    assert verify_password(SECRET_PASSWORD, row.password_hash)
    assert "Kamla Devi" in authed.get(PAGE).text


def test_create_farmer_page_needs_the_csrf_token(authed, db):
    form = {"name": "Kamla Devi", "phone": "+919876543210", "primary_crop": "Apple", "username": "kamla.devi", "password": "password-1"}
    assert authed.post(PAGE, data=form, follow_redirects=False).status_code == 403
    assert authed.post(PAGE, data={**form, "csrf": "bad"}, follow_redirects=False).status_code == 403
    assert list(db.scalars(select(FarmerRow))) == []


@pytest.mark.parametrize("change,err", [({"username": "no"}, "farmer_invalid"), ({"password": "short"}, "farmer_invalid"),
                                        ({"phone": "abc"}, "farmer_invalid"), ({"elevation_m": "high"}, "farmer_invalid"),
                                        ({"name": ""}, "farmer_invalid"), ({"username": "taken.one"}, "username_taken"),
                                        ({"phone": "+919876500000"}, "phone_taken")])
def test_create_farmer_page_errors_come_back_as_a_flash(authed, db, change, err):
    seed(db, farmer_row("F901", username="taken.one", phone="+919876500000"))
    token = csrf_from(authed, PAGE)
    form = {"csrf": token, "name": "Kamla Devi", "phone": "+919876543210", "primary_crop": "Apple", "username": "kamla.devi",
            "password": "password-1", **change}
    response = authed.post(PAGE, data=form, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"{PAGE}?err={err}"
    assert len(list(db.scalars(select(FarmerRow)))) == 1


def test_the_page_keeps_its_security_headers(authed):
    response = authed.get(PAGE)
    assert "form-action 'self'" in response.headers["content-security-policy"] and response.headers["cache-control"] == "no-store"


# ------------------------------------------------------------------------------------------------- the owner dropped the expert call
def test_the_expert_requests_page_does_not_show_phone_numbers(authed, db):
    from app.db.models import ExpertRequestRow

    seed(db, farmer_row("F901", phone="+919876543210"),
         ExpertRequestRow(id="r1", farmer_id="F901", status="open", created_at=NOW, message="leaves are curling"))
    page = authed.get("/admin/expert-requests")
    api = authed.get(f"{BASE}/expert-requests")
    assert "leaves are curling" in page.text
    assert "9876543210" not in page.text and "9876543210" not in api.text and "phone" not in api.text

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.clock import IST
from app.db.migrate import upgrade_to_head
from app.db.models import FarmerRow
from app.db.seed import add_missing_demo_logins, seed_enabled, seed_farmers, seed_if_enabled
from app.db.session import init_db, session_scope
from app.main import create_app
from app.security.passwords import verify_password
from tests.fakes import NOW, make_container, plain_settings

PROD = dict(env="prod", secret_key="k" * 40, admin_api_key="a" * 24, cors_origins=["https://farm.example"], demo_clock=None)


@pytest.fixture
def seeded(api_settings):
    init_db()
    with session_scope() as db:
        assert seed_farmers(db, api_settings.data_dir, NOW) == 50
    return api_settings


def farmer(farmer_id):
    with session_scope() as db:
        return db.get(FarmerRow, farmer_id)


def test_all_fifty_demo_farmers_are_loaded(seeded):
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(FarmerRow)) == 50
        assert {f.id for f in db.scalars(select(FarmerRow))} == {f"F{i:03d}" for i in range(1, 51)}


def test_fields_are_mapped_from_the_csv(seeded):
    f = farmer("F001")
    assert f.name == "Dinesh Sharma" and f.phone == "+910000000001" and f.language == "hi"
    assert f.district == "Shimla" and f.village == "Theog" and f.station_id == "ST01"
    assert f.elevation_m == 2117 and f.phenology_band == "B3" and f.primary_crop == "Apple" and f.primary_variety == "Royal_Delicious"
    assert f.zoho_contact_id == "9990000000000000001"
    assert farmer("F002").language == "en"


def test_crops_are_primary_plus_other_crops_without_duplicates(seeded):
    assert farmer("F001").crops == ["Apple"]
    assert farmer("F003").crops == ["Apple", "Potato"]
    with session_scope() as db:
        multi = [f for f in db.scalars(select(FarmerRow)) if len(f.crops) > 1]
        assert multi and all(len(set(f.crops)) == len(f.crops) and f.crops[0] == f.primary_crop for f in multi)


def test_coordinates_come_from_the_station_table(seeded):
    f = farmer("F001")
    assert (f.lat, f.lon) == (31.12, 77.36)
    with session_scope() as db:
        assert all(f.lat is not None and f.lon is not None for f in db.scalars(select(FarmerRow)))


def test_phones_are_normalised_and_unique(seeded):
    with session_scope() as db:
        phones = [f.phone for f in db.scalars(select(FarmerRow))]
        assert len(set(phones)) == 50 and all(p.startswith("+91") and p[1:].isdigit() and len(p) == 13 for p in phones)


def test_created_at_comes_from_the_clock(seeded):
    created = farmer("F001").created_at
    assert created.replace(tzinfo=None) == datetime(2026, 5, 12, 8, 0)


def test_seeding_only_happens_into_an_empty_table(seeded):
    with session_scope() as db:
        assert seed_farmers(db, seeded.data_dir, NOW) == 0
        db.query(FarmerRow).filter(FarmerRow.id == "F050").update({"name": "Changed"})
    with session_scope() as db:
        assert seed_farmers(db, seeded.data_dir, NOW) == 0
        assert db.get(FarmerRow, "F050").name == "Changed"


def test_seed_if_enabled_loads_outside_production(api_settings):
    init_db()
    assert seed_if_enabled(api_settings, NOW) == 50
    assert seed_if_enabled(api_settings, NOW) == 0


def test_seeding_is_off_in_production_unless_asked(monkeypatch):
    prod = plain_settings(**PROD)
    monkeypatch.delenv("SEED_DEMO", raising=False)
    assert not seed_enabled(prod)
    monkeypatch.setenv("SEED_DEMO", "1")
    assert seed_enabled(prod)
    monkeypatch.setenv("SEED_DEMO", "true")
    assert not seed_enabled(prod)                       # exactly "1"
    assert seed_enabled(plain_settings(env="dev"))


def test_a_production_start_does_not_seed_without_the_switch(monkeypatch, api_settings):
    monkeypatch.delenv("SEED_DEMO", raising=False)
    upgrade_to_head(api_settings.database_url)          # in production the schema comes from migrations
    prod = api_settings.model_copy(update=PROD)
    container = make_container(prod)
    with TestClient(create_app(prod, container_factory=lambda _s: container)):
        pass
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(FarmerRow)) == 0


def test_a_production_start_seeds_with_the_switch(monkeypatch, api_settings):
    monkeypatch.setenv("SEED_DEMO", "1")
    upgrade_to_head(api_settings.database_url)
    prod = api_settings.model_copy(update=PROD)
    container = make_container(prod)
    with TestClient(create_app(prod, container_factory=lambda _s: container)):
        pass
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(FarmerRow)) == 50
        assert db.get(FarmerRow, "F001").created_at.replace(tzinfo=None) == NOW.replace(tzinfo=None)


def test_the_dev_startup_creates_tables_and_seeds_through_the_lifespan(api_client):
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(FarmerRow)) == 50


def test_ist_timezone_constant_matches_the_models():
    assert NOW.tzinfo == IST


# ------------------------------------------------------------------------------------------------- demo logins
@pytest.fixture
def seeded_without_password(api_settings):
    init_db()
    with session_scope() as db:
        assert seed_farmers(db, api_settings.data_dir, NOW) == 50
    return api_settings


def test_demo_farmers_get_their_id_in_lower_case_as_username_and_the_demo_password(api_settings):
    init_db()
    seed_if_enabled(api_settings, NOW)
    with session_scope() as db:
        farmers = list(db.scalars(select(FarmerRow)))
        assert {f.username for f in farmers} == {f"f{i:03d}" for i in range(1, 51)}
        assert all(f.username == f.id.lower() for f in farmers)
        assert all(verify_password(api_settings.demo_password, f.password_hash) for f in farmers)
        assert api_settings.demo_password == "farm1234" and "farm1234" not in farmers[0].password_hash
        assert len({f.password_hash for f in farmers}) == 50                     # every hash has its own salt


def test_the_demo_password_comes_from_the_setting(monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "custom-demo-pass")
    settings = plain_settings()
    init_db()
    seed_if_enabled(settings, NOW)
    f = farmer("F001")
    assert verify_password("custom-demo-pass", f.password_hash) and not verify_password("farm1234", f.password_hash)


def test_seeding_without_a_password_sets_no_password(seeded_without_password):
    f = farmer("F001")
    assert f.username == "f001" and f.password_hash is None


def test_a_production_start_with_the_switch_seeds_logins(monkeypatch, api_settings):
    monkeypatch.setenv("SEED_DEMO", "1")
    upgrade_to_head(api_settings.database_url)
    prod = api_settings.model_copy(update=PROD)
    container = make_container(prod)
    with TestClient(create_app(prod, container_factory=lambda _s: container)) as client:
        assert client.post("/v1/auth/login", json={"username": "f001", "password": "farm1234"}).status_code == 200


def test_a_production_start_without_the_switch_has_no_farmer_to_log_in(monkeypatch, api_settings):
    monkeypatch.delenv("SEED_DEMO", raising=False)
    upgrade_to_head(api_settings.database_url)
    prod = api_settings.model_copy(update=PROD)
    container = make_container(prod)
    with TestClient(create_app(prod, container_factory=lambda _s: container)) as client:
        assert client.post("/v1/auth/login", json={"username": "f001", "password": "farm1234"}).status_code == 401
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(FarmerRow).where(FarmerRow.password_hash.is_not(None))) == 0


def test_an_older_dev_database_gets_the_demo_logins_added_at_startup(seeded_without_password):
    with session_scope() as db:
        db.query(FarmerRow).update({FarmerRow.username: None})                    # a database from before the login columns
        db.get(FarmerRow, "F002").username = "own.name"
        db.get(FarmerRow, "F002").password_hash = "pbkdf2_sha256$1000$00$00"
        db.get(FarmerRow, "F004").username = "own.name2"                          # has another name but no password: left alone
        db.add(FarmerRow(id="X900", name="Admin made", phone="+919000000900", language="hi", crops=[], created_at=NOW,
                         username="f003"))                                        # another farmer already holds the name f003
    assert seed_if_enabled(seeded_without_password, NOW) == 0                    # nothing seeded: the table is not empty
    with session_scope() as db:
        assert verify_password("farm1234", db.get(FarmerRow, "F001").password_hash) and db.get(FarmerRow, "F001").username == "f001"
        assert db.get(FarmerRow, "F002").username == "own.name" and db.get(FarmerRow, "F002").password_hash.endswith("$00")
        assert db.get(FarmerRow, "F003").username is None and db.get(FarmerRow, "F003").password_hash is None   # name taken
        assert db.get(FarmerRow, "F004").username == "own.name2" and db.get(FarmerRow, "F004").password_hash is None
        assert db.get(FarmerRow, "X900").password_hash is None                   # not a demo farmer: untouched


def test_backfill_gives_only_logins_that_are_missing(seeded_without_password):
    with session_scope() as db:
        assert add_missing_demo_logins(db, seeded_without_password.data_dir, "farm1234") == 50
        assert add_missing_demo_logins(db, seeded_without_password.data_dir, "other-pass") == 0
        assert verify_password("farm1234", db.get(FarmerRow, "F010").password_hash)

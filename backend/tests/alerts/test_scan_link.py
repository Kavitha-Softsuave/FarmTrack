"""Alerts about a spray that was logged from a scan's advice carry that scan's id, so the app can open the scan."""
from datetime import datetime

from app.alerts.evaluator import run_once
from app.clock import IST
from app.db.models import AdviceRow, AlertRow, ScanRow
from tests.alerts.test_evaluator import HEAVY, at, seed
from tests.integrations.fakes import (
    FakePush,
    FakeRules,
    device_row,
    farmer_row,
    make_container,
    risk,
    spray_log_row,
)

SPRAYED = "2026-03-30T08:00"


def scan_with_advice(farmer_id="F901", scan_id="scan-1", advice_id="advice-1"):
    created = datetime(2026, 3, 30, 7, 0, tzinfo=IST)
    return [ScanRow(id=scan_id, farmer_id=farmer_id, created_at=created, status="ok", result={}),
            AdviceRow(id=advice_id, scan_id=scan_id, farmer_id=farmer_id, crop_id="Apple", severity="yellow", payload={"products": []},
                      created_at=created)]


def washoff_rules():
    """The rules engine reports the wash-off of the spray made at 08:00 on 30 March (detail.spray_at, like the real one)."""
    return FakeRules(lambda farmer, weather, now, history: [
        risk("rain_washoff", "red", spray_at="2026-03-30T08:00:00+05:30", rain_mm=15.3)] if history else [])


def run(db, tmp_path, rules, now="2026-03-30T20:00", push=None):
    container = make_container(tmp_path, now=at(now), rules=rules, push=push or FakePush())
    return run_once(db, container), container


def test_the_wash_off_reminder_points_to_the_scan_the_spray_came_from(db, tmp_path):
    seed(db, farmer_row("F901", station_id="ST02"), *scan_with_advice(),
         spray_log_row("F901", at(SPRAYED), product_id="P007", advice_id="advice-1"))
    created, _ = run(db, tmp_path, washoff_rules())
    assert [a.kind for a in created] == ["rain_washoff"]
    assert created[0].payload["scan_id"] == "scan-1" and created[0].payload["risk_id"] == "rain_washoff"


def test_the_push_for_that_reminder_carries_the_scan_id(db, tmp_path):
    seed(db, farmer_row("F901", station_id="ST02"), device_row("F901"), *scan_with_advice(),
         spray_log_row("F901", at(SPRAYED), product_id="P007", advice_id="advice-1"))
    push = FakePush()
    run(db, tmp_path, washoff_rules(), push=push)
    assert push.sent[0]["data"]["scan_id"] == "scan-1" and push.sent[0]["data"]["kind"] == "rain_washoff"


def test_a_spray_that_was_not_taken_from_an_advice_has_no_scan(db, tmp_path):
    seed(db, farmer_row("F901", station_id="ST02"), spray_log_row("F901", at(SPRAYED), product_id="P007"))
    created, _ = run(db, tmp_path, washoff_rules())
    assert len(created) == 1 and "scan_id" not in created[0].payload


def test_only_the_matching_spray_is_linked(db, tmp_path):
    other = spray_log_row("F901", at("2026-03-29T08:00"), product_id="P007", advice_id="advice-old")
    seed(db, farmer_row("F901", station_id="ST02"), *scan_with_advice(), *scan_with_advice(scan_id="scan-old", advice_id="advice-old"),
         other, spray_log_row("F901", at(SPRAYED), product_id="P007", advice_id="advice-1"))
    created, _ = run(db, tmp_path, washoff_rules())
    assert created[0].payload["scan_id"] == "scan-1"                       # not the earlier spray's scan


def test_another_farmers_advice_is_never_linked(db, tmp_path):
    seed(db, farmer_row("F901", station_id="ST02"), farmer_row("F902", station_id="ST02"), *scan_with_advice("F902"),
         spray_log_row("F901", at(SPRAYED), product_id="P007", advice_id="advice-1"))
    created, _ = run(db, tmp_path, washoff_rules())
    assert [a.farmer_id for a in created] == ["F901"] and "scan_id" not in created[0].payload


def test_weather_risks_have_no_scan(db, tmp_path):
    seed(db, farmer_row("F901"), *scan_with_advice(), spray_log_row("F901", at("2026-05-01T09:00"), product_id="P007", advice_id="advice-1"))
    created, _ = run(db, tmp_path, FakeRules([risk("scab_infection_risk", "red", episode="2026-05-04")]), now="2026-05-12T08:00")
    assert len(created) == 1 and "scan_id" not in created[0].payload


def test_the_waiting_period_alert_points_to_the_scan_of_that_spray(db, tmp_path):
    seed(db, farmer_row("F901"), *scan_with_advice(),
         spray_log_row("F901", at("2026-08-20T10:00"), product_id=HEAVY.product_id, advice_id="advice-1"))
    created, _ = run(db, tmp_path, FakeRules(), now="2026-08-25T08:00")
    assert [a.kind for a in created] == ["waiting_period"] and created[0].payload["scan_id"] == "scan-1"


# ------------------------------------------------------------------------------------------------ the API field
def stored_alert(client_db, **values):
    row = AlertRow(farmer_id="F001", kind=values.pop("kind", "rain_washoff"), level="red", dedupe_key=values.pop("key", "k"),
                   title={"en": "T", "hi": "शी"}, body={"en": "B", "hi": "बॉ"}, spoken={}, created_at=at("2026-05-12T07:00"), **values)
    client_db.add(row)
    client_db.commit()
    return row.id


def test_the_api_exposes_scan_id_when_the_alert_is_about_a_scan(api_client, auth):
    from app.db.session import session_scope

    with session_scope() as db:
        about_scan = stored_alert(db, key="a", payload={"scan_id": "abc123", "risk_id": "rain_washoff"})
        plain = stored_alert(db, key="b", kind="scab_infection_risk", payload={"risk_id": "scab_infection_risk"})
        empty = stored_alert(db, key="c", payload={})
        odd = stored_alert(db, key="d", payload={"scan_id": 12})
    items = {a["id"]: a for a in api_client.get("/v1/alerts", headers=auth).json()["items"]}
    assert items[about_scan]["scan_id"] == "abc123"
    assert items[plain]["scan_id"] is None and items[empty]["scan_id"] is None and items[odd]["scan_id"] is None
    assert api_client.post(f"/v1/alerts/{about_scan}/read", headers=auth).json()["scan_id"] == "abc123"


def test_the_expert_advice_alert_links_to_its_scan(api_client, auth, fake_container):
    from app.db.models import AlertRow as Alert
    from app.db.session import session_scope
    from app.services.expert_release import _notify

    with session_scope() as db:
        from app.db.models import FarmerRow

        _notify(fake_container, db, db.get(FarmerRow, "F001"), "scan-77", "task-1")
        assert db.query(Alert).one().payload == {"scan_id": "scan-77"}
    item = api_client.get("/v1/alerts", headers=auth).json()["items"][0]
    assert item["kind"] == "expert_advice" and item["scan_id"] == "scan-77"


def test_scan_id_is_optional_in_the_contract(api_app):
    schema = api_app.openapi()["components"]["schemas"]["AlertOut"]
    assert "scan_id" in schema["properties"] and "scan_id" not in schema.get("required", [])


def test_end_to_end_scan_tick_rain_reminder_opens_the_scan(api_client, auth, fake_container):
    """Scan -> 'I sprayed this' (advice id only) -> the rain wash-off reminder -> GET /v1/alerts carries the scan id."""
    from app.db.session import session_scope
    from app.domain.types import RiskItem, Severity
    from tests.fakes import lt
    from tests.imaging import photo_files

    scan = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    tick = api_client.post("/v1/spray-logs", json={"crop_id": "Apple", "advice_id": scan["advice"]["id"]}, headers=auth).json()
    fake_container.rules.risks = [RiskItem(id="rain_washoff", level=Severity.red, title=lt("Rain washed it off"),
                                           text=lt("Repeat the spray."), detail={"spray_at": tick["sprayed_at"]})]
    with session_scope() as db:
        created = run_once(db, fake_container)                       # every seeded farmer gets the (fake) risk; only F001 sprayed
        assert {a.farmer_id: a.payload.get("scan_id") for a in created}["F001"] == scan["id"]
        assert [a for a in created if a.farmer_id != "F001" and "scan_id" in a.payload] == []
    alert = api_client.get("/v1/alerts", headers=auth).json()["items"][0]
    assert alert["kind"] == "rain_washoff" and alert["scan_id"] == scan["id"]

"""WEATHER_ENABLED=false: no weather risk alerts and no lookups; the waiting-period alert (no weather needed) still runs."""
from app.alerts.evaluator import run_once
from tests.alerts.test_evaluator import HEAVY, at, seed
from tests.integrations.fakes import FakePush, FakeRules, farmer_row, make_container, risk, spray_log_row


def test_alerts_off_skip_weather_risks_but_keep_waiting_period_alerts(db, tmp_path):
    seed(db, farmer_row("F901"), spray_log_row("F901", at("2026-08-20T10:00"), product_id=HEAVY.product_id))
    rules = FakeRules([risk_like("scab_infection_risk")])
    container = make_container(tmp_path, now=at("2026-08-25T08:00"), push=FakePush(), rules=rules)
    container.settings.weather_enabled = False
    created = run_once(db, container)
    assert [a.kind for a in created] == ["waiting_period"]
    assert container.weather.calls == []


def test_alerts_on_create_weather_alerts(db, tmp_path):
    seed(db, farmer_row("F901"))
    container = make_container(tmp_path, rules=FakeRules([risk_like("scab_infection_risk")]))
    assert [a.kind for a in run_once(db, container)] == ["scab_infection_risk"]


def risk_like(rid):
    return risk(rid, "red", episode="2026-05-10")

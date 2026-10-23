"""The RulesEngine contract: protocol shape, purity, determinism, robustness to odd inputs, no clock and no I/O in the module."""
from __future__ import annotations

import inspect
import re
from datetime import UTC, timedelta
from pathlib import Path

import pytest

from app.domain.types import (
    FarmerProfile,
    RiskItem,
    RuleInput,
    RuleOutput,
    WarningItem,
    WeatherHour,
    WeatherSnapshot,
)
from app.interfaces import RulesEngine

from .helpers import SCAB, at, dry_weather, farmer, make_engine, rule_input, snapshot, spray

RULES_DIR = Path(__file__).resolve().parents[2] / "app" / "rules"
NOW = "2026-04-25 10:00"


def test_protocol_methods_and_parameter_names_match_the_interface(engine):
    assert isinstance(engine, RulesEngine)
    for name in ("recommend", "evaluate_risks", "supported_crops", "check_spray"):
        expected = [p for p in inspect.signature(getattr(RulesEngine, name)).parameters]
        actual = [p for p in inspect.signature(getattr(engine, name)).parameters]
        assert actual == [p for p in expected if p != "self"], name


def test_return_types(engine):
    inp = rule_input(now=NOW, weather=dry_weather(NOW))
    assert isinstance(engine.recommend(inp), RuleOutput)
    risks = engine.evaluate_risks(inp.farmer, inp.weather, inp.now, [])
    assert risks and all(isinstance(r, RiskItem) for r in risks)
    warnings = engine.check_spray(inp.farmer, spray("2026-04-25 09:00", "P012"), [spray("2026-04-10 10:00", "P012")], inp.now)
    assert warnings and all(isinstance(w, WarningItem) for w in warnings)
    crops = engine.supported_crops()
    assert crops == sorted(crops) and all(isinstance(c, str) for c in crops)


def test_recommend_is_deterministic_and_does_not_mutate_its_input(engine):
    history = [spray("2026-04-10 10:00", "P009"), spray("2026-03-20 10:00", "P005")]            # deliberately out of order
    inp = rule_input(now=NOW, history=history, weather=dry_weather(NOW))
    before = inp.model_dump()
    first = engine.recommend(inp)
    second = make_engine().recommend(inp)
    assert first.model_dump() == second.model_dump()
    assert inp.model_dump() == before
    assert [r.product_id for r in inp.history] == ["P009", "P005"]


def test_evaluate_risks_and_check_spray_do_not_mutate_their_input(engine):
    person = farmer()
    weather = dry_weather(NOW)
    history = [spray("2026-04-10 10:00", "P009")]
    before = (person.model_dump(), weather.model_dump(), [h.model_dump() for h in history])
    engine.evaluate_risks(person, weather, at(NOW), history)
    engine.check_spray(person, spray("2026-04-25 09:00", "P012"), history, at(NOW))
    assert (person.model_dump(), weather.model_dump(), [h.model_dump() for h in history]) == before


def test_result_does_not_depend_on_the_real_clock_or_timezone_spelling(engine):
    ist = engine.recommend(rule_input(now=NOW))
    utc_inp = rule_input(now=NOW).model_copy(update={"now": at(NOW).astimezone(UTC)})
    assert engine.recommend(utc_inp).model_dump() == ist.model_dump()


def test_naive_datetimes_are_taken_as_ist(engine):
    aware = engine.recommend(rule_input(now=NOW, history=[spray("2026-04-10 10:00", "P012")]))
    naive_inp = rule_input(now=NOW, history=[spray("2026-04-10 10:00", "P012")])
    naive_inp = naive_inp.model_copy(update={"now": naive_inp.now.replace(tzinfo=None)})
    assert engine.recommend(naive_inp).model_dump() == aware.model_dump()


def test_naive_weather_hours_are_taken_as_ist(engine):
    when = at(NOW)
    hours = [WeatherHour(time=(when - timedelta(hours=h)).replace(tzinfo=None), temp_c=10.0, rh_pct=95.0, rain_mm=0.5, leaf_wet=True)
             for h in range(24 * 14 - 1, -1, -1)]
    risks = {r.id: r for r in engine.evaluate_risks(farmer(), snapshot(when, hours), when, [])}
    assert risks["scab_infection_risk"].level.value == "red"


@pytest.mark.parametrize(
    "weather",
    [None, WeatherSnapshot(station_id=None, as_of=at(NOW)), snapshot(at(NOW), [], [], temp_c=None), dry_weather(NOW)],
    ids=["none", "empty", "no-temperature", "dry"],
)
def test_odd_weather_never_raises(engine, weather):
    out = engine.recommend(rule_input(now=NOW, weather=weather))
    assert out.status in ("advice", "expert_review")
    if weather is not None:
        assert engine.evaluate_risks(farmer(), weather, at(NOW), []) is not None


def test_minimal_farmer_profile(engine):
    bare = FarmerProfile(id="F0", name="N", phone="+910000000000")
    out = engine.recommend(RuleInput(farmer=bare, crop_id="Apple", disease_id=SCAB, disease_confidence=0.9, now=at(NOW)))
    assert out.status == "needs_more_info"
    assert engine.evaluate_risks(bare, dry_weather(NOW), at(NOW), []) == []        # a farmer with no crops gets no crop risks


def test_hostile_free_text_in_history_cannot_break_anything(engine):
    history = [spray("2026-04-10 10:00", None, active_ingredient="'; DROP TABLE x; -- {0} {name}", trade_name="%s %(x)s",
                     frac_irac_code="???"),
               spray("2026-04-11 10:00", "NOT-A-PRODUCT"), spray("2026-04-12 10:00", None)]
    out = engine.recommend(rule_input(now=NOW, history=history))
    assert out.status == "advice"


def test_supported_crops_are_those_with_approved_rows(engine, ref):
    assert engine.supported_crops() == sorted({p.crop for p in ref.products if p.usable})


def test_no_clock_network_or_randomness_in_the_rules_package():
    forbidden = re.compile(r"datetime\.now|datetime\.utcnow|date\.today|time\.time\(|import (pandas|torch|requests|httpx|socket|urllib)|"
                           r"from (pandas|torch|requests|httpx|urllib) |random\.|import random")
    offenders = []
    for path in RULES_DIR.glob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if forbidden.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == []


def test_only_the_data_loader_touches_the_filesystem():
    touching = [p.name for p in RULES_DIR.glob("*.py")
                if re.search(r"\.open\(|read_text|read_bytes|open\(|os\.environ", p.read_text(encoding="utf-8"))]
    assert sorted(touching) == ["data.py", "policy.py"]            # reference files; the RULES_AUTO_ADVICE_DISEASES variable


def test_frozen_contract_files_are_untouched_by_this_module():
    """The rules package only imports the public contract; it must not reach into other agents' packages."""
    allowed = ("app.domain", "app.interfaces", "app.config", "app.clock", "app.rules")
    for path in RULES_DIR.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*(?:from|import) (app[\w.]*)", line)
            if match:
                assert match.group(1).startswith(allowed), f"{path.name}: {line.strip()}"

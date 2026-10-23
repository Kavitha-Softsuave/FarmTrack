"""DEMO_DISEASE_HINTS: steering the stub disease classifier for offline demos (and only outside production)."""
import logging

import pytest

from app.config import Settings
from app.integrations.reference import load_disease_options
from app.vision import factory
from app.vision.disease import STUB_HINT_CONFIDENCE, StubDiseaseClassifier
from app.vision.hints import parse_demo_disease_hints

SCAB = "Apple___Apple_scab"
BLIGHT = "Tomato___Late_blight"


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)       # never the repo-root .env


# ------------------------------------------------------------------------------------------------ the format
def test_the_documented_format():
    parsed = parse_demo_disease_hints(f"Apple={SCAB}:0.9;Tomato={BLIGHT}")
    assert parsed == {"Apple": (SCAB, 0.9), "Tomato": (BLIGHT, STUB_HINT_CONFIDENCE)}


def test_empty_and_missing_values_give_no_hints():
    assert parse_demo_disease_hints(None) == {} and parse_demo_disease_hints("") == {} and parse_demo_disease_hints(" ; ;; ") == {}


def test_spaces_case_of_the_crop_and_aliases_are_normalised():
    assert parse_demo_disease_hints(f"  apple = {SCAB} : 0.5 ;; corn=Corn_(maize)___Common_rust_") == {
        "Apple": (SCAB, 0.5), "Maize": ("Corn_(maize)___Common_rust_", STUB_HINT_CONFIDENCE)}


def test_every_disease_id_of_the_catalogue_is_accepted():
    ids = [disease_id for disease_id, _ in load_disease_options(Settings(_env_file=None).data_dir)]
    assert len(ids) == 50 and all(parse_demo_disease_hints(f"Apple={disease_id}:0.7") == {"Apple": (disease_id, 0.7)} for disease_id in ids)


@pytest.mark.parametrize("entry", ["Apple", "Apple=", "=Apple___Apple_scab", f"Apple={SCAB}:high", f"Apple={SCAB}:1.5", f"Apple={SCAB}:-0.1",
                                   f"Apple={SCAB}:nan", f"Apple={SCAB}:", "../x=Apple___Apple_scab", "Apple=bad id!:0.9", "Apple=a:b:c",
                                   f"1Apple={SCAB}"])
def test_malformed_entries_are_ignored_with_a_warning(entry, caplog):
    with caplog.at_level(logging.WARNING, logger="app.vision"):
        assert parse_demo_disease_hints(entry) == {}
    assert "DEMO_DISEASE_HINTS" in caplog.text and "ignoring entry" in caplog.text


def test_the_good_entries_survive_a_bad_neighbour(caplog):
    with caplog.at_level(logging.WARNING, logger="app.vision"):
        parsed = parse_demo_disease_hints(f"Apple={SCAB}:0.9;garbage;Tomato={BLIGHT}:2")
    assert parsed == {"Apple": (SCAB, 0.9)} and caplog.text.count("ignoring entry") == 2


def test_a_disease_that_is_not_in_the_catalogue_is_ignored_when_a_catalogue_is_given(caplog):
    with caplog.at_level(logging.WARNING, logger="app.vision"):
        assert parse_demo_disease_hints(f"Apple=Apple___Typo;Tomato={BLIGHT}", {SCAB, BLIGHT}) == {"Tomato": (BLIGHT, STUB_HINT_CONFIDENCE)}
    assert "not in the disease catalogue" in caplog.text


def test_a_crop_listed_twice_keeps_the_last_entry(caplog):
    with caplog.at_level(logging.WARNING, logger="app.vision"):
        assert parse_demo_disease_hints(f"Apple={SCAB}:0.9;apple=Apple___Black_rot:0.6") == {"Apple": ("Apple___Black_rot", 0.6)}
    assert "listed twice" in caplog.text


# ------------------------------------------------------------------------------------------------ the factory
def test_the_setting_steers_the_stub_classifier_outside_production():
    classifier = factory.build_disease_classifier(settings(demo_disease_hints=f"Apple={SCAB}:0.9;Tomato={BLIGHT}"))
    assert isinstance(classifier, StubDiseaseClassifier)
    apple = classifier.classify([b"x"], "Apple")
    assert (apple.disease_id, apple.confidence, apple.model_covers_crop) == (SCAB, 0.9, True)
    assert classifier.classify([b"x"], "tomato").disease_id == BLIGHT
    assert classifier.classify([b"x"], "Potato").disease_id is None                           # crops without a hint are untouched


def test_the_hints_are_checked_against_the_disease_catalogue():
    classifier = factory.build_disease_classifier(settings(demo_disease_hints=f"Apple=Apple___Typo;Tomato={BLIGHT}"))
    assert classifier.classify([b"x"], "Apple").disease_id is None and classifier.classify([b"x"], "Tomato").disease_id == BLIGHT


@pytest.mark.parametrize("env", ["dev", "test"])
def test_without_the_setting_the_stub_says_nothing(env):
    assert factory.build_disease_classifier(settings(env=env)).classify([b"x"], "Apple").disease_id is None


def test_production_ignores_the_hints_in_the_factory(caplog):
    with caplog.at_level(logging.WARNING, logger="app.vision"):
        classifier = factory.build_disease_classifier(settings(env="prod", demo_disease_hints=f"Apple={SCAB}"))
    assert classifier.classify([b"x"], "Apple").disease_id is None
    assert "ENV=prod: ignored" in caplog.text
    assert factory.demo_hints(settings(env="prod", demo_disease_hints=f"Apple={SCAB}")) == {}


def test_explicit_stub_hints_win_over_the_setting():
    classifier = factory.build_disease_classifier(settings(demo_disease_hints=f"Apple={SCAB}"), stub_hints={"Apple": "Apple___Black_rot"})
    assert classifier.classify([b"x"], "Apple").disease_id == "Apple___Black_rot"


def test_hints_only_steer_the_stub_not_the_models(monkeypatch):
    class Models:
        pass

    monkeypatch.setattr(factory, "missing_packages", lambda packages: [])
    monkeypatch.setattr(factory, "build_model_disease_classifier", lambda s: Models())
    classifier = factory.build_disease_classifier(settings(disease_provider="model", demo_disease_hints=f"Apple={SCAB}"))
    assert isinstance(classifier, factory.SafeDiseaseClassifier) and isinstance(classifier._primary, Models)


def test_an_unreadable_catalogue_still_allows_well_formed_hints(tmp_path):
    classifier = factory.build_disease_classifier(settings(data_dir=tmp_path, demo_disease_hints=f"Apple={SCAB}:0.7"))
    assert classifier.classify([b"x"], "Apple").confidence == 0.7


def test_the_setting_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("DEMO_DISEASE_HINTS", f"Apple={SCAB}:0.85")
    assert Settings(_env_file=None).demo_disease_hints == f"Apple={SCAB}:0.85"

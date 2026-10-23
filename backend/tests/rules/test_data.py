from __future__ import annotations

import shutil

import pytest

from app.interfaces import RulesEngine
from app.rules import data as rules_data
from app.rules.data import REFERENCE_FILES, contains_phrase, load_reference, norm_text

from .helpers import DATA_DIR, make_engine, make_settings


def test_reference_data_is_loaded_and_cached(ref):
    assert load_reference(DATA_DIR) is ref
    assert load_reference(str(DATA_DIR)) is ref            # same directory spelled differently
    assert len(ref.products) == 97
    assert len(ref.diseases) == 50
    assert set(ref.bands) == {"B1", "B2", "B3", "B4"}
    assert len(ref.offlabel) == 3 and len(ref.banned) == 7
    assert ref.config["confidence_policy"]["min_confidence_for_auto_advice"] == 0.65


def test_crops_with_usable_rows(ref):
    assert sorted(ref.crops.values()) == ["Apple", "Grape", "Maize", "Potato", "Tomato"]
    assert ref.canonical_crop("apple") == "Apple"
    assert ref.canonical_crop(" TOMATO ") == "Tomato"
    assert ref.canonical_crop("Banana") is None
    assert ref.canonical_crop(None) is None


def test_products_are_parsed(ref):
    p = ref.products_by_id["P012"]
    assert p.active_ingredient == "Myclobutanil" and p.components == ("3",) and p.waiting_period_days == 21
    assert p.targets == {"Apple___Apple_scab"} and p.stage == "petal_fall"
    mix = ref.products_by_id["P014"]
    assert mix.components == ("M03", "11") and mix.waiting_period_days is None
    assert ref.products_by_id["P019"].usable is False        # blank target cell: never recommended
    assert ref.products_by_id["P002"].hp_brands[0] == "Himdin"
    assert all(len(p.components) >= 0 for p in ref.products)


def test_every_apple_product_has_a_known_stage(ref):
    stages = {p.stage for p in ref.products if p.crop == "Apple"}
    from app.rules.stage import STAGE_ORDER

    assert stages - {"any"} <= set(STAGE_ORDER)


def test_calendar_bands_and_harvest_rows(ref):
    b3 = ref.bands["B3"]
    assert dict(b3.stages)["petal_fall"] == 126
    assert b3.harvest["Royal_Delicious"]["harvest"] == 252
    assert b3.elev_min == 2000


def test_missing_reference_file_is_an_error(tmp_path):
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir()
    for name in REFERENCE_FILES[:-1]:
        shutil.copy(DATA_DIR / "reference" / name, ref_dir / name)
    with pytest.raises(FileNotFoundError, match="banned_restricted.csv"):
        load_reference(tmp_path)


def test_clear_cache_forces_a_reload(ref):
    rules_data.clear_cache()
    try:
        assert load_reference(DATA_DIR) is not ref
    finally:
        rules_data.clear_cache()
        load_reference(DATA_DIR)


def test_text_normalisation_helpers():
    assert norm_text("Thiophanate-methyl 70 WP") == "thiophanate methyl 70 wp"
    assert norm_text("30% FS") == "30 fs"
    assert contains_phrase(norm_text("Mancozeb 75 WP"), "mancozeb")
    assert not contains_phrase("mancozebx", "mancozeb")


def test_build_rules_engine_returns_a_rules_engine():
    engine = make_engine()
    assert isinstance(engine, RulesEngine)
    assert engine.supported_crops() == ["Apple", "Grape", "Maize", "Potato", "Tomato"]


def test_settings_data_dir_is_used(tmp_path):
    settings = make_settings()
    assert settings.data_dir == DATA_DIR
    with pytest.raises(FileNotFoundError):
        from app.rules.engine import build_rules_engine

        build_rules_engine(settings.model_copy(update={"data_dir": tmp_path / "nowhere"}))

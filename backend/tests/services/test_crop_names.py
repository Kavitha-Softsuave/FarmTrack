"""Every crop the app can name has a Hindi name (a Devanagari draft) or is listed here as missing; the card never shows Latin Hindi."""
import json
import re

import pytest

from app.advice.crop_names import crop_hi, crop_key
from app.advice.refdata import load_refdata
from app.domain.types import CropCandidate, CropResult
from app.rules.engine import build_rules_engine
from app.services.catalogue import load_catalogue
from app.vision import labels
from tests.fakes import plain_settings
from tests.imaging import photo_files

DEVANAGARI = re.compile("[ऀ-ॿ]")
MISSING_HINDI_NAME: set[str] = set()          # crops that may keep their English name in Hindi mode (none today)


def _all_crops() -> set[str]:
    settings = plain_settings()
    prompts = json.loads((settings.voice_dir / "prompts.json").read_text(encoding="utf-8"))["prompts"]
    voice = {labels.canonical_crop(p["id"].removeprefix("crop_is_")) for p in prompts
             if p["id"].startswith("crop_is_") and p["id"] != "crop_is_unknown"}
    detectors = {labels.detector_label_to_crop(x) for x in (*labels.DETECTOR_16_LABELS, *labels.DETECTOR_36_LABELS)}
    return {*build_rules_engine(settings).supported_crops(), *load_catalogue(str(settings.data_dir)).crops, *labels.DEMO_CROPS,
            *labels.NO_PHOTO_MODEL_CROPS, *labels.PV_CROP_PREFIX, *labels.A_COVERED_CROPS, *voice, *detectors}


def test_every_crop_has_a_devanagari_hindi_name_or_is_listed_as_missing():
    catalogue = load_catalogue(str(plain_settings().data_dir))
    ref = load_refdata(str(plain_settings().data_dir))
    crops = _all_crops()
    assert {"Apple", "Pea", "Wheat", "Cauliflower", "Custard_Apple"} <= crops
    for crop in sorted(crops - MISSING_HINDI_NAME):
        assert DEVANAGARI.search(catalogue.crop_name(crop).hi), f"{crop}: scan card name has no Hindi"
        assert DEVANAGARI.search(ref.crop_name(crop).hi), f"{crop}: advice text name has no Hindi"
    for crop in MISSING_HINDI_NAME:
        assert catalogue.crop_name(crop).hi == catalogue.crop_name(crop).en           # keeps the English name, never empty


def test_both_name_tables_agree_for_every_crop():
    catalogue = load_catalogue(str(plain_settings().data_dir))
    ref = load_refdata(str(plain_settings().data_dir))
    for crop in sorted(_all_crops()):
        assert catalogue.crop_name(crop).hi == ref.crop_name(crop).hi, crop


def test_supported_crops_keep_the_glossary_spelling():
    catalogue = load_catalogue(str(plain_settings().data_dir))
    assert {c: catalogue.crop_name(c).hi for c in ("Apple", "Tomato", "Potato", "Maize", "Grape")} == {
        "Apple": "सेब", "Tomato": "टमाटर", "Potato": "आलू", "Maize": "मक्का", "Grape": "अंगूर"}
    assert catalogue.crop_name("Cherry").hi == "चेरी"          # in the disease catalogue with an empty crop_hi column
    assert catalogue.crop_name("Pea").hi == "मटर"
    assert catalogue.crop_name("Pea").en == "Pea"                # the English side is unchanged


@pytest.mark.parametrize("spelling", ["Custard_Apple", "custard apple", " Custard-Apple "])
def test_crop_key_accepts_any_spelling(spelling):
    assert crop_key(spelling) == "custard_apple" and crop_hi(spelling) == "शरीफा"


def test_unknown_crop_has_no_hindi_name_and_keeps_english():
    assert crop_hi("Dragon_Fruit") is None
    assert load_catalogue(str(plain_settings().data_dir)).crop_name("Dragon_Fruit").hi == "Dragon Fruit"


def test_scan_card_sends_the_hindi_crop_name_for_a_non_demo_crop(api_client, auth, fake_container):
    fake_container.crop_identifier.result = CropResult(
        crop_id="Pea", confidence=0.5, needs_confirmation=True, source="server_model",
        candidates=[CropCandidate(crop_id="Pea", confidence=0.5), CropCandidate(crop_id="Wheat", confidence=0.3)])
    body = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    assert body["crop"]["name"] == {"en": "Pea", "hi": "मटर"}
    assert [c["name"]["hi"] for c in body["crop"]["candidates"]] == ["मटर", "गेहूँ"]
    assert body["next_steps"][0]["prompt_id"] == "crop_confirm_prompt"

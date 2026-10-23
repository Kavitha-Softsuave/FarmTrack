"""ModelCropIdentifier with injected fake detectors (no torch). Probabilities below are chosen so the expected outcome follows from the
documented rules (evidence = max over the two detectors, farmer prior 1.0 vs floor 0.15, ask on a small margin / weak evidence /
crop outside the profile / prior overriding the detectors)."""
from __future__ import annotations

import pytest

from app.domain.types import CropResult
from app.interfaces import CropIdentifier
from app.vision.crop import ModelCropIdentifier, ProfileCropIdentifier
from app.vision.fallback import SafeCropIdentifier
from app.vision.inference import ModelUnavailableError
from app.vision.labels import (
    DETECTOR_16_LABELS,
    DETECTOR_36_LABELS,
    NO_PHOTO_MODEL_CROPS,
    canonical_crop,
    detector_label_to_crop,
)
from tests.vision.support import ExplodingClassifier, FakeClassifier, distribution, photo_bytes


def identifier(p16: dict[str, float], p36: dict[str, float], *more: tuple[dict[str, float], dict[str, float]]) -> ModelCropIdentifier:
    pairs = [(p16, p36), *more]
    return ModelCropIdentifier(
        FakeClassifier(DETECTOR_16_LABELS, *(distribution(DETECTOR_16_LABELS, a) for a, _ in pairs)),
        FakeClassifier(DETECTOR_36_LABELS, *(distribution(DETECTOR_36_LABELS, b) for _, b in pairs)))


def identify(model: ModelCropIdentifier, farmer: list[str], photos: int = 1, **kwargs) -> CropResult:
    return model.identify(photo_bytes(photos), farmer, **kwargs)


APPLE = identifier({"Apple": 0.99}, {"Apple": 0.98})
TOMATO = identifier({"Brinjal": 0.7}, {"Tomato": 0.96})     # the 16-detector does not know tomato and calls it brinjal


def test_implements_the_interface():
    assert isinstance(APPLE, CropIdentifier)


def test_every_detector_label_maps_to_a_catalogue_style_crop_id():
    crops = {detector_label_to_crop(label) for label in (*DETECTOR_16_LABELS, *DETECTOR_36_LABELS)}
    assert len(crops) == len(set(DETECTOR_16_LABELS) | set(DETECTOR_36_LABELS)) == 46     # no two labels collapse into one id
    assert {"Apple", "Tomato", "Potato", "Maize", "Grape", "Pear", "Walnut", "Apricot", "Peach", "Cherry", "Pomegranate", "Pepper",
            "Rice", "Cucumber", "Strawberry", "Mango", "Citrus", "Custard_Apple", "Bitter_Gourd"} <= crops
    assert all(c == canonical_crop(c) and " " not in c and "(" not in c for c in crops)
    assert not crops & NO_PHOTO_MODEL_CROPS       # the detectors cannot name pea, wheat, kiwi, plum ...


def test_confident_detectors_and_matching_profile_need_no_confirmation():
    r = identify(APPLE, ["Apple", "Tomato"])
    assert (r.crop_id, r.source, r.needs_confirmation, r.unknown) == ("Apple", "server_model", False, False)
    assert r.confidence > 0.95 and r.candidates[0].crop_id == "Apple"


def test_confident_crop_outside_the_profile_is_returned_but_confirmed():
    r = identify(APPLE, ["Tomato"])
    assert r.crop_id == "Apple" and r.needs_confirmation and not r.unknown      # a new crop can still win, the farmer is asked
    assert sum(c.confidence for c in r.candidates) <= 1.0


def test_empty_profile_is_no_information_and_does_not_force_a_question():
    assert not identify(APPLE, []).needs_confirmation
    assert identify(APPLE, []).crop_id == "Apple"


def test_detectors_naming_different_crops_shrink_the_margin_and_ask():
    r = identify(TOMATO, [])
    assert r.crop_id == "Tomato" and r.needs_confirmation
    assert [c.crop_id for c in r.candidates[:2]] == ["Tomato", "Brinjal"]


def test_profile_resolves_disagreeing_detectors():
    r = identify(TOMATO, ["Tomato"])
    assert r.crop_id == "Tomato" and not r.needs_confirmation and r.confidence > 0.8


def test_prior_overriding_the_detectors_favourite_asks():
    model = identifier({"Apple": 0.4}, {"Tomato": 0.6})
    assert identify(model, []).crop_id == "Tomato"
    r = identify(model, ["Apple"])
    assert r.crop_id == "Apple" and r.needs_confirmation        # the prior flipped the answer: ask


def test_weak_evidence_asks_even_when_it_is_the_farmers_crop():
    model = identifier({"Apple": 0.5}, {"Apple": 0.55})
    r = identify(model, ["Apple"])
    assert r.crop_id == "Apple" and r.needs_confirmation


def test_two_crops_of_the_profile_that_tie_ask():
    model = identifier({"Apple": 0.5, "Cherry": 0.45}, {"Apple": 0.5, "Cherry": 0.45})
    r = identify(model, ["Apple", "Cherry"])
    assert r.needs_confirmation and {c.crop_id for c in r.candidates[:2]} == {"Apple", "Cherry"}


def test_farmer_crop_no_detector_knows_can_win_when_detectors_are_unsure():
    model = identifier({"Guava": 0.35}, {"Soybean": 0.45})       # a pea leaf: both detectors guess
    r = identify(model, ["Pea"])
    assert r.crop_id == "Pea" and r.needs_confirmation and not r.unknown
    alone = identify(model, [])      # without the profile the same output is too flat to name a crop
    assert alone.unknown and alone.crop_id is None and alone.candidates[0].crop_id == "Soybean"


def test_farmer_crop_no_detector_knows_does_not_beat_confident_detectors():
    r = identify(APPLE, ["Pea"])
    assert r.crop_id == "Apple" and r.needs_confirmation
    assert [c.crop_id for c in r.candidates[:2]] == ["Apple", "Pea"]


def test_clueless_detectors_give_unknown():
    r = ModelCropIdentifier(FakeClassifier(DETECTOR_16_LABELS, [1 / 16] * 16),
                            FakeClassifier(DETECTOR_36_LABELS, [1 / 36] * 36)).identify(photo_bytes(), [])
    assert r.crop_id is None and r.unknown and r.needs_confirmation and r.candidates


def test_clueless_detectors_do_not_become_the_profile_crop():
    flat = ModelCropIdentifier(FakeClassifier(DETECTOR_16_LABELS, [1 / 16] * 16), FakeClassifier(DETECTOR_36_LABELS, [1 / 36] * 36))
    assert flat.identify(photo_bytes(), ["Apple"]).unknown


def test_detectors_returning_only_zeros_give_unknown():
    zeros = ModelCropIdentifier(FakeClassifier(DETECTOR_16_LABELS, [0.0] * 16), FakeClassifier(DETECTOR_36_LABELS, [0.0] * 36))
    r = zeros.identify(photo_bytes(), [])
    assert r.crop_id is None and r.unknown and r.candidates == []


def test_photos_are_averaged_per_detector():
    model = identifier({"Apple": 0.9}, {"Apple": 0.9}, ({"Mango": 0.9}, {"Mango": 0.9}))
    r = identify(model, ["Apple", "Mango"], photos=2)
    assert r.needs_confirmation and {c.crop_id for c in r.candidates[:2]} == {"Apple", "Mango"}     # 0.45 each: a tie
    three = identify(model, ["Apple", "Mango"], photos=3)       # photos cycle: apple, mango, apple
    assert three.crop_id == "Apple"


def test_client_guess_is_ignored_by_the_server_model():
    assert identify(APPLE, ["Apple"], client_guess="Tomato", client_confidence=0.99) == identify(APPLE, ["Apple"])


def test_candidates_are_at_most_three_and_never_sum_above_one():
    r = identify(TOMATO, ["Tomato", "Potato"])
    assert len(r.candidates) <= 3 and sum(c.confidence for c in r.candidates) <= 1.0
    assert [c.confidence for c in r.candidates] == sorted((c.confidence for c in r.candidates), reverse=True)


def test_names_in_the_profile_are_normalised():
    assert not identify(APPLE, ["apple"]).needs_confirmation


def test_no_images_is_an_error():
    with pytest.raises(ValueError, match="no images"):
        APPLE.identify([], ["Apple"])


def test_undecodable_image_is_an_error():
    with pytest.raises(ValueError, match="unreadable"):
        APPLE.identify([b"garbage"], ["Apple"])


def test_detector_with_the_wrong_number_of_outputs_is_an_error():
    broken = ModelCropIdentifier(FakeClassifier(DETECTOR_16_LABELS, [0.5, 0.5]), FakeClassifier(DETECTOR_36_LABELS, [1 / 36] * 36))
    with pytest.raises(ValueError, match="probabilities"):
        broken.identify(photo_bytes(), [])


# ----------------------------------------------------------------------------------------------------- fallback
def test_unavailable_model_falls_back_to_the_profile_identifier_and_logs_once(caplog):
    dead = ModelCropIdentifier(ExplodingClassifier(ModelUnavailableError("no network, no cached weights")),
                               ExplodingClassifier(ModelUnavailableError("no network, no cached weights")))
    safe = SafeCropIdentifier(dead, ProfileCropIdentifier())
    with caplog.at_level("WARNING", logger="app.vision"):
        first = safe.identify(photo_bytes(), ["Apple"], "Apple", 0.9)
        second = safe.identify(photo_bytes(), ["Apple"])
    assert (first.crop_id, first.source) == ("Apple", "on_device")
    assert (second.crop_id, second.source, second.needs_confirmation) == ("Apple", "farmer_profile", True)
    warnings = [r for r in caplog.records if r.name == "app.vision"]
    assert len(warnings) == 1 and "no network" in warnings[0].getMessage()


def test_any_runtime_error_also_falls_back():
    safe = SafeCropIdentifier(ModelCropIdentifier(FakeClassifier(DETECTOR_16_LABELS, [1.0]), FakeClassifier(DETECTOR_36_LABELS, [1.0])),
                              ProfileCropIdentifier())
    assert safe.identify(photo_bytes(), ["Tomato"]).crop_id == "Tomato"        # wrong output length -> ValueError -> profile


def test_working_model_is_not_replaced_by_the_fallback():
    assert SafeCropIdentifier(APPLE, ProfileCropIdentifier()).identify(photo_bytes(), ["Apple", "Tomato"]).source == "server_model"


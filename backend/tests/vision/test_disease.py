"""StubDiseaseClassifier, ModelDiseaseClassifier (fake models, no torch) and the label tables against the data catalogue."""
from __future__ import annotations

import csv

import pytest

from app.config import REPO_ROOT
from app.interfaces import DiseaseClassifier
from app.vision.disease import APPLE_A_WEIGHT, ModelDiseaseClassifier, StubDiseaseClassifier, covers_crop
from app.vision.fallback import SafeDiseaseClassifier
from app.vision.inference import ModelUnavailableError
from app.vision.labels import (
    A_COVERED_CROPS,
    B_MAP,
    NO_PHOTO_MODEL_CROPS,
    PV_CROP_PREFIX,
    PV_LABELS,
    pv_labels_for,
)
from tests.vision.support import ExplodingClassifier, FakeClassifier, distribution, photo_bytes

B_RAW = list(B_MAP)       # the 8 label names of the apple model, in an arbitrary but fixed order


def catalogue() -> list[dict[str, str]]:
    with open(REPO_ROOT / "data" / "reference" / "disease_catalogue.csv", newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def model(a: dict[str, float] | None = None, b: dict[str, float] | None = None, weight: float = APPLE_A_WEIGHT) -> ModelDiseaseClassifier:
    fa = FakeClassifier(PV_LABELS, distribution(PV_LABELS, a or {"Apple___healthy": 0.5}))
    fb = FakeClassifier(B_RAW, distribution(B_RAW, b or {"Healthy": 0.5}))
    return ModelDiseaseClassifier(fa, fb, weight)


def candidates(result) -> dict[str, float]:
    return {c.disease_id: c.confidence for c in result.candidates}


# ------------------------------------------------------------------------------------------------------ label tables
def test_the_38_plantvillage_labels_are_catalogue_ids_for_the_on_device_model():
    rows = catalogue()
    ids = {r["disease_id"] for r in rows}
    on_device = {r["disease_id"] for r in rows if "ondevice_pv" in r["detectable_by"]}
    assert len(PV_LABELS) == len(set(PV_LABELS)) == 38
    assert set(PV_LABELS) <= ids
    assert set(PV_LABELS) == on_device


def test_the_8_apple_model_labels_map_to_distinct_catalogue_ids():
    rows = catalogue()
    ids = {r["disease_id"] for r in rows}
    server_apple = {r["disease_id"] for r in rows if "server_apple" in r["detectable_by"]}
    assert len(B_MAP) == 8 and len(set(B_MAP.values())) == 8
    assert set(B_MAP.values()) <= ids
    assert set(B_MAP.values()) == server_apple
    assert all(i.startswith("Apple___") for i in B_MAP.values())


def test_every_label_belongs_to_exactly_one_crop_mask():
    seen = [lab for crop in PV_CROP_PREFIX for lab in pv_labels_for(crop)]
    assert sorted(seen) == sorted(PV_LABELS)


def test_covered_crops_are_those_with_at_least_two_plantvillage_classes():
    assert A_COVERED_CROPS == {"Apple", "Cherry", "Maize", "Grape", "Peach", "Pepper", "Potato", "Strawberry", "Tomato"}
    for single in ("Blueberry", "Raspberry", "Soybean", "Citrus", "Squash"):
        assert len(pv_labels_for(single)) == 1 and not covers_crop(single)


def test_no_photo_model_crops_are_not_covered():
    assert all(not covers_crop(c) for c in NO_PHOTO_MODEL_CROPS | {"Rice", "Mango", "Pear", "Walnut"})
    assert all(pv_labels_for(c) == [] for c in NO_PHOTO_MODEL_CROPS)


def test_crop_names_are_normalised():
    assert covers_crop("apple") and covers_crop("Corn") and covers_crop("capsicum") and covers_crop("tomato")


# ------------------------------------------------------------------------------------------------------ stub
def test_stub_implements_the_interface_and_covers_the_demo_crops():
    stub = StubDiseaseClassifier()
    assert isinstance(stub, DiseaseClassifier)
    for crop in ("Apple", "Tomato", "Potato", "Maize", "Grape"):
        r = stub.classify([], crop)
        assert (r.crop_id, r.disease_id, r.confidence, r.candidates, r.model, r.model_covers_crop) == (crop, None, 0.0, [], "stub", True)


@pytest.mark.parametrize("crop", ["Pea", "Cauliflower", "Wheat", "Kiwi", "Rice"])
def test_stub_does_not_cover_other_crops(crop):
    r = StubDiseaseClassifier().classify([], crop)
    assert not r.model_covers_crop and r.disease_id is None


def test_stub_is_deterministic_and_ignores_the_images():
    stub = StubDiseaseClassifier()
    assert stub.classify(photo_bytes(2), "apple") == stub.classify([], "Apple")


def test_stub_hint_forces_a_result():
    stub = StubDiseaseClassifier({"apple": "Apple___Apple_scab", "Potato": ("Potato___Late_blight", 0.9), "Pea": "Pea___rust"})
    scab = stub.classify([], "Apple")
    assert (scab.disease_id, scab.confidence, scab.model_covers_crop) == ("Apple___Apple_scab", 0.8, True)
    assert candidates(scab) == {"Apple___Apple_scab": 0.8}
    assert stub.classify([], "Potato").confidence == 0.9
    assert stub.classify([], "Tomato").disease_id is None
    assert stub.classify([], "Pea").model_covers_crop      # a hint makes the crop covered


# ------------------------------------------------------------------------------------------------------ crop mask, renormalisation
def test_model_a_is_masked_to_the_crop_and_renormalised():
    a = {"Tomato___Early_blight": 0.30, "Tomato___Late_blight": 0.10, "Potato___Early_blight": 0.40, "Apple___Apple_scab": 0.10}
    vector = distribution(PV_LABELS, a)
    in_crop = sum(p for label, p in zip(PV_LABELS, vector, strict=True) if label.startswith("Tomato___"))
    r = model(a).classify(photo_bytes(), "Tomato")
    assert r.disease_id == "Tomato___Early_blight"
    assert all(d.startswith("Tomato___") for d in candidates(r))
    assert r.confidence == pytest.approx(0.30 / in_crop, abs=1e-3)       # the Potato and Apple mass is gone, the rest renormalised
    assert r.model_covers_crop and r.crop_id == "Tomato"
    assert len(r.candidates) == 5 and sum(candidates(r).values()) <= 1.0


def test_masked_probabilities_add_up_to_one_for_a_small_crop():
    r = model({"Potato___Late_blight": 0.6, "Tomato___Late_blight": 0.3}).classify(photo_bytes(), "Potato")
    assert set(candidates(r)) == {"Potato___Early_blight", "Potato___Late_blight", "Potato___healthy"}
    assert sum(candidates(r).values()) == pytest.approx(1.0, abs=1e-3)
    assert r.disease_id == "Potato___Late_blight"


def test_a_photo_the_model_puts_entirely_outside_the_crop_gives_a_uniform_answer():
    a = {"Apple___Apple_scab": 1.0}
    r = ModelDiseaseClassifier(FakeClassifier(PV_LABELS, distribution(PV_LABELS, a)), ExplodingClassifier()).classify(photo_bytes(), "Potato")
    assert all(c.confidence == pytest.approx(1 / 3, abs=1e-3) for c in r.candidates)


def test_multiple_photos_are_masked_per_photo_then_averaged():
    first = distribution(PV_LABELS, {"Potato___Late_blight": 0.85, "Potato___Early_blight": 0.05, "Potato___healthy": 0.05,
                                     "Tomato___Early_blight": 0.05})          # 95 % inside the crop
    second = distribution(PV_LABELS, {"Potato___Early_blight": 0.6, "Tomato___Early_blight": 0.4})    # 60 % inside the crop
    m = ModelDiseaseClassifier(FakeClassifier(PV_LABELS, first, second), ExplodingClassifier())
    assert candidates(m.classify(photo_bytes(1), "Potato"))["Potato___Late_blight"] == pytest.approx(0.85 / 0.95, abs=1e-3)
    both = candidates(m.classify(photo_bytes(2), "Potato"))
    # each photo is renormalised inside the crop first (so the second photo counts fully), then the two vectors are averaged
    assert both["Potato___Late_blight"] == pytest.approx((0.85 / 0.95 + 0.0) / 2, abs=1e-3)
    assert both["Potato___Early_blight"] == pytest.approx((0.05 / 0.95 + 1.0) / 2, abs=1e-3)
    assert both["Potato___healthy"] == pytest.approx((0.05 / 0.95 + 0.0) / 2, abs=1e-3)
    assert sum(both.values()) == pytest.approx(1.0, abs=1e-3)


def test_single_photo_equals_the_same_photo_twice():
    m = model({"Tomato___Late_blight": 0.7})
    assert candidates(m.classify(photo_bytes(1), "Tomato")) == candidates(m.classify(photo_bytes(2), "Tomato"))


# ------------------------------------------------------------------------------------------------------ apple: model B + A
def test_apple_returns_b_candidates_mapped_to_catalogue_ids():
    r = model(a={"Apple___Apple_scab": 1.0}, b={"Marssonina Blotch": 0.7, "Alternaria Leaf Spot": 0.2}, weight=0.0).classify(photo_bytes(), "Apple")
    assert r.disease_id == "Apple___Marssonina_blotch" and r.confidence == pytest.approx(0.7, abs=1e-3)
    assert candidates(r)["Apple___Alternaria_leaf_spot"] == pytest.approx(0.2, abs=1e-3)
    assert set(candidates(r)) <= set(B_MAP.values())
    assert "+" in r.model and r.model_covers_crop


def test_apple_mixture_adds_model_a_evidence_for_the_classes_b_has_and_renormalises():
    a = {"Apple___Apple_scab": 0.9, "Apple___Black_rot": 0.05, "Apple___Cedar_apple_rust": 0.03, "Apple___healthy": 0.02}
    b = {"Marssonina Blotch": 0.6, "Apple Scab": 0.3, "Healthy": 0.05, "Brown Spot": 0.05}
    got = candidates(model(a, b, weight=0.2).classify(photo_bytes(), "Apple"))
    total = 0.8 * 1.0 + 0.2 * (0.9 + 0.02)         # model A's black rot and cedar rust mass is dropped
    assert got["Apple___Marssonina_blotch"] == pytest.approx(0.8 * 0.6 / total, abs=1e-3)
    assert got["Apple___Apple_scab"] == pytest.approx((0.8 * 0.3 + 0.2 * 0.9) / total, abs=1e-3)
    assert got["Apple___healthy"] == pytest.approx((0.8 * 0.05 + 0.2 * 0.02) / total, abs=1e-3)
    assert "Apple___Black_rot" not in got and "Apple___Cedar_apple_rust" not in got      # B never answers them
    assert set(got) <= set(B_MAP.values())


def test_apple_weight_one_follows_model_a_where_b_has_classes_and_zero_is_model_b_alone():
    a = {"Apple___Apple_scab": 0.9, "Apple___healthy": 0.1}
    b = {"Marssonina Blotch": 0.9, "Healthy": 0.1}
    assert model(a, b, weight=1.0).classify(photo_bytes(), "Apple").disease_id == "Apple___Apple_scab"
    assert model(a, b, weight=0.0).classify(photo_bytes(), "Apple").disease_id == "Apple___Marssonina_blotch"


def test_apple_model_a_saying_only_things_b_lacks_leaves_model_b_unchanged():
    a = {"Apple___Cedar_apple_rust": 1.0}
    b = {"Marssonina Blotch": 0.7, "Apple Scab": 0.3}
    got = candidates(model(a, b, weight=1.0).classify(photo_bytes(), "Apple"))
    assert got["Apple___Marssonina_blotch"] == pytest.approx(0.7, abs=1e-3)


def test_apple_photos_are_averaged_for_both_models():
    fa = FakeClassifier(PV_LABELS, distribution(PV_LABELS, {"Apple___Apple_scab": 1.0}), distribution(PV_LABELS, {"Apple___healthy": 1.0}))
    fb = FakeClassifier(B_RAW, distribution(B_RAW, {"Apple Scab": 1.0}), distribution(B_RAW, {"Healthy": 1.0}))
    got = candidates(ModelDiseaseClassifier(fa, fb).classify(photo_bytes(2), "Apple"))
    assert got["Apple___Apple_scab"] == pytest.approx(got["Apple___healthy"], abs=1e-3) == pytest.approx(0.5, abs=1e-3)


def test_non_apple_crops_never_touch_model_b():
    m = ModelDiseaseClassifier(FakeClassifier(PV_LABELS, distribution(PV_LABELS, {"Grape___Black_rot": 0.8})), ExplodingClassifier())
    r = m.classify(photo_bytes(), "Grape")
    assert r.disease_id == "Grape___Black_rot" and "+" not in r.model


def test_all_zero_output_gives_no_disease_but_a_covered_crop():
    zeros = ModelDiseaseClassifier(FakeClassifier(PV_LABELS, [0.0] * 38), FakeClassifier(B_RAW, [0.0] * 8), 0.0)
    r = zeros.classify(photo_bytes(), "Apple")      # model A's mask falls back to a uniform answer, model B (weight 1 - 0) is all zero
    assert r.model_covers_crop and r.crop_id == "Apple"


def test_unexpected_apple_model_labels_are_refused():
    labels = [*B_RAW[:-1], "Powdery Mildew"]
    m = ModelDiseaseClassifier(FakeClassifier(PV_LABELS, distribution(PV_LABELS, {})), FakeClassifier(labels, distribution(labels, {})))
    with pytest.raises(ModelUnavailableError, match="cannot map"):
        m.classify(photo_bytes(), "Apple")


def test_model_a_without_classes_for_the_crop_is_refused():
    m = ModelDiseaseClassifier(FakeClassifier(PV_LABELS[:3], [0.2, 0.3, 0.5]), ExplodingClassifier())
    with pytest.raises(ModelUnavailableError):
        m.classify(photo_bytes(), "Tomato")


def test_wrong_output_length_is_an_error():
    m = ModelDiseaseClassifier(FakeClassifier(PV_LABELS, [0.5, 0.5]), ExplodingClassifier())
    with pytest.raises(ValueError, match="probabilities"):
        m.classify(photo_bytes(), "Tomato")


def test_weight_must_be_a_fraction():
    with pytest.raises(ValueError, match="apple_a_weight"):
        model(weight=1.5)


# ------------------------------------------------------------------------------------------------------ crops without a model
@pytest.mark.parametrize("crop", sorted(NO_PHOTO_MODEL_CROPS | {"Blueberry", "Soybean", "Rice", "Pear"}))
def test_crop_without_a_photo_model_is_not_covered_and_no_model_is_loaded(crop):
    m = ModelDiseaseClassifier(ExplodingClassifier(), ExplodingClassifier())
    r = m.classify(photo_bytes(), crop)
    assert (r.crop_id, r.disease_id, r.confidence, r.candidates, r.model_covers_crop) == (crop, None, 0.0, [], False)
    assert not m.covers(crop)


def test_covered_crops_do_not_need_decodable_images_to_be_reported_as_covered():
    assert ModelDiseaseClassifier(ExplodingClassifier(), ExplodingClassifier()).covers("Tomato")
    with pytest.raises(ValueError, match="unreadable"):
        model().classify([b"garbage"], "Tomato")
    with pytest.raises(ValueError, match="no images"):
        model().classify([], "Tomato")


def test_implements_the_interface():
    assert isinstance(model(), DiseaseClassifier)


# ------------------------------------------------------------------------------------------------------ fallback
def test_unavailable_models_fall_back_to_the_stub_and_log_once(caplog):
    err = ModelUnavailableError("weights not cached and no network")
    safe = SafeDiseaseClassifier(ModelDiseaseClassifier(ExplodingClassifier(err), ExplodingClassifier(err)), StubDiseaseClassifier())
    with caplog.at_level("WARNING", logger="app.vision"):
        first = safe.classify(photo_bytes(), "Apple")
        second = safe.classify(photo_bytes(), "Tomato")
    assert (first.disease_id, first.model, first.model_covers_crop) == (None, "stub", True)
    assert second.model_covers_crop
    assert len([r for r in caplog.records if r.name == "app.vision"]) == 1


def test_fallback_is_not_used_when_the_model_works():
    safe = SafeDiseaseClassifier(model({"Tomato___Late_blight": 0.9}), StubDiseaseClassifier())
    assert safe.classify(photo_bytes(), "Tomato").disease_id == "Tomato___Late_blight"
    assert safe.classify(photo_bytes(), "Pea").model == "none"       # an answer, not a failure: no fallback

"""Decision table of ProfileCropIdentifier: one test per branch (g = on-device guess, c = its confidence, F = the farmer's crops)."""
from __future__ import annotations

import itertools

import pytest

from app.interfaces import CropIdentifier
from app.vision.crop import ProfileCropIdentifier

ident = ProfileCropIdentifier()


def run(farmer: list[str], guess: str | None = None, conf: float | None = None):
    return ident.identify([b"photo"], farmer, guess, conf)


def ids(result) -> list[str]:
    return [c.crop_id for c in result.candidates]


def test_implements_the_interface():
    assert isinstance(ident, CropIdentifier)


# 1. the guess is one of the farmer's crops and strong enough
@pytest.mark.parametrize("farmer", [["Apple"], ["Apple", "Tomato"], ["Tomato", "Apple", "Potato"]])
def test_strong_guess_in_profile_is_accepted_without_asking(farmer):
    r = run(farmer, "Apple", 0.8)
    assert (r.crop_id, r.confidence, r.source) == ("Apple", 0.8, "on_device")
    assert not r.needs_confirmation and not r.unknown
    assert ids(r)[0] == "Apple"


def test_guess_at_exactly_half_is_strong():
    assert not run(["Apple", "Tomato"], "Tomato", 0.5).needs_confirmation


# 2. the farmer grows exactly one crop
def test_single_crop_without_guess_asks_one_tap():
    r = run(["Apple"])
    assert (r.crop_id, r.source, r.needs_confirmation, r.unknown) == ("Apple", "farmer_profile", True, False)
    assert 0 < r.confidence < 1


@pytest.mark.parametrize("conf", [0.1, 0.49, None])
def test_single_crop_with_agreeing_weak_guess_needs_no_confirmation(conf):
    r = run(["Apple"], "Apple", conf)
    assert (r.crop_id, r.source, r.needs_confirmation) == ("Apple", "farmer_profile", False)
    assert r.confidence > run(["Apple"]).confidence      # an agreeing guess raises the confidence


# 3. several crops, the guess is one of them but weak
@pytest.mark.parametrize("conf", [0.2, 0.49, None])
def test_weak_guess_in_a_multi_crop_profile_asks(conf):
    r = run(["Apple", "Tomato"], "Tomato", conf)
    assert (r.crop_id, r.source, r.needs_confirmation, r.unknown) == ("Tomato", "on_device", True, False)
    assert ids(r) == ["Tomato", "Apple"]


# 4. the guess is not one of the farmer's crops
def test_strong_guess_outside_profile_leads_but_asks():
    r = run(["Apple"], "Tomato", 0.9)
    assert (r.crop_id, r.source, r.needs_confirmation, r.unknown) == ("Tomato", "on_device", True, False)
    assert ids(r) == ["Tomato", "Apple"]


def test_strong_guess_with_empty_profile_asks():
    r = run([], "Potato", 0.7)
    assert (r.crop_id, r.confidence, r.needs_confirmation) == ("Potato", 0.7, True)


def test_weak_guess_against_a_single_crop_profile_lets_the_profile_lead():
    r = run(["Apple"], "Tomato", 0.3)
    assert (r.crop_id, r.source, r.needs_confirmation) == ("Apple", "farmer_profile", True)
    assert ids(r) == ["Apple", "Tomato"] and r.candidates[0].confidence > r.candidates[1].confidence


def test_weak_guess_against_a_multi_crop_profile_is_unknown_with_choices():
    r = run(["Apple", "Potato"], "Tomato", 0.3)
    assert r.crop_id is None and r.unknown and r.needs_confirmation
    assert set(ids(r)) == {"Apple", "Potato", "Tomato"} and ids(r)[-1] == "Tomato"


def test_weak_guess_with_empty_profile_is_kept_when_at_least_0_3():
    r = run([], "Tomato", 0.3)
    assert (r.crop_id, r.needs_confirmation, r.unknown) == ("Tomato", True, False)


def test_very_weak_guess_with_empty_profile_is_unknown():
    r = run([], "Tomato", 0.1)
    assert r.crop_id is None and r.unknown and r.needs_confirmation
    assert ids(r) == ["Tomato"]


def test_guess_without_confidence_counts_as_weak():
    r = run([], "Tomato", None)
    assert r.crop_id == "Tomato" and r.needs_confirmation and r.confidence == 0.3


# 5. and 6. no guess
def test_no_guess_several_crops_is_unknown_with_choices():
    r = run(["Apple", "Tomato"])
    assert r.crop_id is None and r.unknown and r.needs_confirmation and r.source == "farmer_profile"
    assert ids(r) == ["Apple", "Tomato"]


def test_no_information_is_unknown():
    r = run([])
    assert r.crop_id is None and r.unknown and r.needs_confirmation and r.source == "stub" and r.candidates == []
    assert r.confidence == 0.0


# robustness
def test_names_are_normalised_and_deduplicated():
    r = run(["apple", "Apple", " APPLE "], "apple", 0.9)
    assert r.crop_id == "Apple" and ids(r) == ["Apple"]
    assert run(["Capsicum"], "capsicum", 0.9).crop_id == "Pepper"
    assert run(["Corn"]).crop_id == "Maize"


def test_blank_guess_and_blank_crops_are_ignored():
    assert run(["", "  "], "  ").unknown
    assert run(["Apple", ""], "").crop_id == "Apple"


def test_confidence_is_clamped_and_nan_is_ignored():
    assert run(["Apple"], "Apple", 7.0).confidence == 1.0
    assert run(["Apple", "Tomato"], "Apple", -3.0).needs_confirmation
    nan = float("nan")
    assert run(["Apple"], "Apple", nan).needs_confirmation is False      # treated as a missing confidence: single crop, guess agrees
    assert run([], "Apple", nan).confidence == 0.3


def test_images_are_not_needed():
    assert ident.identify([], ["Apple"]).crop_id == "Apple"


GRID = list(itertools.product([[], ["Apple"], ["Apple", "Tomato"], ["Apple", "Tomato", "Potato", "Maize"]],
                              [None, "Apple", "Tomato", "Grape"], [None, 0.0, 0.2, 0.5, 0.9, 1.0]))


@pytest.mark.parametrize(("farmer", "guess", "conf"), GRID)
def test_invariants_over_every_input_combination(farmer, guess, conf):
    r = run(farmer, guess, conf)
    assert sum(c.confidence for c in r.candidates) <= 1.0 + 1e-9
    assert all(0.0 <= c.confidence <= 1.0 for c in r.candidates)
    assert [c.confidence for c in r.candidates] == sorted((c.confidence for c in r.candidates), reverse=True)
    assert len(ids(r)) == len(set(ids(r)))
    if r.unknown:
        assert r.crop_id is None and r.needs_confirmation
    else:
        assert r.crop_id is not None and r.crop_id == ids(r)[0] and r.confidence == r.candidates[0].confidence

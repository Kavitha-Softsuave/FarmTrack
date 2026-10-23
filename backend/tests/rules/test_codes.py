from __future__ import annotations

import pytest

from app.rules import codes


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("M3", "M03"), ("M03", "M03"), (" m4 ", "M04"), ("M04", "M04"), ("1 + M3", "1+M03"), ("1+M03", "1+M03"),
        ("7 + 3", "7+3"), ("3+M04", "3+M04"), ("03", "3"), ("U12", "U12"), ("UNM", "UNM"), ("IRAC 3A", "3A"), ("FRAC 11", "11"),
        ("IRAC M02", "M02"), ("M05+3", "M05+3"), ("", ""), (None, ""), ("garbage words", ""),
    ],
)
def test_normalise_code(raw, expected):
    assert codes.normalise_code(raw) == expected


def test_components_split_mixtures_and_dedupe():
    assert codes.components("3 + M3 + 3") == ("3", "M03")
    assert codes.components("M03+11") == ("M03", "11")
    assert codes.components(None) == ()


def test_resistance_group_helpers():
    assert codes.has_dmi(codes.components("3+M04"))
    assert codes.has_qoi(codes.components("M03+11"))
    assert codes.has_sdhi(codes.components("7+3"))
    assert not codes.has_dmi(codes.components("1+M03"))


def test_irac_3a_is_not_dmi():
    """The pyrethroid group IRAC 3A must never be counted as the FRAC 3 (DMI) group."""
    assert not codes.has_dmi(codes.components("IRAC 3A"))
    assert not codes.has_dmi(codes.components("3A"))


def test_code_system_and_irac_guess():
    assert codes.code_system("IRAC 4A") == "irac"
    assert codes.code_system("FRAC 3") == "frac"
    assert codes.code_system("3") is None
    assert codes.looks_like_irac("IRAC 28")
    assert codes.looks_like_irac("4A")
    assert not codes.looks_like_irac("7 + 3")
    assert not codes.looks_like_irac("M03")


def test_shared_components():
    assert codes.shared(("3", "M04"), ("1", "M04")) == ("M04",)
    assert codes.shared(("3",), ("1",)) == ()

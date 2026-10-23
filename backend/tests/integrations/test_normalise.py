import pytest

from app.integrations.normalise import normalise_frac, normalise_phone


@pytest.mark.parametrize("raw,expected", [
    ("+91 00000 00001", "+910000000001"),
    ("9000000001", "+919000000001"),
    ("+91-90000-00001", "+919000000001"),
    ("", ""),
    (None, ""),
])
def test_phone(raw, expected):
    assert normalise_phone(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("M3", "M03"),
    ("M03", "M03"),
    ("M4", "M04"),
    ("1 + M3", "1+M03"),
    ("7 + 3", "7+3"),
    ("M01 + M03", "M01+M03"),
    ("IRAC 3A", "3A"),
    ("IRAC 12C+10A", "12C+10A"),
    ("frac 11", "11"),
    ("UNM", "UNM"),
    ("m3 + 11", "M03+11"),
    ("", None),
    ("   ", None),
    (None, None),
])
def test_frac(raw, expected):
    assert normalise_frac(raw) == expected

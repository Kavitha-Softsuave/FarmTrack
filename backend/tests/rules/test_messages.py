"""The message catalogue: EN + draft Hindi for every farmer-facing string, same placeholders, readable aloud."""
from __future__ import annotations

import re
from datetime import date, datetime
from string import Formatter

import pytest

from app.rules import messages as m


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


DEVANAGARI = re.compile(r"[ऀ-ॿ]")
UNITS = re.compile(r"\d\s?(?:mm|ml|kg|g|°C|C|%)\b|g/|ml/|\bkg/ha\b|\d°", re.IGNORECASE)


@pytest.mark.parametrize("key", sorted(m.CATALOGUE))
def test_every_message_has_english_and_hindi_with_the_same_placeholders(key):
    en, hi = m.CATALOGUE[key]
    assert en.strip() and hi.strip()
    assert DEVANAGARI.search(hi) and not DEVANAGARI.search(en)
    assert placeholders(en) == placeholders(hi), key


@pytest.mark.parametrize("key", sorted(m.CATALOGUE))
def test_every_message_renders_with_sample_parameters(key):
    names = placeholders(m.CATALOGUE[key][0])
    params = {n: m.Bilingual("Myclobutanil", "मायक्लोब्यूटानिल") if n == "name" else 7 for n in names}
    text = m.text(key, **params)
    assert text.en and text.hi and "{" not in text.en and "{" not in text.hi


@pytest.mark.parametrize("key", [k for k in sorted(m.CATALOGUE) if not k.endswith("_TITLE")])
def test_sentences_are_short_and_end_properly(key):
    en, hi = m.CATALOGUE[key]
    assert en.rstrip().endswith(".") and hi.rstrip().endswith("।"), key
    assert all(len(sentence.split()) <= 40 for sentence in re.split(r"(?<=[.।])\s+", en + " " + hi)), key


@pytest.mark.parametrize("key", sorted(m.CATALOGUE))
def test_units_are_written_as_words_so_a_voice_can_read_them(key):
    en, hi = m.CATALOGUE[key]
    assert not UNITS.search(en) and not UNITS.search(hi), key


def test_no_foreign_helpline_number_anywhere():
    blob = " ".join(en + hi for en, hi in m.CATALOGUE.values()) + " ".join(m.NON_CHEMICAL_HI.values())
    assert "1-800" not in blob and "222-1222" not in blob


def test_text_with_an_unknown_key_fails_loudly():
    with pytest.raises(KeyError):
        m.text("NOT_A_KEY")


def test_text_helpers():
    assert m.plain("DOSE_PER_200L", "en") == "The dose is for 200 litres of water."
    assert "200 लीटर" in m.plain("DOSE_PER_200L", "hi")
    assert m.text("DOSE_PER_200L").get("hi") == m.plain("DOSE_PER_200L", "hi")


def test_parameters_render_per_language():
    name = m.Bilingual("Captan", "कैप्टान")
    text = m.text("PROPOSED_BAN", name=name)
    assert text.en.startswith("Captan may be banned") and text.hi.startswith("कैप्टान पर")
    assert m.text("RISK_WASHOFF_RED", rain=12.0, days=7).en.count("12 millimetres") == 1
    assert "2.5 millimetres" in m.text("TIMING_WAIT", rain=2.5, hours=8).en


def test_dates_are_written_in_each_language():
    assert m.format_date(date(2026, 2, 5), "en") == "5 Feb" and m.format_date(date(2026, 2, 5), "hi") == "5 फ़रवरी"
    text = m.text("TANK_MIX_HISTORY", date=datetime(2026, 4, 14, 10, 0))
    assert "14 Apr" in text.en and "14 अप्रैल" in text.hi


def test_lists_are_joined_naturally():
    text = m.text("OFF_LABEL_HISTORY", products=["Meothrin", "Trot"])
    assert "Meothrin and Trot" in text.en and "Meothrin और Trot" in text.hi
    assert "Meothrin" in m.text("OFF_LABEL_HISTORY", products=["Meothrin"]).en


def test_number_formatting():
    assert m.format_number(12.0) == "12" and m.format_number(2.5) == "2.5" and m.format_number(0.0) == "0"


def test_every_catalogue_non_chemical_text_has_a_hindi_draft(ref):
    for disease in ref.diseases.values():
        text = disease.non_chemical
        if not text or text.lower().startswith("see ") or re.search(r"\boil\b", text, re.I):
            continue
        assert text in m.NON_CHEMICAL_HI, disease.disease_id
        out = m.non_chemical(text)
        assert out.en == text and DEVANAGARI.search(out.hi)


def test_unknown_non_chemical_text_falls_back_to_the_generic_measure():
    out = m.non_chemical("Something new nobody translated")
    assert out == m.text("HYGIENE")


def test_hindi_measures_have_no_orphan_english_sentences():
    for text in m.NON_CHEMICAL_HI.values():
        assert text.rstrip().endswith("।")

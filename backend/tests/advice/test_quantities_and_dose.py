from decimal import Decimal

import pytest

from app.advice.dose import allowed_quantities, dose_amounts, dose_text, parse_dose_unit
from app.advice.numbers import number_to_words
from app.advice.quantities import DAYS, MASS, PERCENT, VOLUME, extract_quantities, words_to_digits
from app.domain.types import ProductChoice
from tests.advice.helpers import master_rows, product


def q(text):
    return [(x.family, x.value) for x in extract_quantities(text)]


# ---------------------------------------------------------------------------------------------- quantities
@pytest.mark.parametrize("text,expected", [
    ("600 g in 200 litres of water", [(MASS, Decimal(600)), (VOLUME, Decimal(200000))]),
    ("600g in 200L", [(MASS, Decimal(600)), (VOLUME, Decimal(200000))]),
    ("0.6 kg per acre", [(MASS, Decimal(600))]),
    ("2 ml/L", [(VOLUME, Decimal(2))]),
    ("4 litres", [(VOLUME, Decimal(4000))]),
    ("0.1 percent solution", [(PERCENT, Decimal("0.1"))]),
    ("5% urea", [(PERCENT, Decimal(5))]),
    ("wait 21 days", [(DAYS, Decimal(21))]),
    ("1500 to 1750 g per hectare", [(MASS, Decimal(1750)), (MASS, Decimal(1500))]),
    ("600-800 ग्राम", [(MASS, Decimal(800)), (MASS, Decimal(600))]),
    ("200 लीटर पानी में 600 ग्राम", [(MASS, Decimal(600)), (VOLUME, Decimal(200000))]),
    ("21 दिन", [(DAYS, Decimal(21))]),
])
def test_extract_quantities(text, expected):
    assert sorted(q(text)) == sorted(expected)


def test_extract_ignores_numbers_without_a_unit_and_words_that_start_like_units():
    assert q("step 2 of 3, 12 hectares, 5 healthy plants, 3 grapes") == []


@pytest.mark.parametrize("text,expected", [
    ("six hundred grams in two hundred litres", "600 grams in 200 litres"),
    ("one hundred and five millilitres", "105 millilitres"),
    ("two point five litres", "2.5 litres"),
    ("twenty-one days", "21 days"),
    ("एक हज़ार पाँच सौ ग्राम", "1500 ग्राम"),
    ("छह सौ ग्राम", "600 ग्राम"),
    ("ढाई लीटर", "2.5 लीटर"),
    ("सात दिन", "7 दिन"),
    ("one of the plants", "one of the plants"),
    ("दो पत्तियाँ", "दो पत्तियाँ"),
])
def test_words_to_digits_only_before_a_unit(text, expected):
    assert words_to_digits(text) == expected


def test_dose_in_words_is_still_checked():
    assert q("use six hundred grams") == [(MASS, Decimal(600))]
    assert sorted(q("दो सौ लीटर पानी में छह सौ ग्राम")) == sorted([(VOLUME, Decimal(200000)), (MASS, Decimal(600))])


def test_round_trip_for_spoken_numbers():
    for n in (1, 7, 21, 60, 99, 105, 200, 600, 875, 1000, 1500, 9999):
        for lang, unit in (("en", "grams"), ("hi", "ग्राम")):
            assert q(f"{number_to_words(n, lang)} {unit}") == [(MASS, Decimal(n))]


# ---------------------------------------------------------------------------------------------- dose_text
@pytest.mark.parametrize("pid,en,hi", [
    ("P001", "600 g in 200 litres of water", "200 लीटर पानी में 600 ग्राम"),                                   # g/200L
    ("P003", "600 ml in 200 litres of water", "200 लीटर पानी में 600 मिलीलीटर"),                               # ml/200L
    ("P051", "4 litres in 200 litres of water", "200 लीटर पानी में 4 लीटर"),                                    # L/200L
    ("P079", "2 g per litre of water", "1 लीटर पानी में 2 ग्राम"),                                              # g/L
    ("P089", "1 ml per litre of water", "1 लीटर पानी में 1 मिलीलीटर"),                                          # ml/L
    ("P071", "500 ml per hectare", "प्रति हेक्टेयर 500 मिलीलीटर"),                                              # ml/ha
    ("P072", "1500 to 1750 g per hectare", "प्रति हेक्टेयर 1500 से 1750 ग्राम"),                                # g/ha, range
    ("P083", "0.875 to 1.25 kg per hectare", "प्रति हेक्टेयर 0.875 से 1.25 किलोग्राम"),                         # kg/ha, range
    ("P084", "2 kg per hectare, in 1000 litres of water", "प्रति हेक्टेयर 2 किलोग्राम, 1000 लीटर पानी में"),     # kg/ha in N L
    ("P070", "1.5 to 2 kg per hectare, in 750 litres of water", "प्रति हेक्टेयर 1.5 से 2 किलोग्राम, 750 लीटर पानी में"),
    ("P069", "1000 g per acre, in 300 to 400 litres of water", "प्रति एकड़ 1000 ग्राम, 300 से 400 लीटर पानी में"),  # g/acre in a range
    ("P096", "120 g per acre, in 240 litres of water", "प्रति एकड़ 120 ग्राम, 240 लीटर पानी में"),
    ("P095", "0.6 to 0.8 kg per acre, in 300 litres of water", "प्रति एकड़ 0.6 से 0.8 किलोग्राम, 300 लीटर पानी में"),
    ("P097", "0.2 percent solution in water", "0.2 प्रतिशत का घोल"),                                           # percent
    ("P048", "0.1 percent solution, poured on the soil around the base of the tree",
     "0.1 प्रतिशत का घोल, पेड़ के तने के चारों ओर ज़मीन में डालें"),                                             # percent_drench
    ("P086", "1 kg dimethomorph and 2 kg mancozeb per hectare",
     "प्रति हेक्टेयर 1 किलोग्राम डाइमेथोमॉर्फ और 2 किलोग्राम मैन्कोज़ेब"),                                          # combination row
])
def test_dose_text_examples(pid, en, hi):
    text = dose_text(product(pid))
    assert (text.en, text.hi) == (en, hi)


def test_every_dose_unit_in_the_master_is_covered():
    units = {r["dose_unit"] for r in master_rows().values()}
    assert len(units) == 16
    for unit in units:
        assert parse_dose_unit(unit) is not None, unit


def test_dose_text_for_every_product_is_complete_and_checkable():
    for pid in master_rows():
        p = product(pid)
        text = dose_text(p)
        assert text.en and text.hi, pid
        assert "/" not in text.en and "_" not in text.en, (pid, text.en)      # no raw unit code leaks into a sentence
        assert "ask your expert" not in text.en.lower(), pid                  # the 'no dose' fallback never fires for master data
        # what the text states is exactly what the validator allows for this product
        stated = {(x.family, x.value) for x in extract_quantities(text.en)} | {(x.family, x.value) for x in extract_quantities(text.hi)}
        assert stated <= allowed_quantities(p), (pid, text.en, stated - allowed_quantities(p))
        assert dose_amounts(p) <= stated, (pid, text.en)


def test_unknown_unit_falls_back_to_a_plain_sentence():
    p = ProductChoice(product_id="X1", crop="Apple", active_ingredient="Test", category="fungicide", dose_min=3, dose_max=3, dose_unit="pinch/tree")
    text = dose_text(p)
    assert text.en == "3 pinch/tree" and text.hi == "3 pinch/tree"
    assert allowed_quantities(p) == set()


def test_missing_dose_asks_for_the_expert():
    p = ProductChoice(product_id="X1", crop="Apple", active_ingredient="Test", category="fungicide")
    assert dose_text(p).en == "Ask your expert for the dose."

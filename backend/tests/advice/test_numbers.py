import pytest

from app.advice.numbers import digits_to_words, format_number, number_to_words

# Reference lists written by hand (not generated from the implementation). Hindi is a draft: a native speaker reviews it.
EN_0_100 = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen "
    "nineteen twenty "
    "twenty-one twenty-two twenty-three twenty-four twenty-five twenty-six twenty-seven twenty-eight twenty-nine thirty "
    "thirty-one thirty-two thirty-three thirty-four thirty-five thirty-six thirty-seven thirty-eight thirty-nine forty "
    "forty-one forty-two forty-three forty-four forty-five forty-six forty-seven forty-eight forty-nine fifty "
    "fifty-one fifty-two fifty-three fifty-four fifty-five fifty-six fifty-seven fifty-eight fifty-nine sixty "
    "sixty-one sixty-two sixty-three sixty-four sixty-five sixty-six sixty-seven sixty-eight sixty-nine seventy "
    "seventy-one seventy-two seventy-three seventy-four seventy-five seventy-six seventy-seven seventy-eight seventy-nine eighty "
    "eighty-one eighty-two eighty-three eighty-four eighty-five eighty-six eighty-seven eighty-eight eighty-nine ninety "
    "ninety-one ninety-two ninety-three ninety-four ninety-five ninety-six ninety-seven ninety-eight ninety-nine"
).split()

HI_0_99 = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ "
    "दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस "
    "तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस "
    "चालीस इकतालीस बयालीस तैंतालीस चौवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास "
    "पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ "
    "साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर "
    "सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी "
    "अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी "
    "नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()


def test_reference_lists_are_complete():
    assert len(EN_0_100) == 100 and len(HI_0_99) == 100


@pytest.mark.parametrize("n", range(100))
def test_english_0_to_99(n):
    assert number_to_words(n, "en") == EN_0_100[n].replace("-", " ")


@pytest.mark.parametrize("n", range(100))
def test_hindi_0_to_99(n):
    assert number_to_words(n, "hi") == HI_0_99[n]


def test_one_hundred():
    assert number_to_words(100, "en") == "one hundred"
    assert number_to_words(100, "hi") == "एक सौ"


@pytest.mark.parametrize("n,en,hi", [
    (105, "one hundred and five", "एक सौ पाँच"),
    (200, "two hundred", "दो सौ"),
    (250, "two hundred and fifty", "दो सौ पचास"),
    (600, "six hundred", "छह सौ"),
    (999, "nine hundred and ninety nine", "नौ सौ निन्यानवे"),
    (1000, "one thousand", "एक हज़ार"),
    (1005, "one thousand and five", "एक हज़ार पाँच"),
    (1500, "one thousand five hundred", "एक हज़ार पाँच सौ"),
    (1750, "one thousand seven hundred and fifty", "एक हज़ार सात सौ पचास"),
    (12000, "twelve thousand", "बारह हज़ार"),
    (99999, "ninety nine thousand nine hundred and ninety nine", "निन्यानवे हज़ार नौ सौ निन्यानवे"),
])
def test_hundreds_and_thousands(n, en, hi):
    assert number_to_words(n, "en") == en
    assert number_to_words(n, "hi") == hi


@pytest.mark.parametrize("value,en,hi", [
    (0.5, "zero point five", "आधा"),
    (1.5, "one point five", "डेढ़"),
    (2.5, "two point five", "ढाई"),
    (0.1, "zero point one", "शून्य दशमलव एक"),
    (0.875, "zero point eight seven five", "शून्य दशमलव आठ सात पाँच"),
    (12.5, "twelve point five", "बारह दशमलव पाँच"),
    ("2.50", "two point five", "ढाई"),
    (3.0, "three", "तीन"),
    ("0.25", "zero point two five", "शून्य दशमलव दो पाँच"),
])
def test_decimals(value, en, hi):
    assert number_to_words(value, "en") == en
    assert number_to_words(value, "hi") == hi


def test_negative_numbers():
    assert number_to_words(-2, "en") == "minus two"
    assert number_to_words(-2, "hi") == "माइनस दो"


def test_numbers_beyond_range_are_read_digit_by_digit():
    assert number_to_words(100000, "en") == "one zero zero zero zero zero"
    assert digits_to_words("105", "hi") == "एक शून्य पाँच"


def test_every_number_has_a_distinct_spelling():
    for lang in ("en", "hi"):
        words = [number_to_words(n, lang) for n in range(100_000)]
        assert all(words) and len(set(words)) == 100_000


@pytest.mark.parametrize("value,text", [(600.0, "600"), (0.875, "0.875"), ("1.50", "1.5"), (1000, "1000"), (2e-3, "0.002"), (-0.0, "0")])
def test_format_number(value, text):
    assert format_number(value) == text


@pytest.mark.parametrize("bad", ["abc", "", float("nan"), float("inf")])
def test_format_number_rejects_non_numbers(bad):
    with pytest.raises(ValueError):
        format_number(bad)

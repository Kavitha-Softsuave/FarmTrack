"""Number to words for the spoken advice, English and Hindi (0 to 99999 plus decimals).

A machine voice mispronounces digits and units, so the spoken text carries words only. Hindi numbers 0-99 are irregular
(every one has its own word), so they are a full table instead of a rule. The Hindi words are a draft for native review.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.domain.types import Lang

MAX_WORD_INT = 99_999

EN_ONES = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
           "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
EN_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

HI_0_99 = (
    "शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
    "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
    "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चौवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
    "पचास", "इक्यावन", "बावन", "तिरपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
    "साठ", "इकसठ", "बासठ", "तिरसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
    "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उनासी",
    "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे",
)
HI_HUNDRED = "सौ"
HI_THOUSAND = "हज़ार"
HI_POINT = "दशमलव"
HI_HALVES = {"0.5": "आधा", "1.5": "डेढ़", "2.5": "ढाई"}      # the forms a farmer actually says
EN_POINT = "point"


def _en_int(n: int) -> str:
    if n < 20:
        return EN_ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return EN_TENS[tens] + (f" {EN_ONES[ones]}" if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return f"{EN_ONES[hundreds]} hundred" + (f" and {_en_int(rest)}" if rest else "")
    thousands, rest = divmod(n, 1000)
    words = f"{_en_int(thousands)} thousand"
    if rest:
        words += f" and {_en_int(rest)}" if rest < 100 else f" {_en_int(rest)}"
    return words


def _hi_int(n: int) -> str:
    if n < 100:
        return HI_0_99[n]
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return f"{HI_0_99[hundreds]} {HI_HUNDRED}" + (f" {HI_0_99[rest]}" if rest else "")
    thousands, rest = divmod(n, 1000)
    return f"{HI_0_99[thousands]} {HI_THOUSAND}" + (f" {_hi_int(rest)}" if rest else "")


def _digit_word(d: str, lang: Lang) -> str:
    return HI_0_99[int(d)] if lang == "hi" else EN_ONES[int(d)]


def digits_to_words(digits: str, lang: Lang) -> str:
    """Digit by digit ('105' -> 'one zero five'): the fallback for numbers too long to read as a quantity."""
    return " ".join(_digit_word(d, lang) for d in digits if d.isdigit())


def format_number(value: int | float | str | Decimal) -> str:
    """Plain decimal text without exponent or trailing zeros: 600.0 -> '600', 0.875 -> '0.875'."""
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {value!r}") from exc
    if not d.is_finite():
        raise ValueError(f"not a finite number: {value!r}")
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def number_to_words(value: int | float | str | Decimal, lang: Lang) -> str:
    """600 -> 'six hundred' / 'छह सौ'; 2.5 -> 'two point five' / 'ढाई'; negative numbers get 'minus' / 'ऋण'."""
    text = format_number(value)
    negative = text.startswith("-")
    text = text.lstrip("-")
    whole, _, fraction = text.partition(".")
    if lang == "hi" and text in HI_HALVES:
        words = HI_HALVES[text]
    else:
        n = int(whole)
        if n > MAX_WORD_INT:
            words = digits_to_words(whole, lang)
        else:
            words = _hi_int(n) if lang == "hi" else _en_int(n)
        if fraction:
            words += f" {HI_POINT if lang == 'hi' else EN_POINT} {digits_to_words(fraction, lang)}"
    if negative:
        words = f"{'माइनस' if lang == 'hi' else 'minus'} {words}"
    return words

import random
import re
import unicodedata

import pytest

from app.advice.spoken import build_spoken, normalise_spoken, short_hindi, split_sentences
from app.advice.templates import build_template, finalize_draft
from tests.advice.helpers import advice_output, master_rows, plain_output, product, ref, risk, warning

ALLOWED_PUNCTUATION = set(".,?!।'")


def has_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def only_speakable(text: str) -> bool:
    return all(unicodedata.category(ch)[0] in "LMZ" or ch in ALLOWED_PUNCTUATION for ch in text)


@pytest.mark.parametrize("raw,spoken", [
    ("600 g in 200 litres of water", "six hundred grams in two hundred litres of water"),
    ("600 g per 200 L", "six hundred grams per two hundred litres"),
    ("1 g per litre of water", "one gram per litre of water"),
    ("0.5 ml per litre", "zero point five millilitres per litre"),
    ("2.5 ml/L", "two point five millilitres per litre"),
    ("1500 to 1750 g per hectare", "one thousand five hundred to one thousand seven hundred and fifty grams per hectare"),
    ("0.6-0.8 kg per acre", "zero point six to zero point eight kilograms per acre"),
    ("Wait 21 days.", "Wait twenty one days."),
    ("Spray again within 7 days.", "Spray again within seven days."),
    ("Do not spray above 30 °C.", "Do not spray above thirty degrees Celsius."),
    ("Use 5% urea.", "Use five percent urea."),
    ("Rain of 10 mm in 12 h", "Rain of ten millimetres in twelve hours"),
    ("Fluxapyroxad + Difenoconazole", "Fluxapyroxad and Difenoconazole"),
    ("1,000 litres", "one thousand litres"),
    ("it is -2 degrees", "it is minus two degrees"),
    ("tank-mix (do not)!", "tank mix, do not!"),
])
def test_english_normalisation(raw, spoken):
    assert normalise_spoken(raw, "en") == spoken


@pytest.mark.parametrize("raw,spoken", [
    ("200 लीटर पानी में 600 ग्राम", "दो सौ लीटर पानी में छह सौ ग्राम"),
    ("600 g in 200 L", "छह सौ ग्राम in दो सौ लीटर"),
    ("0.5 ml, 1.5 L", "आधा मिलीलीटर, डेढ़ लीटर"),
    ("1 लीटर पानी में 2.5 ग्राम", "एक लीटर पानी में ढाई ग्राम"),
    ("12-14 दिन", "बारह से चौदह दिन"),
    ("5% यूरिया", "पाँच प्रतिशत यूरिया"),
    ("30 °C", "तीस डिग्री सेल्सियस"),
    ("कैप्टान + टेबुकोनाज़ोल", "कैप्टान और टेबुकोनाज़ोल"),
    ("६०० ग्राम", "छह सौ ग्राम"),
    ("2 kg/ha", "दो किलोग्राम प्रति हेक्टेयर"),
])
def test_hindi_normalisation(raw, spoken):
    assert normalise_spoken(raw, "hi") == spoken


def test_hindi_chemical_names_are_written_in_devanagari():
    text = normalise_spoken("Mancozeb और Hexaconazole + Zineb, 2 g/L", "hi", ref())
    assert text == "मैन्कोज़ेब और हेक्साकोनाज़ोल और ज़िनेब, दो ग्राम प्रति लीटर"
    assert normalise_spoken("Sulphur 3 g", "hi", ref()) == "गंधक तीन ग्राम"        # the bracketed synonym is dropped for the ear


def test_english_keeps_latin_names():
    assert "Mancozeb" in normalise_spoken("Use Mancozeb.", "en", ref())


def test_short_hindi_drops_brackets():
    assert short_hindi("गंधक (सल्फर)") == "गंधक"
    assert short_hindi("कैप्टान") == "कैप्टान"


def test_symbols_and_emoji_are_removed():
    out = normalise_spoken("Spray *now* #1 [fast] {ok} <b>wow</b> 🙂 ~ ^ | = _ \\ /", "en")
    assert only_speakable(out) and not has_digit(out)
    assert "now" in out and "fast" in out


def test_random_noise_never_leaves_a_digit_or_symbol():
    rng = random.Random(7)
    alphabet = list("0123456789 .,-+/%°C gGlLmMkKhH:;()[]{}*#_&'\"abc") + ["६", "७", "²", "½", "🙂", "।", "ग्राम", " L ", " ml ", " kg ", "लीटर"]
    for _ in range(1500):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 40)))
        for lang in ("en", "hi"):
            out = normalise_spoken(text, lang, ref())
            assert not has_digit(out), (text, out)
            assert only_speakable(out), (text, out)


def test_split_sentences_handles_both_scripts_and_decimals():
    assert split_sentences("Use 0.5 ml. Wait. Go?") == ["Use 0.5 ml.", "Wait.", "Go?"]
    assert split_sentences("एक। दो। तीन।") == ["एक।", "दो।", "तीन।"]
    assert split_sentences("") == []


# ---------------------------------------------------------------------------------------------- template spoken text
def spoken_for(out):
    return finalize_draft(build_template(out, ref()), out, ref()).spoken


@pytest.mark.parametrize("pid", sorted(master_rows()))
def test_spoken_text_of_every_product_is_clean(pid):
    """Property over all 97 products: no digit, no symbol, 3 to 6 sentences, Hindi without Latin letters, English without Devanagari."""
    p = product(pid)
    for action in ("spray_now", "wait", "repeat_within_days"):
        out = advice_output(pids=(pid,), action=action, crop_id=p.crop, disease_id=None)
        spoken = spoken_for(out)
        for lang, text in (("en", spoken.en), ("hi", spoken.hi)):
            assert text, (pid, lang)
            assert not has_digit(text), (pid, lang, text)
            assert only_speakable(text), (pid, lang, text)
            assert 3 <= len(split_sentences(text)) <= 6, (pid, lang, text)
        assert not re.search("[A-Za-z]", spoken.hi), (pid, spoken.hi)
        assert not re.search("[ऀ-ॿ]", spoken.en), (pid, spoken.en)


def test_advice_spoken_reads_the_dose_in_words():
    spoken = spoken_for(advice_output(pids=("P001",)))
    assert "six hundred grams in two hundred litres of water" in spoken.en
    assert "दो सौ लीटर पानी में छह सौ ग्राम" in spoken.hi
    assert "Captan" in spoken.en and "Captaf" in spoken.en and "कैप्टान" in spoken.hi


def test_spoken_mentions_waiting_period_in_words():
    spoken = spoken_for(advice_output(pids=("P002",)))
    assert "twenty one days" in spoken.en
    assert "इक्कीस दिन" in spoken.hi


def test_spoken_for_wait_says_wait_and_skips_the_waiting_period():
    spoken = spoken_for(advice_output(pids=("P002",), action="wait"))
    assert "Do not spray now" in spoken.en and "अभी छिड़काव न करें" in spoken.hi
    assert "harvest" not in spoken.en


def test_spoken_severity_tone():
    red = spoken_for(advice_output(severity="red")).en
    yellow = spoken_for(advice_output(severity="yellow")).en
    green = spoken_for(advice_output(severity="green")).en
    assert "serious" in red and "needs attention soon" in yellow and "serious" not in green and "attention" not in green


def test_spoken_always_has_protective_clothing_and_expert_lines():
    spoken = spoken_for(advice_output())
    assert "gloves" in spoken.en and "expert" in spoken.en
    assert "दस्ताने" in spoken.hi and "खेती के जानकार" in spoken.hi


@pytest.mark.parametrize("status", ["expert_review", "no_approved_data", "not_a_disease", "needs_more_info"])
def test_spoken_for_statuses_without_medicine(status):
    out = plain_output(status, warnings=[warning()], risks=[risk()])
    spoken = build_spoken(out, ref())
    assert 3 <= len(split_sentences(normalise_spoken(spoken.en, "en"))) <= 6
    assert 3 <= len(split_sentences(normalise_spoken(spoken.hi, "hi", ref()))) <= 6


def test_rule_measures_are_screen_only_the_spoken_text_uses_whole_sentences():
    fragment = advice_output().non_chemical[0].model_copy(update={"en": "Resistant varieties (Kufri Jyoti)", "hi": "रोग सहने वाली किस्में"})
    spoken = build_spoken(plain_output("expert_review", non_chemical=[fragment]), ref())
    assert "Kufri" not in spoken.en and "किस्में" not in spoken.hi
    assert "Remove fallen leaves and badly spotted leaves" in spoken.en

"""Small English/Hindi word lists used by retrieval and question handling: crop names, medicine-seeking words and
equivalent-term groups. Hindi spellings are draft (native review pending); matching is done on normalised text, so
nukta and chandrabindu variants are covered.
"""
from __future__ import annotations

import re

from app.rag.text import normalize, stem, tokenize

# canonical crop id (as in data/reference/product_master.csv and the disease catalogue) -> names farmers use
CROP_ALIASES: dict[str, tuple[str, ...]] = {
    # crops that exist in the approved notes
    "Apple": ("apple", "apples", "seb", "सेब"),
    "Tomato": ("tomato", "tomatoes", "tamatar", "टमाटर"),
    "Potato": ("potato", "potatoes", "aloo", "alu", "आलू"),
    "Maize": ("maize", "corn", "makka", "मक्का", "भुट्टा"),
    "Grape": ("grape", "grapes", "angoor", "अंगूर"),
    "Cherry": ("cherry", "cherries", "चेरी"),
    "Peach": ("peach", "peaches", "aadu", "आड़ू"),
    "Pepper": ("bell pepper", "capsicum", "shimla mirch", "शिमला मिर्च"),
    "Strawberry": ("strawberry", "strawberries", "स्ट्रॉबेरी", "स्ट्रोबेरी"),
    "Blueberry": ("blueberry", "blueberries", "ब्लूबेरी"),
    "Orange": ("santra", "sweet orange", "संतरा"),   # bare "orange" is also a colour in disease descriptions
    "Raspberry": ("raspberry", "raspberries", "रास्पबेरी", "रसभरी"),
    "Soybean": ("soybean", "soybeans", "soya", "सोयाबीन"),
    "Squash": ("squash", "pumpkin", "कद्दू"),
    # other Himachal crops: no approved notes, listed so that a medicine question about them is recognised and refused
    "Mango": ("mango", "mangoes", "aam", "आम"),
    "Plum": ("plum", "plums", "आलूबुखारा", "आलू बुखारा"),
    "Pear": ("pear", "pears", "nashpati", "नाशपाती"),
    "Apricot": ("apricot", "apricots", "khubani", "खुबानी"),
    "Pomegranate": ("pomegranate", "anar", "अनार"),
    "Kiwi": ("kiwi", "कीवी"),
    "Walnut": ("walnut", "walnuts", "akhrot", "अखरोट"),
    "Almond": ("almond", "almonds", "badam", "बादाम"),
    "Citrus": ("lemon", "citrus", "kinnow", "nimbu", "नींबू", "किन्नू", "माल्टा"),
    "Cabbage": ("cabbage", "patta gobhi", "पत्ता गोभी", "पत्तागोभी"),
    "Cauliflower": ("cauliflower", "phool gobhi", "फूल गोभी", "फूलगोभी"),
    "Garlic": ("garlic", "lahsun", "लहसुन"),
    "Onion": ("onion", "onions", "pyaz", "प्याज"),
    "Ginger": ("ginger", "adrak", "अदरक"),
    "Chilli": ("chilli", "chili", "chillies", "mirch", "मिर्च"),
    "Cucumber": ("cucumber", "kheera", "खीरा"),
    "Brinjal": ("brinjal", "eggplant", "baingan", "बैंगन"),
    "Wheat": ("wheat", "gehun", "gehu", "गेहूं", "गेहूँ"),
    "Rice": ("rice", "paddy", "dhan", "धान", "चावल"),
    "Barley": ("barley", "jau", "जौ"),
    "Banana": ("banana", "bananas", "kela", "केला"),
    "Papaya": ("papaya", "papita", "पपीता"),
    "Guava": ("guava", "amrud", "अमरूद"),
    "Rose": ("rose", "roses", "gulab", "गुलाब"),
    "Cotton": ("cotton", "kapas", "कपास"),
    "Sugarcane": ("sugarcane", "ganna", "गन्ना"),
}

def _words(text: str) -> frozenset[str]:
    return frozenset(normalize(w) for w in text.split())


# words that always ask for a medicine, a cure or a dose
_RECOMMEND = _words(
    "medicine medicines medication cure treat treatment remedy remedies dose dosage control drug dawa dawai davai "
    "इलाज उपचार मात्रा रोकथाम नियंत्रण"
)
# product nouns: they ask for a recommendation only together with an asking word ("which fungicide ...")
_PRODUCT_NOUNS = _words(
    "pesticide pesticides fungicide fungicides insecticide insecticides acaricide miticide chemical chemicals product "
    "products brand brands दवा दवाई दवाइयां दवाएं दवाइयाँ दवाएँ कीटनाशक फफूंदनाशक फफूंदनाशी फफूंदनाशकों माइटनाशक ब्रांड रसायन"
)
_ASKING = _words(
    "which what suggest recommend recommended best name कौन कौनसी कौनसा कौनसे बताइए बताएं बताएँ बताओ बताइये सुझाइए सुझाएं सुझाओ"
)
_SPRAY = _words("spray sprays spraying sprayed chidkav छिड़काव छिड़कें छिड़कना स्प्रे")
# every word that makes a question a medicine question (refused for crops without approved data)
MEDICINE_WORDS: frozenset[str] = _RECOMMEND | _PRODUCT_NOUNS | _SPRAY

# groups of equivalent terms (already stemmed/normalised on use): a query term matches a note if the note has any member
_GROUPS_RAW: tuple[tuple[str, ...], ...] = (
    ("medicine", "medication", "treatment", "treat", "cure", "remedy", "pesticide", "fungicide", "insecticide",
     "acaricide", "chemical", "product", "dawa", "dawai", "दवा", "दवाई", "दवाइयां", "दवाएं", "कीटनाशक", "फफूंदनाशक",
     "फफूंदनाशी", "इलाज", "उपचार", "रसायन"),
    ("rain", "rainfall", "rainy", "barish", "बारिश", "बरसात", "वर्षा"),
    ("spray", "chidkav", "छिड़काव", "छिड़कें", "स्प्रे"),
    ("dose", "dosage", "quantity", "amount", "मात्रा"),
    ("harvest", "तुड़ाई", "कटाई"),
    ("wait", "waiting", "प्रतीक्षा", "रुकना", "रुकें", "इंतजार"),
    ("mix", "mixing", "mixture", "मिलाना", "मिलाएं", "मिलाएँ", "मिलाते", "मिश्रण"),
    ("scab", "स्कैब", "पपड़ी"),
    ("blight", "झुलसा"),
    ("mite", "mites", "माइट", "मकड़ी"),
    ("aphid", "एफिड"),
    ("virus", "वायरस"),
    ("mildew", "मिल्ड्यू", "चूर्णिल"),
    ("leaf", "leaves", "पत्ती", "पत्तियों", "पत्ते", "पत्तियां"),
    ("safe", "safety", "protect", "protective", "precaution", "precautions", "careful", "caution", "सुरक्षित", "सुरक्षा",
     "सावधानी", "सावधानियां"),
)


def _term(word: str) -> str:
    return stem(normalize(word))


# product notes are about medicine and doses even when they never say so: indexed with these extra terms
PRODUCT_NOTE_CONCEPTS: tuple[str, ...] = tuple(
    _term(w) for w in ("medicine", "product", "treatment", "dose", "दवा", "दवाई", "मात्रा", "इलाज")
)


ALIAS_GROUPS: tuple[frozenset[str], ...] = tuple(frozenset(_term(w) for w in group) for group in _GROUPS_RAW) + tuple(
    frozenset(_term(a) for a in aliases if " " not in a) | {_term(canon)}
    for canon, aliases in CROP_ALIASES.items()
)

_ALIAS_OF: dict[str, frozenset[str]] = {}
for _group in ALIAS_GROUPS:
    for _member in _group:
        _ALIAS_OF[_member] = _group | _ALIAS_OF.get(_member, frozenset())


def alias_group(term: str) -> frozenset[str]:
    """The set of terms equivalent to `term` (always contains `term` itself)."""
    return _ALIAS_OF.get(term, frozenset()) | {term}


_WORD_EDGE_BEFORE = r"(?<![\w\u0900-\u097F])"
_WORD_EDGE_AFTER = r"(?![\w\u0900-\u097F])"
# "आम" is mango but also "common" (आम तौर पर): do not read it as a crop in those phrases
_NOT_MANGO = r"(?!\s*(?:तौर|तोर|लोग|आदमी|बात))"


def _alias_pattern(alias: str) -> re.Pattern[str]:
    extra = _NOT_MANGO if normalize(alias) == normalize("आम") else ""
    return re.compile(_WORD_EDGE_BEFORE + re.escape(normalize(alias)) + _WORD_EDGE_AFTER + extra)


_CROP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (crop, _alias_pattern(alias)) for crop, aliases in CROP_ALIASES.items() for alias in aliases
)


def detect_crops(text: str) -> list[str]:
    """Canonical crop ids named in `text`, in order of first appearance, without duplicates.
    A name inside a longer name ("मिर्च" inside "शिमला मिर्च") is ignored."""
    norm = normalize(text)
    spans: list[tuple[int, int, str]] = []
    for crop, pattern in _CROP_PATTERNS:
        spans.extend((m.start(), m.end(), crop) for m in pattern.finditer(norm))
    kept = [
        (start, crop) for start, end, crop in spans
        if not any(o != (start, end, crop) and o[0] <= start and end <= o[1] and (o[1] - o[0]) > (end - start)
                   for o in spans)
    ]
    found: list[str] = []
    for _, crop in sorted(kept):
        if crop not in found:
            found.append(crop)
    return found


def asks_for_recommendation(text: str) -> bool:
    """True when the question asks WHICH medicine, cure or dose to use (not merely mentions chemicals)."""
    tokens = set(tokenize(text))
    return bool(tokens & _RECOMMEND) or bool(tokens & _ASKING and tokens & _PRODUCT_NOUNS)


def asks_for_medicine(text: str) -> bool:
    """True when the question is about a medicine, a product or spraying."""
    return any(w in MEDICINE_WORDS for w in tokenize(text))

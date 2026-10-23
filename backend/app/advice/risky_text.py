"""Extra checks on LLM advice text that the product, dose and timing checks of `validator.py` cannot see.

Found by throwing hostile drafts at the validator (tests/advice/test_hostile_llm.py). Each check is deliberately blunt: a rejected
draft only costs the LLM wording (the safe template is always used instead), a missed one could mislead a farmer.

- contact details: links, helpline and phone numbers (a model must never invent who to call)
- a denied waiting period ("no need to wait before picking", "harvest tomorrow")
- advice to change the dose or the frequency, and doses in kitchen units (spoons, cups, sachets)
- 'spray now' sentences when the rules say wait or give no medicine, in English and Hindi, even with a hedge word elsewhere in the sentence
- Hindi spellings of chemicals: any Hindi name of a product that is not in the rule output, however it is spelled, and names that look
  like pesticides (-conazole, -strobin, -phos ...) but are in no list
"""
from __future__ import annotations

import re
import unicodedata

from app.advice.names import DEVA_RANGE, norm_deva

_D = DEVA_RANGE
_W = rf"[\w{_D}]"             # a word character, matras included (\w alone stops at a vowel sign)
_NW = rf"[^\w{_D}]"


_INVISIBLE = "​‌‍‎‏⁠﻿­"


def clean(text: str) -> str:
    """Compatibility-normalise (full-width letters, ligatures) and drop invisible characters, so 'Man<zero width>cozeb' cannot hide.

    Zero-width joiners stay between Devanagari letters, where Hindi spelling uses them."""
    normal = unicodedata.normalize("NFKC", text)
    normal = re.sub(rf"(?<![{_D}])[{_INVISIBLE}]|[{_INVISIBLE}](?![{_D}])", "", normal)
    return "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in normal if unicodedata.category(ch) != "Cf" or ch in "‌‍")


def _search(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


# ---------------------------------------------------------------------------------------------------- contact details
_LINK = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|org|net|app|io|me|co\.in|gov\.in|nic\.in)\b|\w@\w", re.IGNORECASE)
_HELPLINE = re.compile(r"\bhelp ?line\b|\btoll[- ]?free\b|\bwhats ?app\b|\b1[- ]?800\b|हेल्प ?लाइन|टोल[- ]?फ्री|व्हाट्सएप|वॉट्सऐप", re.IGNORECASE)


def contact_problems(text: str) -> list[str]:
    squeezed = re.sub(r"(?<=\d)[\s\-](?=\d)", "", text)                 # '1800 180 1551' -> '18001801551'
    if _LINK.search(text) or _HELPLINE.search(text) or re.search(r"\d{7,}", squeezed):
        return ["contact_details_in_text"]
    return []


# ---------------------------------------------------------------------------------------------------- waiting period
_NO_WAIT_EN = (
    r"\bno (?:need to wait|waiting period|wait(?:ing)? (?:time|needed|required))\b",
    r"\bwaiting period (?:is|of|:)?\s*(?:zero|none|0|not needed|not required)\b",
    r"\b(?:harvest|harvesting|pick|picking|eat|eating|sell|selling)\b[^.!?]{0,50}\b(?:immediately|right away|straight away|at once|"
    r"the same day|same day|next day|tomorrow|today|any ?time|whenever)\b",
    r"\bsafe to (?:harvest|eat|pick|sell)\b[^.!?]{0,30}\b(?:now|immediately|right away|after (?:the )?spray)",
)
_HI_TIME = rf"(?<![{_D}])(?:तुरंत|उसी दिन|अगले दिन|कल|कभी भी|फौरन|फ़ौरन)(?![{_D}])"
_NO_WAIT_HI = (
    r"(?:रुकने|इंतजार|प्रतीक्षा)[^।.!?]{0,25}(?:जरूरत|आवश्यकता)[^।.!?]{0,12}नहीं",
    r"कोई\s+(?:प्रतीक्षा|इंतजार|रुकने)",
    r"प्रतीक्षा अवधि\s*(?:शून्य|नहीं)",
    rf"(?<![{_D}])(?:तुड़ाई|तोड़|खाना|खाएँ|खा सकते|बेच|बेचें)[^।.!?]{{0,40}}{_HI_TIME}",
)


def waiting_denial_problems(sentence: str, lang: str) -> list[str]:
    hit = (any(_search(p, sentence) for p in _NO_WAIT_EN) if lang == "en"
           else any(re.search(norm_deva(p), norm_deva(sentence)) for p in _NO_WAIT_HI))
    return ["waiting_period_denied"] if hit else []


# ---------------------------------------------------------------------------------------------------- dose and frequency
_DOSE_CHANGE_EN = re.compile(
    r"\b(?:double|triple|twice the|extra|more than|higher|stronger|heavier|increase|increasing|raise|add more|top up|full strength|"
    r"undiluted|neat)\b[^.!?]{0,30}\b(?:dose|dosage|amount|quantity|concentration|medicine|chemical|spray|mixture|strength)\b|"
    r"\b(?:dose|dosage|amount|quantity)\b[^.!?]{0,25}\b(?:double|increase|higher|more|stronger)\b|\bwithout (?:any )?water\b", re.IGNORECASE)
_FREQUENCY_EN = re.compile(
    r"\b(?:twice|thrice)\b|\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:times|x)\b|"
    r"\bevery\s+(?:day|morning|evening|other day|week|night)\b|\b(?:daily|weekly|each day|once a week|once a day)\b", re.IGNORECASE)
_KITCHEN_EN = re.compile(
    r"\b(?:spoons?|spoonfuls?|teaspoons?|tablespoons?|tbsp|tsp|cups?|glass(?:es)?|mugs?|buckets?|handfuls?|pinch(?:es)?|"
    r"bottle ?caps?|capfuls?|lids?|palmfuls?|fistfuls?|sachets?|packets?|pouch(?:es)?)\b", re.IGNORECASE)
_DOSE_CHANGE_HI = re.compile(norm_deva(
    r"दोगुना|दुगना|दुगुना|तिगुना|ज़्यादा मात्रा|ज्यादा मात्रा|अधिक मात्रा|मात्रा (?:को )?बढ़ा|और ज़्यादा दवा|और ज्यादा दवा|बिना पानी"))
_FREQUENCY_HI = re.compile(norm_deva(
    rf"(?<![{_D}])(?:दो|तीन|चार|पाँच|पांच|\d+)\s*बार(?![{_D}])|रोज़|रोज|रोजाना|प्रतिदिन|हर दिन|हर सुबह|हर शाम|हर रात|हर हफ्ते|हर सप्ताह|साप्ताहिक"))
_KITCHEN_HI = re.compile(norm_deva(
    rf"चम्मच|(?<![{_D}])कप(?![{_D}])|गिलास|(?<![{_D}])मग(?![{_D}])|बाल्टी|मुट्ठी|चुटकी|ढक्कन|पैकेट|थैली|पुड़िया|सैशे"))


def dosing_style_problems(sentence: str, lang: str) -> list[str]:
    """Problems for advice that changes how much or how often to spray, or measures a dose in kitchen units."""
    problems: list[str] = []
    if lang == "en":
        if _DOSE_CHANGE_EN.search(sentence):
            problems.append("dose_change_advised")
        if _FREQUENCY_EN.search(sentence):
            problems.append("frequency_advised")
        if _KITCHEN_EN.search(sentence):
            problems.append("household_dose_unit")
    else:
        text = norm_deva(sentence)
        if _DOSE_CHANGE_HI.search(text):
            problems.append("dose_change_advised")
        if _FREQUENCY_HI.search(text):
            problems.append("frequency_advised")
        if _KITCHEN_HI.search(text):
            problems.append("household_dose_unit")
    return problems


# ---------------------------------------------------------------------------------------------------- spray now
_SPRAY_VERB_EN = r"(?:spray(?:s|ed|ing)?|apply|applying|drench(?:ing)?|dust(?:ing)?)"
_NOW_EN = re.compile(r"\b(?:now|today|immediately|right away|straight away|at once|asap|without delay|this (?:morning|evening|afternoon)|"
                     r"tonight|tomorrow)\b", re.IGNORECASE)
_NEGATED_EN = re.compile(rf"\b(?:not|never|no|avoid|don't|dont|without|stop|hold off|delay|wait|waiting|until|before|after|once|when|"
                         rf"if|unless|while|ask|expert)\b(?:\W+\w+){{0,4}}?\W+{_SPRAY_VERB_EN}\b|n't\W+(?:\w+\W+){{0,3}}?{_SPRAY_VERB_EN}\b",
                         re.IGNORECASE)
_SPRAY_VERB_HI = norm_deva("छिड़क|स्प्रे|स्प्रै|छिडक")
_NOW_HI = re.compile(rf"(?<![{_D}])(?:{norm_deva('अभी|आज|तुरंत|फौरन|फ़ौरन|जल्दी से|इसी समय|कल')})(?![{_D}])")
_NEG_HI = norm_deva("नहीं|मत|बाद|पहले|जब तक|जब|अगर|यदि|रुक|इंतज़ार|प्रतीक्षा|टाल")
_NEGATED_HI = re.compile(
    rf"(?<![{_D}])(?:{_NEG_HI}){_W}*{_NW}+(?:{_W}+{_NW}+){{0,3}}?(?:{_SPRAY_VERB_HI})|"
    rf"(?:{_SPRAY_VERB_HI}){_W}*{_NW}+(?:{_W}+{_NW}+){{0,1}}?(?:नहीं|(?<![{_D}])न(?![{_D}])\s*(?:करें|करना|कीजिए))")


def spray_now_unhedged(sentence: str, lang: str) -> bool:
    """A sentence that tells the farmer to spray now/today/tomorrow without a negation or condition right before the spray verb.

    'Spray now, there is no need to wait' counts (the 'no' is not next to the verb); 'Do not spray today' does not."""
    if lang == "hi":
        text = norm_deva(sentence)
        return bool(re.search(_SPRAY_VERB_HI, text) and _NOW_HI.search(text) and not _NEGATED_HI.search(text))
    return bool(re.search(_SPRAY_VERB_EN, sentence, re.IGNORECASE) and _NOW_EN.search(sentence) and not _NEGATED_EN.search(sentence))


# ---------------------------------------------------------------------------------------------------- Hindi chemical names
_BLOCKED_HINDI = (
    "डाइकोफोल", "डाइनोकैप", "मिथोमिल", "मोनोक्रोटोफॉस", "मैलाथियान", "डाइमेथोएट", "पाइडिफ्लुमेटोफेन", "फेनप्रोपेथ्रिन",
    "थायामेथोक्सम", "स्ट्रेप्टोमाइसिन", "टेट्रासाइक्लिन", "ग्लाइफोसेट", "पैराक्वाट", "एंडोसल्फान", "कार्बोफ्यूरान", "साइपरमेथ्रिन",
    "डेल्टामेथ्रिन", "डीडीटी", "राउंडअप", "ग्रामोक्सोन", "रोगोर", "बाविस्टिन", "डाइथेन", "इंडोफिल", "कॉन्फिडोर", "टिल्ट", "ब्लिटॉक्स",
)
_PESTICIDE_ENDINGS = (
    "कोनाज़ोल", "कोनेज़ोल", "स्ट्रोबिन", "थ्रिन", "मेक्टिन", "क्लोप्रिड", "ज़ेब", "फॉस", "फोस", "फास", "थियान", "थिओन", "थायोन",
    "क्वाट", "फ्यूरान", "सल्फान",
)
_MIN_NAME_KEY = 4


def phonetic_key(word: str) -> str:
    """A spelling-insensitive key for a Devanagari word: no nukta, nasal sign, nasal+halant, matras collapsed, long = short vowels.

    'मैन्कोज़ेब', 'मैंकोज़ेब' and 'मेनकोजेब' all give the same key, so a chemical cannot be written past the name lists."""
    text = unicodedata.normalize("NFC", unicodedata.normalize("NFD", clean(word)).replace("़", ""))
    text = re.sub("[नम]्", "", text)
    for source, target in (("ं", ""), ("ँ", ""), ("ः", ""), ("ै", "े"), ("ौ", "ो"), ("ऐ", "ए"), ("औ", "ओ"), ("ॉ", "ो"), ("ऑ", "ओ"),
                           ("ी", "ि"), ("ू", "ु"), ("ई", "इ"), ("ऊ", "उ"), ("ा", ""), ("्", ""), ("ृ", "ि")):
        text = text.replace(source, target)
    return re.sub(rf"[^{_D}A-Za-z0-9]", "", text)


_BLOCKED_KEYS = {phonetic_key(n) for n in _BLOCKED_HINDI}
_ENDING_KEYS = tuple(phonetic_key(e) for e in _PESTICIDE_ENDINGS)


def _tokens(text: str) -> list[str]:
    return re.findall(rf"[{_D}]+", clean(text))


def phrase_keys(name: str) -> set[str]:
    """Keys of a (possibly several word) Hindi product name; single words shorter than the minimum are ignored."""
    words = [phonetic_key(w) for w in _tokens(name)]
    key = " ".join(w for w in words if w)
    return {key} if len(key.replace(" ", "")) >= _MIN_NAME_KEY else set()


def hindi_names_in(text: str, known: dict[str, set[str]]) -> set[str]:
    """Keys from `known` (key -> anything) that occur in `text` as a word or as 2 to 4 consecutive words."""
    keys = [phonetic_key(w) for w in _tokens(text)]
    found: set[str] = set()
    for size in (1, 2, 3, 4):
        for start in range(len(keys) - size + 1):
            window = " ".join(keys[start:start + size])
            if window in known:
                found.add(window)
    return found


def unlisted_hindi_chemicals(text: str, known: dict[str, set[str]], allowed: set[str]) -> list[str]:
    """Problem codes for Hindi text that names a product the rules did not choose, or something that looks like a pesticide.

    `known` maps phonetic keys of every product (master, glossary) to product ids; `allowed` are the keys the rules chose or quoted."""
    problems = [f"product_not_in_rules:{key}" for key in sorted(hindi_names_in(text, known)) if key not in allowed]
    for key in sorted({phonetic_key(w) for w in _tokens(text)}):
        if key in _BLOCKED_KEYS and key not in allowed:
            problems.append(f"banned_or_offlabel_product_mentioned:{key}")
        elif len(key) >= 6 and key not in allowed and key not in known and any(
                key.endswith(end) and len(key) > len(end) + 1 for end in _ENDING_KEYS if end):
            problems.append(f"unlisted_chemical_name:{key}")
    return problems

"""Text normalisation shared by the embedder, the keyword scorer and the answer validator.

English and Devanagari Hindi are handled together. Hindi spelling is normalised so that common typing variants
compare equal: nukta is dropped (ज़ -> ज, ड़ -> ड), chandrabindu becomes anusvara (गेहूँ -> गेहूं), Devanagari digits
become ASCII digits and zero-width joiners are removed.
"""
from __future__ import annotations

import re
import unicodedata

# Word characters are Unicode letters/digits plus the whole Devanagari block (vowel signs are combining marks,
# which \w does not match), minus the danda punctuation marks U+0964/U+0965.
_TOKEN_RE = re.compile(r"(?:[^\W_]|[\u0900-\u0963\u0966-\u097F])+")

_TRANSLATE: dict[int, int | str | None] = {
    0x093C: None,        # nukta
    0x0901: 0x0902,      # chandrabindu -> anusvara
    0x200B: None,        # zero-width space
    0x200C: None,        # zero-width non-joiner
    0x200D: None,        # zero-width joiner
    0xFEFF: None,
}
_TRANSLATE.update({ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")})

_ENGLISH_STOPWORDS = """
a an the and or of to in on at for from with by is are was were be been being am do does did can could should would
will shall may might must i me my mine we our you your he she it its they them their this that these those what which
who whom when where why how if then than so not no yes also very just any some about into over under up out as there
here have has had get got please tell kindly sir madam want need know help advice suggest suggestion suggestions ask
question questions give say let us one using use used much many long often without between during again always
make take put like good better right sure really too only even still already ever every each other another else more
most less lot lots thing things way ways time times now
"""

_HINDI_STOPWORDS = """
के का की में से को पर है हैं था थी थे हो होता होती होते और या कि जो यह वह ये वे इस उस इन उन एक कुछ कौन कौनसी
कौनसा कौन-सी कौन-सा क्या कैसे कब कहाँ कहां क्यों कितना कितनी कितने मैं मेरा मेरी मेरे हम आप आपका आपकी तो भी ही नहीं
न कर करें करना करता करते करती किया लिए लिये साथ तक द्वारा सकता सकते सकती चाहिए चाहिये रहा रही रहे जा जाए जाएँ
जाना लें कृपया बताइए बताएं बताएँ बताओ बताइये सी सा हूँ हूं हुआ हुई हुए वाला वाली वाले ऐसे अगर तब जब
करनी डालनी डालें डालना डालूं डालो करूं करूँ रखें रखना लगाएं लगाना देना देनी दें बार होगा होगी होंगे रहेगा रहेगी
कैसा कैसी किस किसी किन अपने अपना अपनी मुझे मुझको हमें आपको उसे इसे इसका इसकी उसका उसकी
"""


def normalize(text: str) -> str:
    """Case-fold and unify Hindi spelling variants. Idempotent."""
    return unicodedata.normalize("NFKC", text).casefold().translate(_TRANSLATE)


STOPWORDS: frozenset[str] = frozenset(
    normalize(w) for w in (_ENGLISH_STOPWORDS + " " + _HINDI_STOPWORDS).split()
)


def tokenize(text: str) -> list[str]:
    """All word tokens of `text` after normalisation (stop-words kept, no stemming)."""
    return _TOKEN_RE.findall(normalize(text))


def stem(token: str) -> str:
    """Very light English stemmer (plural and -ing/-ed endings). Non-English tokens are returned unchanged."""
    if not (token.isascii() and token.isalpha()) or len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ied") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("ed") and len(token) > 4:
        return token[:-2]
    if token.endswith(("sses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def content_terms(text: str) -> list[str]:
    """Stemmed, stop-word-free tokens in order (duplicates kept)."""
    return [stem(t) for t in tokenize(text) if t not in STOPWORDS]


def is_devanagari(ch: str) -> bool:
    return "\u0900" <= ch <= "\u097F"


def script_ratio(text: str) -> float:
    """Share of Devanagari characters among all letters (0.0 when there are no letters)."""
    letters = [c for c in text if c.isalpha() or is_devanagari(c)]
    if not letters:
        return 0.0
    return sum(1 for c in letters if is_devanagari(c)) / len(letters)

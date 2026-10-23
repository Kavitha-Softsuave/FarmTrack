"""Farmer-facing text -> SpokenOut (text plus an audio reference per language, None when there is no TTS or no audio yet)."""
from __future__ import annotations

import re
from collections.abc import Iterable

from app.api.schemas import SpokenOut
from app.domain.types import LocalizedText
from app.interfaces import AudioStore
from app.voice.spoken import spoken_out

_THIS_MEDICINE = {"en": "this medicine", "hi": "यह दवा"}
_SENTENCE_END = (".", "!", "?", "।")


def speak(audio: AudioStore | None, text: LocalizedText) -> SpokenOut:
    """A broken or missing audio store never breaks the answer: spoken_out returns the text with no audio reference."""
    return spoken_out(audio, text.en, text.hi)


def without_typed_text(text: LocalizedText, typed: Iterable[str | None]) -> LocalizedText:
    """`text` with every occurrence of what a farmer typed replaced by 'this medicine' (for texts that are going to be SPOKEN).

    Audio is generated once per distinct text and served publicly under the hash of that text, and the text-to-speech bill is
    paid per distinct text. A warning that echoes a typed medicine name ("<typed text> is banned") would therefore publish
    whatever a farmer typed there (a name, a phone number) and let a farmer choose what the voice reads out. The written
    warning on the screen keeps the typed name; only the spoken copy is cleaned.
    """
    needles = sorted({t.strip() for t in typed if t and t.strip()}, key=len, reverse=True)
    if not needles:
        return text
    return LocalizedText(en=_swap(text.en, needles, _THIS_MEDICINE["en"]), hi=_swap(text.hi, needles, _THIS_MEDICINE["hi"]))


def _swap(source: str, needles: list[str], phrase: str) -> str:
    for needle in needles:
        left = r"(?<!\w)" if needle[0].isalnum() else ""
        right = r"(?!\w)" if needle[-1].isalnum() else ""

        def replace(match: re.Match[str], current: str = source) -> str:
            before = current[: match.start()].rstrip()
            starts_sentence = not before or before.endswith(_SENTENCE_END)
            return phrase[0].upper() + phrase[1:] if starts_sentence else phrase

        source = re.sub(f"{left}{re.escape(needle)}{right}", replace, source, flags=re.IGNORECASE)
    return source

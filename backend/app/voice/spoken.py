"""SpokenOut builder: the text to speak plus an audio reference per language (None when there is no store or no TTS)."""
from __future__ import annotations

import logging

from app.api.schemas import AudioRef, SpokenOut
from app.domain.types import Lang, LocalizedText
from app.interfaces import AudioStore

logger = logging.getLogger(__name__)


def spoken_out(store: AudioStore | None, en: str, hi: str) -> SpokenOut:
    audio: dict[Lang, AudioRef | None] = {}
    pairs: tuple[tuple[Lang, str], ...] = (("hi", hi), ("en", en))
    for lang, text in pairs:
        ref = None
        if store is not None and text.strip():
            try:
                found = store.get_or_create(text, lang)
            except Exception as exc:                  # a broken cache must not break the answer; the app falls back to its own voice
                logger.warning("audio store failed for %s (%s)", lang, type(exc).__name__)
                found = None
            if found:
                ref = AudioRef(url=found[0], sha256=found[1])
        audio[lang] = ref
    return SpokenOut(text=LocalizedText(en=en, hi=hi), audio=audio)

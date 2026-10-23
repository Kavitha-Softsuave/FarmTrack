"""Factory used by app.services.container.

build_audio_store ALWAYS returns a store. When no TTS is configured its get_or_create returns None, so callers treat 'no audio'
the same way whether the store is missing or silent. The FastAPI app must serve `<storage_dir>/audio` at /audio.
"""
from __future__ import annotations

import logging

from app.config import Settings
from app.interfaces import TTSProvider
from app.voice.store import FileAudioStore
from app.voice.tts import GoogleCloudTTS, NullTTS

logger = logging.getLogger(__name__)
_warned = False


def voices_from(settings: Settings) -> dict[str, str]:
    return {"hi": settings.tts_voice_hi, "en": settings.tts_voice_en}


def build_tts(settings: Settings) -> TTSProvider:
    global _warned
    if settings.tts_provider == "google":
        if settings.google_tts_configured and settings.google_tts_api_key:
            return GoogleCloudTTS(settings.google_tts_api_key, voices_from(settings))
        if not _warned:
            _warned = True
            logger.warning("TTS_PROVIDER=google but GOOGLE_TTS_API_KEY is not set: no audio will be generated")
    return NullTTS()


def build_audio_store(settings: Settings) -> FileAudioStore:
    tts = build_tts(settings)
    return FileAudioStore(settings.storage_dir, tts, voices_from(settings) if tts.name != "null" else {})

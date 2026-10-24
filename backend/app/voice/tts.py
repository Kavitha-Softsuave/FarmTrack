"""Text-to-speech providers. Both return mp3 bytes, or None when no audio can be produced (the app then speaks with the
phone's own voice). The spoken text is never logged: it can contain advice for a named crop and, in future, other personal context.
"""
from __future__ import annotations

import base64
import logging
import time
from collections.abc import Callable, Mapping

import httpx

from app.domain.types import Lang

logger = logging.getLogger(__name__)

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
GOOGLE_TTS_VOICES_URL = "https://texttospeech.googleapis.com/v1/voices"
MAX_TEXT_BYTES = 4800                     # the API limit is 5000 bytes of input text
_DEFAULT_LANGUAGE_CODE: dict[str, str] = {"hi": "hi-IN", "en": "en-IN"}
_RETRY_STATUS = {429, 500, 502, 503, 504}


class NullTTS:
    name = "null"

    def synthesize(self, text: str, lang: Lang, speed: float = 0.9) -> bytes | None:
        return None


class GoogleCloudTTS:
    """Google Cloud Text-to-Speech over REST (no SDK). The API key travels in a header, never in the URL."""

    name = "google"

    def __init__(self, api_key: str, voices: Mapping[str, str], *, client: httpx.Client | None = None, timeout: float = 20.0,
                 max_retries: int = 2, sleep: Callable[[float], None] = time.sleep, url: str = GOOGLE_TTS_URL) -> None:
        self._api_key = api_key
        self._voices = dict(voices)
        self._client = client or httpx.Client(timeout=timeout)
        self._max_retries = max_retries
        self._sleep = sleep
        self._url = url

    def __repr__(self) -> str:
        return f"GoogleCloudTTS(voices={self._voices!r})"

    def voice_for(self, lang: Lang) -> str:
        return self._voices.get(lang, "")

    def build_request(self, text: str, lang: Lang, speed: float) -> dict:
        voice = self.voice_for(lang)
        language_code = "-".join(voice.split("-")[:2]) if voice.count("-") >= 2 else _DEFAULT_LANGUAGE_CODE[lang]
        audio_config: dict = {"audioEncoding": "MP3"}
        if "Chirp3-HD" not in voice:                     # Chirp 3 HD voices accept no speaking rate (and no SSML)
            audio_config["speakingRate"] = min(2.0, max(0.25, speed))
        return {"input": {"text": text}, "voice": {"languageCode": language_code, "name": voice}, "audioConfig": audio_config}

    def list_voices(self, language_code: str) -> list[str] | None:
        """Names of the voices Google offers for a language code (e.g. "hi-IN"), or None when the call failed.
        Used by `generate_prompt_audio.py --list-voices` to check that a Hindi voice really exists before generating."""
        try:
            response = self._client.get(GOOGLE_TTS_VOICES_URL, params={"languageCode": language_code},
                                        headers={"X-Goog-Api-Key": self._api_key})
        except httpx.TransportError as exc:
            logger.warning("tts: network error while listing voices (%s)", type(exc).__name__)
            return None
        if response.status_code != 200:
            logger.warning("tts: listing voices answered %s (%s)", response.status_code, self._error_status(response))
            return None
        try:
            return sorted(str(v["name"]) for v in response.json().get("voices", []) if isinstance(v, dict) and "name" in v)
        except (ValueError, AttributeError, TypeError, KeyError):
            return None

    def synthesize(self, text: str, lang: Lang, speed: float = 0.9) -> bytes | None:
        if not text.strip() or not self.voice_for(lang):
            return None
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            logger.warning("tts: text for %s is too long for one request; no audio", lang)
            return None
        body = self.build_request(text, lang, speed)
        attempt = 0
        while True:
            try:
                response = self._client.post(self._url, json=body, headers={"X-Goog-Api-Key": self._api_key})
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    logger.warning("tts: network error (%s); no audio", type(exc).__name__)
                    return None
                self._sleep(2 ** attempt)
                attempt += 1
                continue
            if response.status_code == 200:
                return self._decode(response)
            if response.status_code in _RETRY_STATUS and attempt < self._max_retries:
                self._sleep(2 ** attempt)
                attempt += 1
                continue
            logger.warning("tts: Google answered %s (%s); no audio", response.status_code, self._error_status(response))
            return None

    @staticmethod
    def _error_status(response: httpx.Response) -> str:
        try:
            return str(response.json().get("error", {}).get("status", ""))
        except (ValueError, AttributeError):
            return ""

    @staticmethod
    def _decode(response: httpx.Response) -> bytes | None:
        try:
            content = response.json().get("audioContent")
            audio = base64.b64decode(content, validate=True) if content else b""
        except (ValueError, AttributeError, TypeError):
            audio = b""
        if not audio:
            logger.warning("tts: Google returned no audio content")
            return None
        return audio

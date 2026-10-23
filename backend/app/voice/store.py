"""Content-addressed audio cache: storage_dir/audio/<sha256(text|lang|voice|speed)>.mp3, served under /audio/<name>.mp3."""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid
from collections.abc import Mapping
from pathlib import Path

from app.domain.types import Lang
from app.interfaces import TTSProvider

logger = logging.getLogger(__name__)

AUDIO_URL_PREFIX = "/audio"
_LOCK_STRIPES = 32
_REPLACE_ATTEMPTS = 5          # Windows refuses to replace a file another thread is reading at that instant


class FileAudioStore:
    def __init__(self, storage_dir: Path, tts: TTSProvider, voices: Mapping[str, str] | None = None) -> None:
        self._dir = Path(storage_dir) / "audio"
        self._tts = tts
        self._voices = dict(voices or {})
        self._locks = [threading.Lock() for _ in range(_LOCK_STRIPES)]
        self._sha_cache: dict[tuple[str, int, int], str] = {}

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def provider_name(self) -> str:
        return self._tts.name

    def cache_key(self, text: str, lang: Lang, speed: float = 0.9) -> str:
        voice = self._voices.get(lang, "")
        return hashlib.sha256(f"{text.strip()}|{lang}|{voice}|{speed:.2f}".encode()).hexdigest()

    def _sha(self, path: Path) -> str:
        stat = path.stat()
        marker = (str(path), stat.st_mtime_ns, stat.st_size)
        if marker not in self._sha_cache:
            self._sha_cache[marker] = hashlib.sha256(path.read_bytes()).hexdigest()
        return self._sha_cache[marker]

    def get_cached(self, text: str, lang: Lang, speed: float = 0.9) -> tuple[str, str] | None:
        """The cached audio for this text, or None. Never calls the TTS provider."""
        if not text.strip():
            return None
        key = self.cache_key(text, lang, speed)
        path = self._dir / f"{key}.mp3"
        try:
            return (f"{AUDIO_URL_PREFIX}/{key}.mp3", self._sha(path)) if path.is_file() else None
        except OSError:                                    # being replaced right now: treat as not cached yet
            return None

    def get_or_create(self, text: str, lang: Lang, speed: float = 0.9) -> tuple[str, str] | None:
        cached = self.get_cached(text, lang, speed)
        if cached or not text.strip():
            return cached
        key = self.cache_key(text, lang, speed)
        with self._locks[int(key[:8], 16) % _LOCK_STRIPES]:        # one synthesis per text, even under concurrent requests
            cached = self.get_cached(text, lang, speed)
            if cached:
                return cached
            audio = self._tts.synthesize(text.strip(), lang, speed)
            if not audio:
                return None
            path = self._dir / f"{key}.mp3"
            try:
                self._write_atomic(path, audio)
            except OSError as exc:                         # disk full or read-only: the app falls back to its own voice
                logger.warning("audio store: cannot write %s (%s)", path.name, type(exc).__name__)
                return None
            return f"{AUDIO_URL_PREFIX}/{key}.mp3", hashlib.sha256(audio).hexdigest()

    def _write_atomic(self, path: Path, data: bytes) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_bytes(data)
            for attempt in range(_REPLACE_ATTEMPTS):
                try:
                    os.replace(tmp, path)
                    return
                except PermissionError:
                    if attempt == _REPLACE_ATTEMPTS - 1:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        finally:
            tmp.unlink(missing_ok=True)

"""Voice prompt catalogue for GET /voice/prompts: texts from voice/prompts.json, audio from voice/audio/<lang>/<id>.mp3.

Prompt audio is served under /audio-prompts/<lang>/<id>.mp3 (a static mount of <voice_dir>/audio); synthesised advice audio is
served under /audio (see store.py). The catalogue never synthesises: generate the files with scripts/generate_prompt_audio.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path

from app.api.schemas import AudioRef, PromptOut, VoiceCatalogueOut
from app.config import Settings
from app.domain.types import Lang
from app.interfaces import AudioStore

logger = logging.getLogger(__name__)

PROMPT_AUDIO_URL_PREFIX = "/audio-prompts"
_ID_RE = re.compile(r"^[a-z0-9_]+$")
_SETTLE_NS = 3_000_000_000  # files younger than this are not cached
_sha_cache: dict[tuple[str, int, int], str] = {}


def file_sha(path: Path) -> str:
    """SHA-256 of a file, cached by (path, mtime, size).

    A file modified in the last few seconds is hashed every time and not cached: a rewrite of the same size inside
    the filesystem's timestamp resolution (coarse on Windows, FAT, network drives) would otherwise return a stale hash.
    """
    stat = path.stat()
    if time.time_ns() - stat.st_mtime_ns < _SETTLE_NS:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _sha_cache:
        _sha_cache[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _sha_cache[key]


def _missing(lang: Lang) -> VoiceCatalogueOut:
    return VoiceCatalogueOut(version="missing", language=lang, prompts=[])


def load_catalogue(settings: Settings, lang: Lang, audio_store: AudioStore | None = None) -> VoiceCatalogueOut:
    """Never raises: a missing or broken prompts file gives an empty catalogue with version 'missing'."""
    path = settings.voice_dir / "prompts.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data["prompts"]
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("voice catalogue unavailable: %s", path.name)
        return _missing(lang)
    prompts: list[PromptOut] = []
    digest = hashlib.sha256()
    for item in items if isinstance(items, list) else []:
        prompt_id, text = (item.get("id"), item.get(lang)) if isinstance(item, dict) else (None, None)
        if not isinstance(prompt_id, str) or not _ID_RE.match(prompt_id) or not isinstance(text, str) or not text.strip():
            continue
        audio = _audio_ref(settings, lang, prompt_id, text, audio_store)
        prompts.append(PromptOut(id=prompt_id, text=text, audio=audio))
        digest.update(f"{prompt_id}|{text}|{audio.sha256 if audio else ''}\n".encode())
    version = f"{data.get('version', '0')}+{digest.hexdigest()[:8]}"
    return VoiceCatalogueOut(version=version, language=lang, prompts=prompts)


def _audio_ref(settings: Settings, lang: Lang, prompt_id: str, text: str, audio_store: AudioStore | None) -> AudioRef | None:
    file = settings.voice_dir / "audio" / lang / f"{prompt_id}.mp3"
    if file.is_file():
        return AudioRef(url=f"{PROMPT_AUDIO_URL_PREFIX}/{lang}/{prompt_id}.mp3", sha256=file_sha(file))
    lookup = getattr(audio_store, "get_cached", None)       # cached advice-style audio for the same text, if any (no synthesis)
    found = lookup(text, lang) if callable(lookup) else None
    return AudioRef(url=found[0], sha256=found[1]) if found else None

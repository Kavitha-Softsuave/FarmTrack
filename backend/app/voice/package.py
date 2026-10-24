"""The voice package: the fixed-prompt audio (voice/audio/<lang>/<id>.mp3) as one unit.

`package_status` says how complete it is (admin Voice page, `generate_prompt_audio.py --status`); `build_package` zips one language
(manifest.json + <id>.mp3) for an app that wants a single download instead of one request per prompt. The version is the one of
GET /v1/voice/catalogue, so both ways of syncing agree on what is current.
"""
from __future__ import annotations

import json
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings
from app.domain.types import Lang
from app.voice.catalogue import load_catalogue
from app.voice.prompt_audio import LANGS

PACKAGE_MANIFEST = "manifest.json"


@dataclass
class LangStatus:
    lang: str
    version: str
    prompts: int = 0
    with_audio: int = 0
    audio_bytes: int = 0
    missing: list[str] = field(default_factory=list)       # prompt ids that still have no audio file


def package_status(settings: Settings) -> list[LangStatus]:
    """One row per language. Reads files only; never calls the TTS provider."""
    rows: list[LangStatus] = []
    for lang in LANGS:
        catalogue = load_catalogue(settings, lang)
        row = LangStatus(lang=lang, version=catalogue.version, prompts=len(catalogue.prompts))
        for prompt in catalogue.prompts:
            file = settings.voice_dir / "audio" / lang / f"{prompt.id}.mp3"
            if file.is_file():
                row.with_audio += 1
                row.audio_bytes += file.stat().st_size
            else:
                row.missing.append(prompt.id)
        rows.append(row)
    return rows


def build_package(settings: Settings, lang: Lang) -> Path | None:
    """A zip of the language's prompt audio in a temporary file (the caller deletes it), or None when there is no audio at all."""
    catalogue = load_catalogue(settings, lang)
    entries = []
    for prompt in catalogue.prompts:
        if prompt.audio is not None and prompt.audio.url.startswith(f"/audio-prompts/{lang}/"):
            entries.append((prompt, settings.voice_dir / "audio" / lang / f"{prompt.id}.mp3", prompt.audio.sha256))
    entries = [e for e in entries if e[1].is_file()]
    if not entries:
        return None
    handle = tempfile.NamedTemporaryFile(prefix="voice-", suffix=".zip", delete=False)  # noqa: SIM115
    handle.close()
    manifest = {"version": catalogue.version, "language": lang,
                "prompts": [{"id": p.id, "text": p.text, "file": f"{p.id}.mp3", "sha256": sha} for p, _file, sha in entries]}
    with zipfile.ZipFile(handle.name, "w", zipfile.ZIP_STORED) as archive:      # mp3 is already compressed
        archive.writestr(PACKAGE_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
        for prompt, file, _sha in entries:
            archive.write(file, f"{prompt.id}.mp3")
    return Path(handle.name)

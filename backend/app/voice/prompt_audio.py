"""Generate the audio for the fixed voice prompts (voice/prompts.json) and the native-speaker review sheet.

Used by scripts/generate_prompt_audio.py. Idempotent: a file is regenerated only when its prompt text, voice or speed changed
(tracked in voice/audio/manifest.json) or when force=True. A file with no manifest entry (for example a human recording that
was dropped in) is never overwritten unless force=True.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.types import Lang
from app.interfaces import TTSProvider

logger = logging.getLogger(__name__)

LANGS: tuple[Lang, ...] = ("hi", "en")
REVIEW_COLUMNS = ["id", "lang", "text", "audio_file", "native_speaker_ok", "corrected_text", "notes"]
MANIFEST_NAME = "manifest.json"
REVIEW_SHEET_NAME = "review_sheet.csv"


@dataclass
class GenerationSummary:
    generated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _key(text: str, lang: str, voice: str, speed: float) -> str:
    return hashlib.sha256(f"{text.strip()}|{lang}|{voice}|{speed:.2f}".encode()).hexdigest()


def load_prompts(voice_dir: Path) -> list[dict]:
    data = json.loads((voice_dir / "prompts.json").read_text(encoding="utf-8"))
    return [p for p in data["prompts"] if isinstance(p, dict) and p.get("id")]


def generate_prompt_audio(voice_dir: Path, tts: TTSProvider, voices: dict[str, str], *, speed: float = 0.9, force: bool = False,
                          langs: Iterable[Lang] = LANGS, only_ids: set[str] | None = None,
                          log: Callable[[str], None] = lambda _msg: None) -> GenerationSummary:
    prompts = load_prompts(voice_dir)
    audio_dir = voice_dir / "audio"
    manifest_path = audio_dir / MANIFEST_NAME
    manifest: dict[str, str] = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    summary = GenerationSummary()
    for prompt in prompts:
        if only_ids and prompt["id"] not in only_ids:
            continue
        for lang in langs:
            text = prompt.get(lang)
            if not isinstance(text, str) or not text.strip():
                continue
            name = f"{lang}/{prompt['id']}"
            file = audio_dir / lang / f"{prompt['id']}.mp3"
            key = _key(text, lang, voices.get(lang, ""), speed)
            if file.exists() and not force and (name not in manifest or manifest[name] == key):
                summary.skipped.append(name)
                continue
            audio = tts.synthesize(text, lang, speed)
            if not audio:
                summary.failed.append(name)
                log(f"  FAILED {name}")
                continue
            _write_atomic(file, audio)
            manifest[name] = key
            summary.generated.append(name)
            log(f"  wrote {name}")
    if summary.generated:
        _write_atomic(manifest_path, json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8"))
    write_review_sheet(voice_dir, prompts, langs)
    return summary


def _read_review_rows(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return {(row["id"], row["lang"]): row for row in csv.DictReader(handle)}


def write_review_sheet(voice_dir: Path, prompts: list[dict], langs: Iterable[Lang] = LANGS) -> Path:
    """Rewrite the sheet, keeping what the reviewer already filled in (reset if the prompt text changed after the review)."""
    path = voice_dir / REVIEW_SHEET_NAME
    previous = _read_review_rows(path)
    rows: list[dict[str, str]] = []
    for prompt in prompts:
        for lang in langs:
            text = prompt.get(lang)
            if not isinstance(text, str) or not text.strip():
                continue
            old = previous.get((prompt["id"], lang), {})
            changed = bool(old) and old.get("text") != text
            audio_file = f"audio/{lang}/{prompt['id']}.mp3"
            rows.append({
                "id": prompt["id"], "lang": lang, "text": text,
                "audio_file": audio_file if (voice_dir / audio_file).exists() else "",
                "native_speaker_ok": "" if changed else old.get("native_speaker_ok", ""),
                "corrected_text": old.get("corrected_text", ""),
                "notes": (f"TEXT CHANGED after review. {old.get('notes', '')}".strip() if changed else old.get("notes", "")),
            })
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path

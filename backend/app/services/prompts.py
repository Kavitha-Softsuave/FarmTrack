"""Fixed voice prompt texts by id (voice/prompts.json, written by the VOICE agent).

The result screens speak these prompts as the lead-in to dynamic text. If a prompt is missing the caller's fallback is used, so a
broken or old catalogue file never breaks a scan.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.domain.types import LocalizedText

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _load(voice_dir: str) -> dict[str, LocalizedText]:
    path = Path(voice_dir) / "prompts.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {p["id"]: LocalizedText(en=p.get("en", ""), hi=p.get("hi", "")) for p in raw.get("prompts", []) if "id" in p}
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("voice prompts not available at %s", path.name)
        return {}


class PromptBook:
    def __init__(self, voice_dir: Path) -> None:
        self._prompts = _load(str(voice_dir))

    def get(self, prompt_id: str, fallback: LocalizedText | None = None) -> LocalizedText:
        return self._prompts.get(prompt_id) or fallback or LocalizedText()

    def join(self, *parts: LocalizedText) -> LocalizedText:
        """Concatenate several texts into one sentence block per language, skipping empty parts."""
        return LocalizedText(en=" ".join(p.en for p in parts if p.en), hi=" ".join(p.hi for p in parts if p.hi))

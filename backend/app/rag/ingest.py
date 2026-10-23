"""Load the approved advisory notes (data/reference/advisory_notes.jsonl) and write them to a vector store.

Ingestion is idempotent: notes already stored with identical content are skipped, changed or new notes are embedded
(text_en + text_hi) and upserted. A change of embedder with unchanged text does not re-embed (drop the store instead).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.domain.types import Note
from app.interfaces import Embedder
from app.rag.store import NoteRecord, VectorStore

log = logging.getLogger(__name__)

NOTES_FILE = Path("reference") / "advisory_notes.jsonl"
GLOSSARY_FILE = Path("reference") / "hindi_glossary.json"

# Notes that steer the app itself (grounding policy, photo guidance, low-prior model labels, a US phone number that
# must never be shown): stored like every other note, but never returned to farmers or to the advice writer.
INTERNAL_TAGS = frozenset({"grounding", "photo", "gap", "lowprior"})

_BATCH = 64


def notes_path(settings: Settings) -> Path:
    return Path(settings.data_dir) / NOTES_FILE


def parse_tags(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        parts: Iterable[object] = raw.split(";")
    elif isinstance(raw, list):
        parts = raw
    else:
        parts = ()
    return tuple(t for t in (str(p).strip() for p in parts) if t)


def is_internal(tags: Iterable[str]) -> bool:
    return any(t.casefold() in INTERNAL_TAGS for t in tags)


def _record_from_row(row: dict, line_no: int) -> NoteRecord:
    note_id = str(row.get("note_id", "")).strip()
    text_en = str(row.get("text_en", "")).strip()
    topic = str(row.get("topic", "")).strip()
    if not note_id or not text_en or not topic:
        raise ValueError(f"advisory notes line {line_no}: note_id, topic and text_en are required")
    note = Note(
        note_id=note_id,
        topic=topic,
        crop=(str(row.get("crop") or "").strip() or None),
        disease_id=(str(row.get("disease_id") or "").strip() or None),
        stage=(str(row.get("stage") or "").strip() or None),
        text_en=text_en,
        text_hi=str(row.get("text_hi") or "").strip(),
        source_ref=str(row.get("source_ref") or "").strip(),
        confidence=str(row.get("confidence") or "").strip(),
    )
    return NoteRecord(note=note, tags=parse_tags(row.get("tags")))


def load_notes(path: Path) -> list[NoteRecord]:
    """Parse the JSONL file. Raises FileNotFoundError or ValueError (with the line number) on bad input."""
    records: list[NoteRecord] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"advisory notes line {line_no}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"advisory notes line {line_no}: expected a JSON object")
            rec = _record_from_row(row, line_no)
            if rec.note.note_id in seen:
                raise ValueError(f"advisory notes line {line_no}: duplicate note_id {rec.note.note_id}")
            seen.add(rec.note.note_id)
            records.append(rec)
    return records


@dataclass(frozen=True)
class Glossary:
    """Hindi names from hindi_glossary.json (draft Hindi): active ingredient and disease_id -> Hindi."""

    ingredients: dict[str, str]
    diseases: dict[str, str]


def _str_map(raw: object) -> dict[str, str]:
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def load_glossary(path: Path) -> Glossary:
    """Read the glossary; an empty Glossary when the file is missing or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Glossary(_str_map(data.get("active_ingredients")), _str_map(data.get("diseases")))
    except (OSError, ValueError, AttributeError):
        return Glossary({}, {})


def embedding_text(record: NoteRecord) -> str:
    return f"{record.note.text_en}\n{record.note.text_hi}".strip()


def ingest(store: VectorStore, embedder: Embedder, records: Sequence[NoteRecord]) -> int:
    """Upsert `records`; returns how many notes were written (0 when the store was already up to date)."""
    existing = {r.note.note_id: r for r in store.list_records()}
    pending = [r for r in records if existing.get(r.note.note_id) != r]
    for start in range(0, len(pending), _BATCH):
        batch = pending[start:start + _BATCH]
        vectors = embedder.embed([embedding_text(r) for r in batch])
        store.upsert(batch, vectors)
    if pending:
        log.info("knowledge base: %d of %d notes written", len(pending), len(records))
    return len(pending)

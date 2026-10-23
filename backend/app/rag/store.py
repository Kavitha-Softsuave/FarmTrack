"""Vector stores for the approved-notes knowledge base.

`InMemoryVectorStore` keeps everything in process memory (nothing persisted); `PgVectorStore` keeps the notes in a
PostgreSQL table `kb_notes` with a pgvector column. Both expose the same small interface (`VectorStore`).
Similarity is cosine; vectors passed in are expected to be L2-normalised (all embedders in this package are).
"""
from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.domain.types import Note

TABLE = "kb_notes"
_TAG_SEP = ";"


@dataclass(frozen=True)
class NoteRecord:
    """A note plus its tags (tags are not part of the shared `Note` contract)."""

    note: Note
    tags: tuple[str, ...] = ()


class VectorStore(Protocol):
    dim: int

    def upsert(self, records: Sequence[NoteRecord], vectors: Sequence[Sequence[float]]) -> None:
        """Insert or replace notes by note_id. Idempotent."""
        ...

    def count(self) -> int: ...

    def list_records(self) -> list[NoteRecord]:
        """Every stored note (without vectors), ordered by note_id."""
        ...

    def similar(self, vector: Sequence[float], k: int | None = None,
                crops: Sequence[str] | None = None) -> list[tuple[str, float]]:
        """(note_id, cosine) best first, ties by note_id. `crops` keeps only notes of those crops plus crop-less
        notes (case-insensitive); None keeps everything. k None returns all matches."""
        ...


def _crop_filter(crops: Sequence[str] | None) -> set[str] | None:
    return None if crops is None else {c.casefold() for c in crops}


class InMemoryVectorStore:
    """numpy cosine store. Thread-safe; persists nothing."""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._records: dict[str, NoteRecord] = {}
        self._vectors: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()
        self._ids: list[str] = []
        self._matrix: np.ndarray = np.zeros((0, dim), dtype=np.float32)
        self._dirty = False

    def upsert(self, records: Sequence[NoteRecord], vectors: Sequence[Sequence[float]]) -> None:
        if len(records) != len(vectors):
            raise ValueError("records and vectors must have the same length")
        arrays = []
        for vec in vectors:
            arr = np.asarray(vec, dtype=np.float32)
            if arr.shape != (self.dim,):
                raise ValueError(f"vector has dimension {arr.shape}, expected ({self.dim},)")
            arrays.append(arr)
        with self._lock:
            for rec, arr in zip(records, arrays, strict=True):
                self._records[rec.note.note_id] = rec
                self._vectors[rec.note.note_id] = arr
            self._dirty = True

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def list_records(self) -> list[NoteRecord]:
        with self._lock:
            return [self._records[i] for i in sorted(self._records)]

    def similar(self, vector: Sequence[float], k: int | None = None,
                crops: Sequence[str] | None = None) -> list[tuple[str, float]]:
        q = np.asarray(vector, dtype=np.float32)
        if q.shape != (self.dim,):
            raise ValueError(f"query vector has dimension {q.shape}, expected ({self.dim},)")
        wanted = _crop_filter(crops)
        with self._lock:
            if self._dirty:
                self._ids = sorted(self._vectors)
                self._matrix = np.stack([self._vectors[i] for i in self._ids]) if self._ids else np.zeros((0, self.dim), np.float32)
                self._dirty = False
            ids, matrix = self._ids, self._matrix
            crops_of = {i: (self._records[i].note.crop or "").casefold() for i in ids}
        if not ids:
            return []
        sims = matrix @ q
        scored = [
            (i, float(s)) for i, s in zip(ids, sims, strict=True)
            if wanted is None or not crops_of[i] or crops_of[i] in wanted
        ]
        scored.sort(key=lambda p: (-p[1], p[0]))
        return scored if k is None else scored[: max(0, k)]


def _vector_literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in vec) + "]"


class PgVectorStore:
    """PostgreSQL + pgvector store. Raw SQL through a SQLAlchemy engine; the schema is created on first use.

    Vectors travel as text literals cast to `vector`, so only the PostgreSQL `vector` extension is needed (no client
    library registration). The table is scanned exactly (no ANN index): the note set is small (hundreds of rows).
    Changing the embedding dimension requires dropping `kb_notes`.
    """

    def __init__(self, engine: Engine, dim: int) -> None:
        if engine.dialect.name != "postgresql":
            raise ValueError("PgVectorStore needs a PostgreSQL engine")
        if not 1 <= int(dim) <= 16000:
            raise ValueError("dim out of range for pgvector")
        self._engine = engine
        self.dim = int(dim)
        self._ready = False
        self._lock = threading.Lock()

    def ensure_schema(self) -> None:
        with self._lock:
            if self._ready:
                return
            with self._engine.begin() as conn:
                has_ext = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first()
                if not has_ext:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text(
                    f"CREATE TABLE IF NOT EXISTS {TABLE} ("
                    "note_id text PRIMARY KEY, crop text NOT NULL DEFAULT '', disease_id text NOT NULL DEFAULT '', "
                    "stage text NOT NULL DEFAULT '', topic text NOT NULL DEFAULT '', tags text NOT NULL DEFAULT '', "
                    "text_en text NOT NULL DEFAULT '', text_hi text NOT NULL DEFAULT '', "
                    "source_ref text NOT NULL DEFAULT '', confidence text NOT NULL DEFAULT '', "
                    f"embedding vector({self.dim}))"
                ))
            self._ready = True

    def upsert(self, records: Sequence[NoteRecord], vectors: Sequence[Sequence[float]]) -> None:
        if len(records) != len(vectors):
            raise ValueError("records and vectors must have the same length")
        if not records:
            return
        for vec in vectors:
            if len(vec) != self.dim:
                raise ValueError(f"vector has dimension {len(vec)}, expected {self.dim}")
        self.ensure_schema()
        rows = [
            {
                "note_id": r.note.note_id, "crop": r.note.crop or "", "disease_id": r.note.disease_id or "",
                "stage": r.note.stage or "", "topic": r.note.topic, "tags": _TAG_SEP.join(r.tags),
                "text_en": r.note.text_en, "text_hi": r.note.text_hi, "source_ref": r.note.source_ref,
                "confidence": r.note.confidence, "embedding": _vector_literal(v),
            }
            for r, v in zip(records, vectors, strict=True)
        ]
        with self._engine.begin() as conn:
            conn.execute(text(
                f"INSERT INTO {TABLE} (note_id, crop, disease_id, stage, topic, tags, text_en, text_hi, source_ref, "  # noqa: S608
                "confidence, embedding) VALUES (:note_id, :crop, :disease_id, :stage, :topic, :tags, :text_en, "
                ":text_hi, :source_ref, :confidence, CAST(:embedding AS vector)) "
                "ON CONFLICT (note_id) DO UPDATE SET crop = EXCLUDED.crop, disease_id = EXCLUDED.disease_id, "
                "stage = EXCLUDED.stage, topic = EXCLUDED.topic, tags = EXCLUDED.tags, text_en = EXCLUDED.text_en, "
                "text_hi = EXCLUDED.text_hi, source_ref = EXCLUDED.source_ref, confidence = EXCLUDED.confidence, "
                "embedding = EXCLUDED.embedding"
            ), rows)

    def count(self) -> int:
        self.ensure_schema()
        with self._engine.connect() as conn:
            return int(conn.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar_one())  # noqa: S608

    def list_records(self) -> list[NoteRecord]:
        self.ensure_schema()
        with self._engine.connect() as conn:
            rows = conn.execute(text(
                f"SELECT note_id, crop, disease_id, stage, topic, tags, text_en, text_hi, source_ref, confidence "  # noqa: S608
                f"FROM {TABLE} ORDER BY note_id"
            )).mappings().all()
        return [
            NoteRecord(
                note=Note(
                    note_id=r["note_id"], topic=r["topic"], crop=r["crop"] or None, disease_id=r["disease_id"] or None,
                    stage=r["stage"] or None, text_en=r["text_en"], text_hi=r["text_hi"],
                    source_ref=r["source_ref"], confidence=r["confidence"],
                ),
                tags=tuple(t for t in r["tags"].split(_TAG_SEP) if t),
            )
            for r in rows
        ]

    def similar(self, vector: Sequence[float], k: int | None = None,
                crops: Sequence[str] | None = None) -> list[tuple[str, float]]:
        if len(vector) != self.dim:
            raise ValueError(f"query vector has dimension {len(vector)}, expected {self.dim}")
        self.ensure_schema()
        params: dict[str, object] = {"q": _vector_literal(vector)}
        where = ""
        wanted = _crop_filter(crops)
        if wanted is not None:
            names = []
            for n, crop in enumerate(sorted(wanted)):
                params[f"c{n}"] = crop
                names.append(f":c{n}")
            where = "WHERE crop = '' OR lower(crop) IN (" + ", ".join(names) + ")" if names else "WHERE crop = ''"
        limit = ""
        if k is not None:
            params["k"] = max(0, int(k))
            limit = " LIMIT :k"
        sql = (
            "SELECT note_id, 1 - (embedding <=> CAST(:q AS vector)) AS score "  # noqa: S608
            f"FROM {TABLE} {where} ORDER BY embedding <=> CAST(:q AS vector), note_id{limit}"
        )
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).all()
        return [(str(r[0]), float(r[1])) for r in rows]

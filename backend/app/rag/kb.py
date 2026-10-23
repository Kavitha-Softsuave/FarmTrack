"""RagKnowledgeBase: approved-notes retrieval for the advice writer (`notes_for`) and for farmer questions (`search`).

Ranking choices (see docs/design-notes/rag.md):
- Structured filters decide WHAT may be returned; semantic ranking only orders and fills.
- A note whose crop differs from the requested crop is never returned (crop-less general notes may be).
- `product_use` notes are returned by `notes_for` only for the product ids the rules engine chose, never as "similar
  products" (the rules decide what may be recommended).
- Notes tagged INTERNAL_TAGS are never returned.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter, OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.domain.types import Note
from app.interfaces import Embedder
from app.rag.ingest import ingest, is_internal
from app.rag.lexicon import PRODUCT_NOTE_CONCEPTS, alias_group
from app.rag.store import NoteRecord, VectorStore
from app.rag.text import content_terms, normalize

log = logging.getLogger(__name__)

DEFAULT_K = 6
VECTOR_WEIGHT = 0.4
KEYWORD_WEIGHT = 0.6
MAX_QUERY_CHARS = 500
VECTOR_FLOOR = 0.15           # cosines below this are noise (hash collisions, unrelated text) and count as 0
_BM25_K1 = 1.2
_BM25_B = 0.75
MIN_GENERAL_RULES = 2        # slots kept for general rules whenever k allows (k // 3, at most this many)
FILL_MIN_SCORE = 0.12        # semantic fill never adds a note scoring below this
_QUERY_CACHE = 256

# general rules that apply to every spray recommendation, in the order they are added (first group first)
_GENERAL_RULE_TAGS: tuple[tuple[str, ...], ...] = (
    ("safety",),
    ("waiting_period",),
    ("rotation",),
    ("rain", "respray", "rainfast"),
    ("mixing",),
    ("brands",),
    ("proposed_ban", "banned", "offlabel", "antibiotic", "policy", "expert_referral"),
)
_RULE_PRIORITY = {tag: i for i, group in enumerate(_GENERAL_RULE_TAGS) for tag in group}

# product names that are also ordinary English words: not used to police answers
_COMMON_WORD_BRANDS = frozenset({
    "alert", "force", "glow", "index", "key", "laurel", "majestic", "maiden", "navigator", "score", "scale", "stop",
    "titan", "trust", "governor", "companion", "endurer", "magister",
})

_PRODUCT_ID_RE = re.compile(r"^P\d{2,}$", re.IGNORECASE)
_BRAND_LIST_RE = re.compile(r"Brands evaluated in the HP 2026 schedule:\s*(.*?)(?:\s+Note:|$)", re.DOTALL)
_BRAND_PAREN_RE = re.compile(r"recommends\s+[^()]+?\(([^)]+)\)\s+at\s")


@dataclass(frozen=True, eq=False)
class _Entry:
    note: Note
    tags: tuple[str, ...]
    internal: bool
    product_ids: frozenset[str]
    atoms: frozenset[str]            # active-ingredient names this note is specific to (lower case)
    tf: dict[str, int]               # stemmed content-term frequencies for keyword matching
    length: int                      # number of content terms

    @property
    def note_id(self) -> str:
        return self.note.note_id


def _atoms_of(tags: Sequence[str]) -> frozenset[str]:
    """Active-ingredient names among a note's tags ("Hexaconazole + Zineb" gives two). Product ids and the names of
    general rule topics are not ingredients."""
    atoms: set[str] = set()
    for tag in tags:
        if _PRODUCT_ID_RE.match(tag) or tag.casefold() in _RULE_PRIORITY:
            continue
        atoms.update(part.strip().casefold() for part in tag.split("+") if part.strip())
    return frozenset(atoms)


def _words(identifier: str | None) -> str:
    return (identifier or "").replace("___", " ").replace("_", " ")


def _clean_query(query: str) -> str:
    return " ".join(query.split())[:MAX_QUERY_CHARS]


def _crop_matches(entry: _Entry, crop_key: str | None) -> bool:
    """Crop-less notes always match; crop-specific notes need the same crop. crop_key None = no crop filter."""
    note_crop = (entry.note.crop or "").casefold()
    return crop_key is None or not note_crop or note_crop == crop_key


class RagKnowledgeBase:
    """Implements `app.interfaces.KnowledgeBase`. Ingests `source()` into the store on first use."""

    def __init__(self, store: VectorStore, embedder: Embedder,
                 source: Callable[[], Sequence[NoteRecord]] | None = None) -> None:
        self._store = store
        self._embedder = embedder
        self._source = source
        self._lock = threading.Lock()
        self._ready = False
        self._entries: list[_Entry] = []
        self._idf: dict[str, float] = {}
        self._max_idf = 1.0
        self._avg_length = 1.0
        self._ingredient_vocab: frozenset[str] = frozenset()
        self._product_crops: frozenset[str] = frozenset()
        self._crops: dict[str, str] = {}
        self._query_vectors: OrderedDict[str, list[float]] = OrderedDict()
        self._query_lock = threading.Lock()

    # ------------------------------------------------------------------ setup
    def _ensure_ready(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            if self._source is not None:
                ingest(self._store, self._embedder, self._source())
            self._build_index(self._store.list_records())
            self._ready = True

    def _build_index(self, records: Sequence[NoteRecord]) -> None:
        tag_atoms = {r.note.note_id: _atoms_of(r.tags) for r in records}
        vocab: set[str] = set()
        for r in records:
            if r.note.topic == "product_use":
                vocab |= tag_atoms[r.note.note_id]
        entries = []
        for r in sorted(records, key=lambda rec: rec.note.note_id):
            n = r.note
            is_product = n.topic == "product_use"
            text = " ".join([
                n.text_en, n.text_hi, " ".join(r.tags), n.crop or "", _words(n.disease_id), _words(n.stage),
            ])
            tf = Counter(content_terms(text))
            if is_product:
                tf.update(PRODUCT_NOTE_CONCEPTS)
            entries.append(_Entry(
                note=n,
                tags=r.tags,
                internal=is_internal(r.tags),
                product_ids=frozenset(t.upper() for t in r.tags if _PRODUCT_ID_RE.match(t)),
                atoms=tag_atoms[n.note_id] if is_product else tag_atoms[n.note_id] & vocab,
                tf=dict(tf),
                length=sum(tf.values()),
            ))
        df: dict[str, int] = {}
        for e in entries:
            for term in e.tf:
                df[term] = df.get(term, 0) + 1
        self._avg_length = sum(e.length for e in entries) / max(1, len(entries)) or 1.0
        total = max(1, len(entries))
        self._idf = {t: math.log(1 + (total - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self._max_idf = math.log(1 + (total + 0.5) / 0.5)
        self._entries = entries
        self._ingredient_vocab = frozenset(vocab)
        self._product_crops = frozenset((e.note.crop or "").casefold() for e in entries
                                        if e.note.topic == "product_use" and e.note.crop)
        self._crops = {e.note.crop.casefold(): e.note.crop for e in entries if e.note.crop}

    # ------------------------------------------------------------------ introspection (used by AskService)
    @property
    def size(self) -> int:
        self._ensure_ready()
        return len(self._entries)

    def has_product_notes(self, crop: str) -> bool:
        """True when approved product notes exist for `crop` (the 'no medicine advice without approved data' gate)."""
        self._ensure_ready()
        return crop.strip().casefold() in self._product_crops

    def canonical_crop(self, name: str | None) -> str | None:
        """Crop spelling used by the notes for `name` (case-insensitive), or None for a crop without any note."""
        self._ensure_ready()
        return self._crops.get((name or "").strip().casefold())

    def disease_ids(self) -> frozenset[str]:
        """Every disease or pest id the notes are tied to."""
        self._ensure_ready()
        return frozenset(e.note.disease_id for e in self._entries if e.note.disease_id)

    def product_terms(self) -> frozenset[str]:
        """Normalised product names found in the notes: active ingredients and brand names."""
        self._ensure_ready()
        names: set[str] = set(self._ingredient_vocab)
        for e in self._entries:
            if e.note.topic != "product_use":
                continue
            for m in _BRAND_LIST_RE.finditer(e.note.text_en):
                for item in m.group(1).split(";"):
                    brand = item.split(" (")[0].strip().rstrip(".").strip()
                    if brand:
                        names.add(brand.casefold())
            for m in _BRAND_PAREN_RE.finditer(e.note.text_en):
                names.add(m.group(1).strip().casefold())
        return frozenset(normalize(n) for n in names if n and n.casefold() not in _COMMON_WORD_BRANDS)

    # ------------------------------------------------------------------ scoring
    def _query_groups(self, query: str) -> list[tuple[frozenset[str], float]]:
        groups: list[tuple[frozenset[str], float]] = []
        seen: set[frozenset[str]] = set()
        for term in content_terms(query):
            group = alias_group(term)
            if group in seen:
                continue
            seen.add(group)
            # a group is as generic as its most common member that occurs in the notes; unknown terms weigh most
            weight = min((self._idf[m] for m in group if m in self._idf), default=self._max_idf)
            groups.append((group, weight))
        return groups

    def _embed_query(self, query: str) -> list[float]:
        with self._query_lock:
            cached = self._query_vectors.get(query)
            if cached is not None:
                self._query_vectors.move_to_end(query)
                return cached
        vector = self._embedder.embed([query])[0]
        with self._query_lock:
            self._query_vectors[query] = vector
            while len(self._query_vectors) > _QUERY_CACHE:
                self._query_vectors.popitem(last=False)
        return vector

    def _vector_scores(self, query: str, crops: Sequence[str] | None) -> dict[str, float]:
        try:
            return dict(self._store.similar(self._embed_query(query), None, crops))
        except Exception:
            log.warning("vector scoring unavailable; ranking by keywords only", exc_info=True)
            return {}

    def _score(self, query: str, candidates: Sequence[_Entry], crops: Sequence[str] | None) -> dict[str, float]:
        """Hybrid score in [0, 1] per candidate: 0.4 * cosine + 0.6 * keyword score. The keyword score is the
        idf-weighted share of query terms found in the note, each term saturating BM25-style so that a short note
        that states the term beats a long note that merely contains it."""
        groups = self._query_groups(query)
        total = sum(w for _, w in groups)
        if not groups or total <= 0:
            return {e.note_id: 0.0 for e in candidates}
        cosines = self._vector_scores(query, crops)
        scores = {}
        for e in candidates:
            norm = _BM25_K1 * (1 - _BM25_B + _BM25_B * e.length / self._avg_length)
            keyword = 0.0
            for group, weight in groups:
                tf = sum(e.tf.get(m, 0) for m in group)
                if tf:
                    keyword += weight * min(1.0, tf * (_BM25_K1 + 1) / (tf + norm))
            cosine = cosines.get(e.note_id, 0.0)
            scores[e.note_id] = VECTOR_WEIGHT * (cosine if cosine >= VECTOR_FLOOR else 0.0) + KEYWORD_WEIGHT * keyword / total
        return scores

    @staticmethod
    def _with_score(entry: _Entry, score: float) -> Note:
        return entry.note.model_copy(update={"score": round(score, 4)})

    # ------------------------------------------------------------------ search
    def search(self, query: str, k: int = 5, crop: str | None = None, disease_id: str | None = None,
               stage: str | None = None) -> list[Note]:
        """Hybrid (keyword + vector) search over approved notes, best first, with `Note.score` set.

        Filters exclude notes that CONFLICT with the request (another crop, another disease, another stage); notes
        without a crop, disease or stage (or with stage 'any') stay eligible."""
        self._ensure_ready()
        query = _clean_query(query)
        if not query or k <= 0:
            return []
        crop_key = crop.strip().casefold() if crop and crop.strip() else None
        candidates = [
            e for e in self._entries
            if not e.internal and _crop_matches(e, crop_key)
            and (not disease_id or not e.note.disease_id or e.note.disease_id == disease_id)
            and (not stage or e.note.stage in (None, "any", stage))
        ]
        scores = self._score(query, candidates, [crop_key] if crop_key else None)
        ranked = sorted((e for e in candidates if scores[e.note_id] > 0), key=lambda e: (-scores[e.note_id], e.note_id))
        return [self._with_score(e, scores[e.note_id]) for e in ranked[:k]]

    # ------------------------------------------------------------------ notes for a recommendation
    def notes_for(self, crop: str, disease_id: str | None, stage: str | None, product_ids: list[str],
                  k: int = DEFAULT_K) -> list[Note]:
        """Approved notes relevant to one recommendation, at most `k`, in priority order:

        1. product notes for `product_ids` (their order);  2. rules specific to those active ingredients;
        3. notes for crop + disease + stage;  4. notes for crop + disease;  5. general rules (safety, waiting period,
        rotation, rain, mixing, brands, policy), with `min(2, k // 3)` slots always reserved;  6. semantic fill.
        """
        self._ensure_ready()
        if k <= 0:
            return []
        crop_key = (crop or "").strip().casefold()
        disease = (disease_id or "").strip() or None
        stage_key = (stage or "").strip() or None
        pool = [e for e in self._entries if not e.internal and _crop_matches(e, crop_key)]

        wanted = list(dict.fromkeys(p.strip().upper() for p in product_ids if p and p.strip()))
        by_pid: dict[str, list[_Entry]] = {}
        for e in pool:
            if e.note.topic == "product_use":
                for pid in e.product_ids:
                    by_pid.setdefault(pid, []).append(e)
        tier_products = [e for pid in wanted for e in by_pid.get(pid, [])]
        atoms: frozenset[str] = frozenset().union(*(e.atoms for e in tier_products)) if tier_products else frozenset()

        def eligible(e: _Entry) -> bool:
            if e.note.topic == "product_use":
                return False
            if e.note.topic == "rule" and e.atoms and not e.atoms & atoms:
                return False                                   # rule about an ingredient that was not recommended
            if e.note.disease_id and e.note.disease_id != disease:
                return False                                   # another disease, or no disease requested
            return stage_key is None or e.note.stage in (None, "any", stage_key)

        rest = [e for e in pool if eligible(e)]
        scores = self._score(
            " ".join(filter(None, [crop, _words(disease), _words(stage_key), *sorted(atoms)])),
            [*tier_products, *rest], [crop_key] if crop_key else None,
        )

        tier_rules = [e for e in rest if e.note.topic == "rule" and e.atoms & atoms]
        disease_notes = [e for e in rest if disease and e.note.disease_id == disease and e not in tier_rules]
        tier_stage = [e for e in disease_notes if e.note.stage and (e.note.stage == "any" or e.note.stage == stage_key)]
        tier_disease = sorted(
            (e for e in disease_notes if e not in tier_stage),
            key=lambda e: (e.note.topic != "disease_info", -scores[e.note_id], e.note_id),
        )
        general = sorted(
            (e for e in rest if e.note.topic == "rule" and not e.note.disease_id and not e.atoms
             and any(t.casefold() in _RULE_PRIORITY for t in e.tags)),
            key=lambda e: (min(_RULE_PRIORITY[t.casefold()] for t in e.tags if t.casefold() in _RULE_PRIORITY), e.note_id),
        )

        rule_slots = min(MIN_GENERAL_RULES, k // 3)
        lead = [*tier_products, *tier_rules, *tier_stage, *tier_disease]
        chosen: list[_Entry] = []

        def add(entries: Sequence[_Entry], limit: int) -> None:
            for e in entries:
                if len(chosen) >= limit:
                    return
                if e not in chosen:
                    chosen.append(e)

        add(lead, k - rule_slots)
        add(general, len(chosen) + rule_slots)
        add(lead, k)
        add(general, k)
        if len(chosen) < k:
            fill = sorted((e for e in rest if e not in chosen and scores[e.note_id] >= FILL_MIN_SCORE),
                          key=lambda e: (-scores[e.note_id], e.note_id))
            add(fill, k)
        return [self._with_score(e, scores.get(e.note_id, 0.0)) for e in chosen]

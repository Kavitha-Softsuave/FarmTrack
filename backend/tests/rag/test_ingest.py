from __future__ import annotations

import csv
import json

import pytest

from app.domain.types import Note
from app.rag.embeddings import HashEmbedder
from app.rag.factory import build_knowledge_base
from app.rag.ingest import (
    embedding_text,
    ingest,
    is_internal,
    load_glossary,
    load_notes,
    notes_path,
    parse_tags,
)
from app.rag.store import InMemoryVectorStore, NoteRecord
from tests.rag.conftest import rag_settings


@pytest.fixture(scope="module")
def records() -> list[NoteRecord]:
    return load_notes(notes_path(rag_settings()))


def test_every_note_in_the_file_is_loaded(records):
    lines = [ln for ln in notes_path(rag_settings()).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(records) == len(lines) == 186
    assert len({r.note.note_id for r in records}) == 186
    assert {r.note.topic for r in records} == {"product_use", "rule", "disease_info"}


def test_fields_are_parsed(records):
    by_id = {r.note.note_id: r for r in records}
    n1 = by_id["N001"]
    assert n1.note.crop == "Apple" and n1.note.disease_id == "Apple___Apple_scab" and n1.note.stage == "green_tip"
    assert n1.tags == ("P001", "Captan") and n1.note.confidence == "V" and "HP Dept" in n1.note.source_ref
    assert n1.note.text_hi.startswith("सेब")
    general = by_id["N128"]                                    # safety rule: no crop, disease or stage
    assert general.note.crop is None and general.note.disease_id is None and general.note.stage is None
    assert general.tags == ("safety",)
    assert by_id["N175"].note.text_hi == ""                    # some notes have no Hindi draft yet


def test_parse_tags():
    assert parse_tags("P001;Captan ; ") == ("P001", "Captan")
    assert parse_tags(["a", " b "]) == ("a", "b")
    assert parse_tags(None) == ()


def test_internal_notes_are_flagged(records):
    internal = sorted(r.note.note_id for r in records if is_internal(r.tags))
    assert internal == ["N129", "N132", "N133", "N136"]        # US poison number, photo tips, low-prior labels, grounding policy


def test_embedding_text_is_english_plus_hindi(records):
    text = embedding_text(records[0])
    assert records[0].note.text_en in text and records[0].note.text_hi in text


def test_ingest_counts_and_is_idempotent(records):
    store, embedder = InMemoryVectorStore(512), HashEmbedder()
    assert ingest(store, embedder, records) == 186
    assert store.count() == 186
    assert ingest(store, embedder, records) == 0                # nothing changed: nothing written
    assert store.count() == 186


def test_ingest_rewrites_only_changed_notes(records):
    store, embedder = InMemoryVectorStore(512), HashEmbedder()
    ingest(store, embedder, records)
    edited = list(records)
    edited[5] = NoteRecord(note=edited[5].note.model_copy(update={"text_en": "Edited text about rain."}),
                           tags=edited[5].tags)
    extra = NoteRecord(note=Note(note_id="N999", topic="rule", text_en="A brand new note."))
    assert ingest(store, embedder, [*edited, extra]) == 2
    assert store.count() == 187
    stored = {r.note.note_id: r for r in store.list_records()}
    assert stored[edited[5].note.note_id].note.text_en == "Edited text about rain."


def test_every_catalogue_disease_already_has_a_disease_note(records):
    """Why ingestion does not synthesise notes from disease_catalogue.csv: every class already has one."""
    path = rag_settings().data_dir / "reference" / "disease_catalogue.csv"
    with path.open(encoding="utf-8-sig") as fh:
        catalogue = {row["disease_id"] for row in csv.DictReader(fh)}
    covered = {r.note.disease_id for r in records if r.note.topic == "disease_info"}
    assert catalogue <= covered


def test_load_notes_reports_bad_input_with_line_numbers(tmp_path):
    good = {"note_id": "N1", "topic": "rule", "text_en": "hello", "tags": "a;b"}
    path = tmp_path / "notes.jsonl"
    path.write_text(json.dumps(good) + "\n\n{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 3: invalid JSON"):
        load_notes(path)
    path.write_text(json.dumps(good) + "\n" + json.dumps(good) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2: duplicate note_id N1"):
        load_notes(path)
    path.write_text(json.dumps({"note_id": "N2", "topic": "rule"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1: note_id, topic and text_en are required"):
        load_notes(path)
    path.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON object"):
        load_notes(path)
    with pytest.raises(FileNotFoundError):
        load_notes(tmp_path / "missing.jsonl")


def test_load_glossary(tmp_path):
    glossary = load_glossary(rag_settings().data_dir / "reference" / "hindi_glossary.json")
    assert glossary.ingredients["Mancozeb"] == "मैन्कोज़ेब"
    assert glossary.diseases["Apple___Apple_scab"].startswith("सेब का स्कैब")
    empty = load_glossary(tmp_path / "nope.json")
    assert empty.ingredients == {} and empty.diseases == {}
    (tmp_path / "bad.json").write_text("{oops", encoding="utf-8")
    assert load_glossary(tmp_path / "bad.json").diseases == {}


def test_knowledge_base_ingests_on_first_use_and_hides_internal_notes():
    kb = build_knowledge_base(rag_settings())
    assert kb._store.count() == 0                               # built lazily: nothing embedded yet
    assert kb.size == 186
    assert kb._store.count() == 186
    for query in ("poison control number first aid", "photo guidance one leaf in daylight",
                  "if retrieval finds no supporting note answer I do not have approved advice"):
        assert not {"N129", "N132", "N133", "N136"} & {n.note_id for n in kb.search(query, k=20)}


def test_knowledge_base_can_be_built_from_a_custom_data_dir(tmp_path):
    notes = tmp_path / "reference"
    notes.mkdir()
    (notes / "advisory_notes.jsonl").write_text(
        json.dumps({"note_id": "X1", "topic": "rule", "text_en": "Keep sprayers clean.", "tags": "safety"}) + "\n",
        encoding="utf-8")
    kb = build_knowledge_base(rag_settings(data_dir=tmp_path))
    assert kb.size == 1
    assert [n.note_id for n in kb.search("sprayers clean")] == ["X1"]

from __future__ import annotations

import pytest

from app.domain.types import Note
from app.interfaces import KnowledgeBase
from app.rag.embeddings import HashEmbedder
from app.rag.kb import RagKnowledgeBase
from app.rag.store import InMemoryVectorStore, NoteRecord

SCAB = "Apple___Apple_scab"
INTERNAL = {"N129", "N132", "N133", "N136"}


def ids(notes):
    return [n.note_id for n in notes]


def test_knowledge_base_satisfies_the_interface(kb):
    assert isinstance(kb, KnowledgeBase)


# ------------------------------------------------------------------ notes_for
def test_notes_for_apple_scab_petal_fall_with_products(kb, product_ids):
    carbendazim = product_ids("Apple", "Carbendazim")
    myclobutanil = product_ids("Apple", "Myclobutanil")
    assert myclobutanil == ["P012"]
    petal_fall = [p for p in carbendazim if p in ("P009",)]
    notes = kb.notes_for("Apple", SCAB, "petal_fall", [*petal_fall, *myclobutanil])
    got = ids(notes)
    assert got[:2] == ["N009", "N012"]                          # the requested products come first, in request order
    by_id = {n.note_id: n for n in notes}
    assert by_id["N009"].topic == "product_use" and "Carbendazim" in by_id["N009"].text_en
    assert by_id["N012"].topic == "product_use" and "Myclobutanil" in by_id["N012"].text_en
    assert "N137" in got                                        # the apple scab disease note
    assert {"N128", "N130"} <= set(got)                         # general rules: safe use, waiting period
    assert len(got) == len(set(got)) <= 6
    assert not INTERNAL & set(got)
    assert all(n.crop in (None, "Apple") for n in notes)
    assert all(n.disease_id in (None, SCAB) for n in notes)


def test_notes_for_never_returns_other_products_or_other_diseases(kb):
    notes = kb.notes_for("Apple", SCAB, "petal_fall", ["P012"], k=20)
    product_notes = [n for n in notes if n.topic == "product_use"]
    assert ids(product_notes) == ["N012"]                       # no "similar" products: rules decide what is recommended
    assert all(n.disease_id in (None, SCAB) for n in notes)     # nothing about powdery mildew, Marssonina ...
    none_requested = kb.notes_for("Apple", SCAB, "petal_fall", [], k=20)
    assert not [n for n in none_requested if n.topic == "product_use"]


def test_notes_for_never_leaks_apple_notes_into_tomato(kb, product_ids):
    for disease, stage, products in [
        ("Tomato___Early_blight", None, ["P070"]),
        ("Tomato___Late_blight", None, []),
        (None, None, []),
        ("Tomato___healthy", None, []),
    ]:
        notes = kb.notes_for("Tomato", disease, stage, products, k=30)
        assert notes, disease
        assert all(n.crop in (None, "Tomato") for n in notes), (disease, [(n.note_id, n.crop) for n in notes])
    # even an apple product id (a caller bug) must not pull in the apple product note
    assert "N012" not in ids(kb.notes_for("Tomato", "Tomato___Early_blight", None, ["P012"], k=30))
    # and the other way round
    assert all(n.crop in (None, "Apple") for n in kb.notes_for("Apple", None, None, ["P070"], k=30))


def test_notes_for_tomato_early_blight(kb):
    notes = kb.notes_for("Tomato", "Tomato___Early_blight", None, ["P070"])
    got = ids(notes)
    assert got[0] == "N069" and notes[0].topic == "product_use" and "Mancozeb" in notes[0].text_en
    assert "N154" in got                                        # early blight disease note
    assert {"N128", "N130"} <= set(got)


def test_notes_for_always_includes_general_rules(kb):
    for crop, disease, stage, products in [
        ("Apple", SCAB, "petal_fall", ["P012"]),
        ("Apple", "Apple___Marssonina_blotch", None, []),
        ("Tomato", "Tomato___Late_blight", None, ["P073", "P074"]),
        ("Maize", "Corn_(maize)___Common_rust_", None, ["P092"]),
        ("Mango", None, None, []),                              # a crop without any note: general rules only
    ]:
        notes = kb.notes_for(crop, disease, stage, products)
        general = [n for n in notes if n.topic == "rule" and n.disease_id is None]
        assert len(general) >= 2, (crop, ids(notes))
        assert {"N128", "N130"} <= set(ids(notes)), (crop, ids(notes))


def test_notes_for_unknown_crop_returns_only_general_notes(kb):
    notes = kb.notes_for("Mango", "Mango___anthracnose", None, [], k=20)
    assert notes and all(n.crop is None and n.disease_id is None for n in notes)
    assert not [n for n in notes if n.topic in ("product_use", "disease_info")]


def test_notes_for_respects_k_and_is_stable(kb):
    args = ("Apple", SCAB, "petal_fall", ["P009", "P012"])
    assert len(kb.notes_for(*args)) == 6
    assert len(kb.notes_for(*args, k=3)) == 3
    assert kb.notes_for(*args, k=0) == []
    assert ids(kb.notes_for(*args, k=10)) == ids(kb.notes_for(*args, k=10))
    small = ids(kb.notes_for(*args, k=3))
    assert small[:2] == ["N009", "N012"] and len(small) == 3
    assert ids(kb.notes_for(*args, k=2)) == ["N009", "N012"]


def test_notes_for_adds_ingredient_specific_rules_only_for_that_ingredient(kb):
    dodine = kb.notes_for("Apple", SCAB, "green_tip", ["P002"], k=8)
    assert "N100" in ids(dodine)                                # dodine: no mixing, not above 30 C
    carbendazim = kb.notes_for("Apple", SCAB, "petal_fall", ["P009"], k=20)
    assert "N100" not in ids(carbendazim)
    captan = kb.notes_for("Apple", SCAB, "green_tip", ["P001"], k=8)
    assert "N101" in ids(captan)                                # captan and oil sprays


def test_notes_for_never_returns_internal_notes(kb):
    for crop, disease in [("Apple", "Apple___Cedar_apple_rust"), ("Apple", SCAB), ("Tomato", None), ("", None)]:
        assert not INTERNAL & set(ids(kb.notes_for(crop, disease, None, [], k=50)))


def test_notes_for_scores_are_set_and_do_not_change_stored_notes(kb):
    notes = kb.notes_for("Apple", SCAB, "petal_fall", ["P012"])
    assert notes[0].note_id == "N012" and all(0.0 <= n.score <= 1.0 for n in notes) and notes[0].score > 0
    again = kb.notes_for("Apple", SCAB, "petal_fall", ["P012"])
    assert [n.score for n in again] == [n.score for n in notes]
    assert all(r.note.score == 0.0 for r in kb._store.list_records())       # copies are scored, stored notes are not


def test_notes_for_stage_conflict_is_excluded(kb):
    notes = kb.notes_for("Apple", "PEST_apple_woolly_aphid", "green_tip", [], k=20)
    assert "N108" not in ids(notes)                             # N108 is a post-harvest drench
    assert "N108" in ids(kb.notes_for("Apple", "PEST_apple_woolly_aphid", "post_harvest", [], k=20))
    assert "N108" in ids(kb.notes_for("Apple", "PEST_apple_woolly_aphid", None, [], k=20))


# ------------------------------------------------------------------ search
def test_search_finds_the_rain_rule(kb):
    assert "N097" in ids(kb.search("rain after spray", k=5))
    assert ids(kb.search("heavy rain after spraying what to do", k=3))[0] == "N097"
    top = kb.search("repeat the spray after heavy rain", k=1)[0]
    assert top.note_id == "N097" and "7 days" in top.text_en


def test_search_finds_hindi_text(kb):
    hits = kb.search("भारी बारिश के बाद क्या करें", k=3)
    assert hits[0].note_id == "N097"
    assert "बारिश" in hits[0].text_hi
    scab = kb.search("सेब में स्कैब की दवा", k=5, crop="Apple")
    assert scab and all(n.crop == "Apple" for n in scab)
    assert any(n.disease_id == SCAB and "स्कैब" in n.text_hi for n in scab)


def test_search_keyword_boost_finds_a_named_product(kb):
    assert kb.search("Myclobutanil", k=1)[0].note_id == "N012"
    assert kb.search("myclobutanil dose", k=3)[0].note_id == "N012"
    assert kb.search("Systhane", k=3)[0].note_id == "N012"      # a brand name from the HP evaluated list


def test_search_crop_filter_excludes_other_crops_but_keeps_general_notes(kb):
    hits = kb.search("late blight", k=15, crop="Tomato")
    assert hits and all(n.crop in (None, "Tomato") for n in hits)
    assert not [n for n in hits if n.crop == "Potato"]
    assert any(n.crop is None for n in kb.search("safety gloves goggles", k=5, crop="Tomato"))
    potato = kb.search("late blight", k=15, crop="potato")      # case-insensitive
    assert potato and all(n.crop in (None, "Potato") for n in potato)
    assert any(n.crop == "Tomato" for n in kb.search("late blight", k=15))      # unfiltered search spans crops


def test_search_disease_and_stage_filters_exclude_conflicts(kb):
    hits = kb.search("recommended spray", k=40, crop="Apple", disease_id=SCAB, stage="petal_fall")
    assert hits
    assert all(n.disease_id in (None, SCAB) for n in hits)
    assert all(n.stage in (None, "any", "petal_fall") for n in hits)
    assert any(n.topic == "product_use" and n.stage == "petal_fall" for n in hits)


def test_search_scores_are_sorted_bounded_and_internal_notes_hidden(kb):
    hits = kb.search("spray", k=50)
    scores = [n.score for n in hits]
    assert scores == sorted(scores, reverse=True) and all(0.0 < s <= 1.0 for s in scores)
    assert not INTERNAL & set(ids(hits))
    assert len(kb.search("spray", k=3)) == 3


@pytest.mark.parametrize("query", ["", "   ", "the of and", "zzzqqq xyzzy"])
def test_search_returns_nothing_for_empty_or_unknown_queries(kb, query):
    assert kb.search(query) == []


def test_search_with_k_zero_or_huge_query(kb):
    assert kb.search("rain", k=0) == []
    assert kb.search("rain " * 2000, k=2)                        # long input is truncated, not rejected


def test_search_falls_back_to_keywords_when_the_embedder_fails():
    class Broken(HashEmbedder):
        def embed(self, texts):
            if len(texts) == 1:                                  # queries fail; note ingestion (batches) works
                raise RuntimeError("embedding service down")
            return super().embed(texts)

    notes = [
        NoteRecord(note=Note(note_id="A", topic="rule", text_en="Keep sprayers clean after use.")),
        NoteRecord(note=Note(note_id="B", topic="rule", text_en="Heavy rain washes the spray off the leaves.")),
    ]
    store, embedder = InMemoryVectorStore(512), Broken()
    store.upsert(notes, embedder.embed(["a", "b"]))
    kb = RagKnowledgeBase(store, embedder)
    hits = kb.search("rain washes spray")
    assert [n.note_id for n in hits] == ["B"] and hits[0].score > 0


def test_knowledge_base_over_a_prefilled_store_needs_no_source():
    notes = [NoteRecord(note=Note(note_id="A", topic="rule", text_en="Keep sprayers clean."), tags=("safety",))]
    embedder = HashEmbedder()
    store = InMemoryVectorStore(embedder.dim)
    store.upsert(notes, embedder.embed(["Keep sprayers clean."]))
    kb = RagKnowledgeBase(store, embedder)
    assert kb.size == 1 and ids(kb.notes_for("Apple", None, None, [])) == ["A"]


# ------------------------------------------------------------------ helpers used by the ask service
def test_introspection_helpers(kb):
    assert kb.has_product_notes("apple") and kb.has_product_notes("Tomato") and kb.has_product_notes("Grape")
    assert not kb.has_product_notes("Cherry") and not kb.has_product_notes("Mango")
    assert kb.canonical_crop("apple") == "Apple" and kb.canonical_crop("Mango") is None
    assert SCAB in kb.disease_ids() and "Cherry_(including_sour)___healthy" in kb.disease_ids()
    terms = kb.product_terms()
    assert {"mancozeb", "captan", "dodine", "myclobutanil", "noor", "systhane", "captaf"} <= terms
    assert "score" not in terms and "stop" not in terms        # brands that are ordinary English words are left out

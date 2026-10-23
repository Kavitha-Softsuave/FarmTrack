"""Vector store contract tests. The in-memory store always runs; the PostgreSQL/pgvector store runs the same tests only
when PG_TEST_URL points at a throwaway PostgreSQL database that has (or may create) the `vector` extension, e.g.

    docker run -d -p 5433:5432 -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=kbtest pgvector/pgvector:pg16
    PG_TEST_URL=postgresql+psycopg://postgres:pw@localhost:5433/kbtest   (needs `pip install psycopg[binary]`)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from app.domain.types import Note
from app.rag import factory
from app.rag.store import InMemoryVectorStore, NoteRecord, PgVectorStore
from tests.rag.conftest import rag_settings

DIM = 8


def unit(*parts: float) -> list[float]:
    vec = [*parts] + [0.0] * (DIM - len(parts))
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


def rec(note_id: str, crop: str | None = None, tags: tuple[str, ...] = (), **fields) -> NoteRecord:
    data = {"topic": "rule", "text_en": f"text {note_id}", "text_hi": f"हिंदी {note_id}", "source_ref": "src",
            "confidence": "V", "disease_id": None, "stage": None, **fields}
    return NoteRecord(note=Note(note_id=note_id, crop=crop, **data), tags=tags)


@pytest.fixture(params=["memory", "pgvector"])
def store(request):
    if request.param == "memory":
        yield InMemoryVectorStore(DIM)
        return
    url = os.environ.get("PG_TEST_URL")
    if not url:
        pytest.skip("PG_TEST_URL not set: PgVectorStore tests need a PostgreSQL database with pgvector")
    try:
        engine = create_engine(url)
    except ImportError:
        pytest.skip("PostgreSQL driver (psycopg) is not installed")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS kb_notes"))
    yield PgVectorStore(engine, DIM)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS kb_notes"))
    engine.dispose()


def test_upsert_count_and_round_trip(store):
    assert store.count() == 0 and store.list_records() == []
    records = [
        rec("N2", "Apple", ("P001", "Captan"), topic="product_use", disease_id="Apple___Apple_scab", stage="petal_fall"),
        rec("N1"),
        rec("N3", "Tomato", ("late_blight",), text_hi=""),
    ]
    store.upsert(records, [unit(1), unit(0, 1), unit(0, 0, 1)])
    assert store.count() == 3
    listed = store.list_records()
    assert [r.note.note_id for r in listed] == ["N1", "N2", "N3"]           # ordered by note_id
    by_id = {r.note.note_id: r for r in listed}
    assert by_id["N2"] == records[0]                                         # every field survives, incl. tags
    assert by_id["N1"].note.crop is None and by_id["N1"].note.stage is None and by_id["N1"].tags == ()
    assert by_id["N3"].note.text_hi == ""


def test_upsert_is_idempotent_and_replaces(store):
    store.upsert([rec("N1", "Apple"), rec("N2")], [unit(1), unit(0, 1)])
    store.upsert([rec("N1", "Apple"), rec("N2")], [unit(1), unit(0, 1)])
    assert store.count() == 2
    store.upsert([rec("N1", "Potato", text_en="changed")], [unit(0, 0, 1)])
    assert store.count() == 2
    changed = next(r for r in store.list_records() if r.note.note_id == "N1")
    assert changed.note.crop == "Potato" and changed.note.text_en == "changed"
    assert store.similar(unit(0, 0, 1), k=1)[0][0] == "N1"                   # the vector was replaced too


def test_similar_orders_by_cosine_with_deterministic_ties(store):
    store.upsert(
        [rec("A"), rec("B"), rec("C"), rec("D")],
        [unit(1, 0), unit(1, 1), unit(0, 1), unit(1, 1)],
    )
    result = store.similar(unit(1, 0.2))
    assert [i for i, _ in result] == ["A", "B", "D", "C"]                     # B and D tie: note_id breaks the tie
    scores = [s for _, s in result]
    assert scores == sorted(scores, reverse=True)
    assert result[0][1] == pytest.approx(0.9806, abs=1e-3)                    # cos(unit(1,.2), unit(1,0))
    assert len(store.similar(unit(1, 0), k=2)) == 2
    assert store.similar(unit(1, 0), k=0) == []


def test_similar_crop_filter_keeps_cropless_notes(store):
    store.upsert(
        [rec("APPLE", "Apple"), rec("TOMATO", "Tomato"), rec("GENERAL"), rec("MAIZE", "Maize")],
        [unit(1), unit(1), unit(1), unit(1)],
    )
    assert [i for i, _ in store.similar(unit(1), crops=["apple"])] == ["APPLE", "GENERAL"]      # case-insensitive
    assert [i for i, _ in store.similar(unit(1), crops=["Tomato", "Maize"])] == ["GENERAL", "MAIZE", "TOMATO"]
    assert [i for i, _ in store.similar(unit(1), crops=[])] == ["GENERAL"]
    assert len(store.similar(unit(1), crops=None)) == 4
    assert len(store.similar(unit(1), k=1, crops=["Apple"])) == 1


def test_similar_on_empty_store(store):
    assert store.similar(unit(1)) == []


def test_dimension_and_length_mismatches_raise(store):
    with pytest.raises(ValueError):
        store.upsert([rec("N1")], [[1.0, 0.0]])
    with pytest.raises(ValueError):
        store.upsert([rec("N1"), rec("N2")], [unit(1)])
    store.upsert([rec("N1")], [unit(1)])
    with pytest.raises(ValueError):
        store.similar([1.0, 0.0])
    assert store.count() == 1


# ------------------------------------------------------------------ PgVectorStore without a database
class _Result:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._rows[0][0]


class RecordingEngine:
    """Records the SQL PgVectorStore sends; stands in for a PostgreSQL engine (no server needed)."""

    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, rows=()):
        self.statements: list[tuple[str, object]] = []
        self.rows = list(rows)

    @contextmanager
    def begin(self):
        yield SimpleNamespace(execute=self._execute)

    connect = begin

    def _execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        return _Result([] if "pg_extension" in sql else self.rows)


def test_pgvector_store_creates_schema_once_and_upserts_with_vector_literals():
    engine = RecordingEngine()
    store = PgVectorStore(engine, DIM)                        # nothing is sent until first use
    assert engine.statements == []
    store.upsert([rec("N1", "Apple", ("P001",))], [unit(1, 1)])
    store.upsert([rec("N2")], [unit(0, 1)])
    sql = [s for s, _ in engine.statements]
    assert sum("CREATE TABLE IF NOT EXISTS kb_notes" in s for s in sql) == 1
    assert any("CREATE EXTENSION IF NOT EXISTS vector" in s for s in sql)
    ddl = next(s for s in sql if "CREATE TABLE" in s)
    for column in ("note_id text PRIMARY KEY", "crop text", "disease_id text", "stage text", "topic text", "tags text",
                   "text_en text", "text_hi text", "source_ref text", "confidence text", f"embedding vector({DIM})"):
        assert column in ddl
    insert_sql, rows = next((s, p) for s, p in engine.statements if s.startswith("INSERT INTO kb_notes"))
    assert "ON CONFLICT (note_id) DO UPDATE" in insert_sql and "CAST(:embedding AS vector)" in insert_sql
    assert rows[0]["embedding"].startswith("[") and rows[0]["embedding"].count(",") == DIM - 1
    assert rows[0]["tags"] == "P001" and rows[0]["crop"] == "Apple" and rows[0]["stage"] == ""


def test_pgvector_store_similarity_sql_filters_by_crop_with_bound_parameters():
    engine = RecordingEngine(rows=[("N2", 0.9), ("N1", 0.5)])
    store = PgVectorStore(engine, DIM)
    result = store.similar(unit(1), k=5, crops=["Apple", "o'; DROP TABLE kb_notes; --"])
    assert result == [("N2", 0.9), ("N1", 0.5)]
    sql, params = engine.statements[-1]
    assert "<=>" in sql and "LIMIT :k" in sql and "ORDER BY" in sql
    assert "crop = ''" in sql and "lower(crop) IN (:c0, :c1)" in sql
    assert "DROP TABLE" not in sql                                            # values travel as parameters only
    assert params["k"] == 5 and {params["c0"], params["c1"]} == {"apple", "o'; drop table kb_notes; --"}
    store.similar(unit(1))
    sql, params = engine.statements[-1]
    assert "WHERE" not in sql and "LIMIT" not in sql and set(params) == {"q"}


def test_pgvector_store_needs_a_postgresql_engine():
    with pytest.raises(ValueError):
        PgVectorStore(create_engine("sqlite://"), DIM)


# ------------------------------------------------------------------ factory
def test_build_vector_store_defaults_to_memory():
    assert isinstance(factory.build_vector_store(rag_settings(), 512), InMemoryVectorStore)


def test_pgvector_requires_a_postgresql_database():
    settings = rag_settings(vector_store="pgvector", database_url="sqlite:///x.db")
    assert isinstance(factory.build_vector_store(settings, 512), InMemoryVectorStore)


def test_pgvector_is_used_with_a_postgresql_database(monkeypatch):
    fake_engine = MagicMock()
    fake_engine.dialect.name = "postgresql"
    monkeypatch.setattr(factory, "make_engine", lambda url: fake_engine)
    settings = rag_settings(vector_store="pgvector", database_url="postgresql+psycopg://u:p@localhost/db")
    store = factory.build_vector_store(settings, 512)
    assert isinstance(store, PgVectorStore) and store.dim == 512
    fake_engine.begin.assert_not_called()                                     # schema is created on demand

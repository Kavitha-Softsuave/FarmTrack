"""Factories for the knowledge base (contract: app/services/container.py)."""
from __future__ import annotations

import logging

from app.config import Settings
from app.db.session import make_engine
from app.rag.embeddings import build_embedder
from app.rag.ingest import load_notes, notes_path
from app.rag.kb import RagKnowledgeBase
from app.rag.store import InMemoryVectorStore, PgVectorStore, VectorStore

log = logging.getLogger(__name__)


def build_vector_store(settings: Settings, dim: int) -> VectorStore:
    """pgvector only when requested AND the database is PostgreSQL; otherwise the in-memory store."""
    if settings.vector_store == "pgvector":
        if settings.database_url.startswith("postgresql"):
            return PgVectorStore(make_engine(settings.database_url), dim)
        log.warning("vector_store=pgvector needs a PostgreSQL database_url; using the in-memory store")
    return InMemoryVectorStore(dim)


def build_knowledge_base(settings: Settings) -> RagKnowledgeBase:
    """Build the knowledge base. The approved notes are read and embedded on first use (idempotent upsert)."""
    embedder = build_embedder(settings)
    store = build_vector_store(settings, embedder.dim)
    path = notes_path(settings)
    return RagKnowledgeBase(store, embedder, source=lambda: load_notes(path))

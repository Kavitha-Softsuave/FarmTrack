"""Shared fixtures for the RAG tests: real approved notes, hash embedder, in-memory store, a scripted fake LLM."""
from __future__ import annotations

import csv
import re
from collections.abc import Callable
from typing import Any

import pytest

from app.config import Settings
from app.rag.factory import build_knowledge_base
from app.rag.kb import RagKnowledgeBase

NOTE_BLOCK = re.compile(r"^NOTE (N\d+) \(crop: ([^,]+), topic: (\w+)\)", re.MULTILINE)


def rag_settings(**overrides: Any) -> Settings:
    """Explicit settings: never reads the repo-root .env, never touches the network."""
    values: dict[str, Any] = {"embeddings_provider": "hash", "vector_store": "memory", "openai_api_key": ""}
    return Settings(_env_file=None, **{**values, **overrides})


@pytest.fixture(scope="session")
def kb() -> RagKnowledgeBase:
    return build_knowledge_base(rag_settings())


@pytest.fixture(scope="session")
def product_ids() -> Callable[[str, str], list[str]]:
    """product_ids(crop, active_ingredient) -> ids from data/reference/product_master.csv."""
    path = rag_settings().data_dir / "reference" / "product_master.csv"
    with path.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    def lookup(crop: str, active_ingredient: str) -> list[str]:
        return [r["product_id"] for r in rows if r["crop"] == crop and r["active_ingredient"] == active_ingredient]

    return lookup


class FakeLLM:
    """Scripted LLMProvider. `responder` is a dict, an Exception, or a callable(prompt) -> dict | Exception."""

    name = "fake"

    def __init__(self, responder: Any = None) -> None:
        self.responder = responder
        self.calls: list[dict[str, Any]] = []

    @property
    def called(self) -> bool:
        return bool(self.calls)

    @property
    def prompt(self) -> str:
        return self.calls[-1]["prompt"]

    def prompt_notes(self) -> list[tuple[str, str, str]]:
        """(note_id, crop, topic) of every note in the last prompt."""
        return [(m.group(1), m.group(2), m.group(3)) for m in NOTE_BLOCK.finditer(self.prompt)]

    def generate_json(self, prompt: str, schema: dict[str, Any], schema_name: str = "response",
                      images: list[bytes] | None = None) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, "schema": schema, "schema_name": schema_name})
        out = self.responder(prompt) if callable(self.responder) else self.responder
        if isinstance(out, Exception):
            raise out
        return out


def answering(answer: str, *note_ids: str) -> FakeLLM:
    return FakeLLM({"answer": answer, "used_note_ids": list(note_ids)})

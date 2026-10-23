"""Embedders. `HashEmbedder` is the offline default (deterministic, no model download); `OpenAIEmbedder` calls the
OpenAI embeddings endpoint over HTTPS. Both satisfy `app.interfaces.Embedder`.
"""
from __future__ import annotations

import hashlib
import logging
import math
import time
from collections import Counter
from collections.abc import Callable
from functools import lru_cache

import httpx
import numpy as np

from app.config import Settings
from app.interfaces import Embedder
from app.rag.text import STOPWORDS, stem, tokenize

log = logging.getLogger(__name__)

HASH_DIM = 512
_W_UNIGRAM = 1.0
_W_BIGRAM = 0.7
_W_CHAR3 = 0.3


class EmbeddingError(RuntimeError):
    """An embedding request failed. Messages never contain the text that was being embedded."""


@lru_cache(maxsize=1 << 16)
def _slot(key: str, dim: int) -> tuple[int, float]:
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    h = int.from_bytes(digest, "big")
    return h % dim, (1.0 if (h >> 63) & 1 else -1.0)


class HashEmbedder:
    """Hashing-trick embedder over word unigrams, word bigrams and character 3-grams, L2-normalised.

    Purely lexical: it matches shared words and word fragments (so spelling variants and inflections still match) but
    cannot relate English to Hindi or synonyms to each other. Works for English and Devanagari Hindi alike. Dimension 512
    by default; empty or stop-word-only text gives the zero vector.
    """

    def __init__(self, dim: int = HASH_DIM) -> None:
        if dim < 16:
            raise ValueError("dim must be at least 16")
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t).tolist() for t in texts]

    def _vector(self, text: str) -> np.ndarray:
        features: Counter[str] = Counter()
        weights: dict[str, float] = {}
        words = [t for t in tokenize(text) if t not in STOPWORDS]
        stems = [stem(w) for w in words]
        for s in stems:
            features[f"u:{s}"] += 1
            weights[f"u:{s}"] = _W_UNIGRAM
        for a, b in zip(stems, stems[1:], strict=False):
            features[f"b:{a} {b}"] += 1
            weights[f"b:{a} {b}"] = _W_BIGRAM
        for w in words:
            padded = f"#{w}#"
            for i in range(len(padded) - 2):
                key = f"c:{padded[i:i + 3]}"
                features[key] += 1
                weights[key] = _W_CHAR3
        vec = np.zeros(self.dim, dtype=np.float32)
        for key, count in features.items():
            idx, sign = _slot(key, self.dim)
            vec[idx] += sign * weights[key] * (1.0 + math.log(count))
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec


class OpenAIEmbedder:
    """OpenAI embeddings over HTTPS (httpx). Texts are never logged. Retries 429, 5xx and transport errors."""

    _KNOWN_DIMS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072, "text-embedding-ada-002": 1536}
    _MAX_CHARS = 6000

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        *,
        base_url: str = "https://api.openai.com/v1",
        batch_size: int = 64,
        max_retries: int = 3,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("an OpenAI API key is required")
        self.model = model
        self.dim = self._KNOWN_DIMS.get(model, 1536)
        self._url = base_url.rstrip("/") + "/embeddings"
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._batch = max(1, batch_size)
        self._retries = max(0, max_retries)
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleep

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = [[0.0] * self.dim for _ in texts]
        todo = [(i, t[: self._MAX_CHARS]) for i, t in enumerate(texts) if t.strip()]
        for start in range(0, len(todo), self._batch):
            chunk = todo[start:start + self._batch]
            vectors = self._request([t for _, t in chunk])
            for (i, _), vec in zip(chunk, vectors, strict=True):
                out[i] = vec
        return out

    def close(self) -> None:
        self._client.close()

    def _request(self, inputs: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": inputs, "encoding_format": "float"}
        for attempt in range(self._retries + 1):
            retryable = False
            try:
                resp = self._client.post(self._url, headers=self._headers, json=payload)
            except httpx.TransportError as exc:
                failure = f"transport error ({type(exc).__name__})"
                retryable = True
            else:
                if resp.status_code == 200:
                    return self._parse(resp, len(inputs))
                failure = f"status {resp.status_code}"
                retryable = resp.status_code == 429 or resp.status_code >= 500
            if not retryable or attempt == self._retries:
                raise EmbeddingError(f"OpenAI embeddings request failed: {failure}")
            log.warning("OpenAI embeddings request failed (%s), retrying", failure)
            self._sleep(min(0.5 * 2**attempt, 8.0))
        raise EmbeddingError("OpenAI embeddings request failed")  # pragma: no cover

    def _parse(self, resp: httpx.Response, expected: int) -> list[list[float]]:
        try:
            rows = sorted(resp.json()["data"], key=lambda r: r["index"])
            vectors = [[float(x) for x in r["embedding"]] for r in rows]
        except (ValueError, KeyError, TypeError) as exc:
            raise EmbeddingError("OpenAI embeddings response was malformed") from exc
        if len(vectors) != expected or any(len(v) != self.dim for v in vectors):
            raise EmbeddingError(f"OpenAI embeddings response has an unexpected shape (expected dimension {self.dim})")
        result = []
        for v in vectors:
            norm = math.sqrt(sum(x * x for x in v))
            result.append([x / norm for x in v] if norm > 0 else v)
        return result


def build_embedder(settings: Settings) -> Embedder:
    """OpenAI only when explicitly selected AND a real key is configured; otherwise the offline hash embedder."""
    if settings.embeddings_provider == "openai":
        if settings.openai_configured:
            return OpenAIEmbedder(str(settings.openai_api_key), settings.embeddings_model)
        log.warning("embeddings_provider=openai but no OpenAI key is configured; using the offline hash embedder")
    return HashEmbedder()


__all__ = ["HASH_DIM", "EmbeddingError", "HashEmbedder", "OpenAIEmbedder", "build_embedder"]

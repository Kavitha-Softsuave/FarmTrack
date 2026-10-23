from __future__ import annotations

import hashlib
import json
import logging

import httpx
import numpy as np
import pytest

from app.rag.embeddings import EmbeddingError, HashEmbedder, OpenAIEmbedder, build_embedder
from tests.rag.conftest import rag_settings


def cos(a: list[float], b: list[float]) -> float:
    return float(np.dot(a, b))


def test_hash_embedder_is_deterministic_and_normalised():
    e = HashEmbedder()
    text = "Apple scab at petal fall: spray mancozeb"
    first, second = e.embed([text])[0], HashEmbedder().embed([text])[0]
    assert first == second
    assert len(first) == e.dim == 512
    assert abs(float(np.linalg.norm(first)) - 1.0) < 1e-5
    # stable across processes (no use of Python's randomised hash()): pinned fingerprint of the vector
    digest = hashlib.sha256(np.round(np.array(first, dtype=np.float32), 5).tobytes()).hexdigest()[:16]
    assert digest == "f32a12edf6a10191"


def test_hash_embedder_batches_are_independent():
    e = HashEmbedder()
    vectors = e.embed(["rain after spray", "सेब का स्कैब", "rain after spray"])
    assert vectors[0] == vectors[2]
    assert vectors[0] != vectors[1]


@pytest.mark.parametrize("text", ["", "   ", "the of and"])
def test_empty_or_stopword_text_gives_zero_vector(text):
    vec = HashEmbedder().embed([text])[0]
    assert len(vec) == 512 and not any(vec)


def test_english_inflections_stay_close():
    e = HashEmbedder()
    a, b, c = e.embed(["spraying apple trees", "sprayed apples tree", "tomato virus in greenhouse"])
    assert cos(a, b) > 0.5
    assert cos(a, b) > cos(a, c) + 0.3


def test_hindi_text_is_embedded_not_dropped():
    e = HashEmbedder()
    scab, scab2, rain = e.embed(["सेब में स्कैब रोग", "सेब का स्कैब रोग की दवा", "बारिश के बाद छिड़काव"])
    assert any(scab)
    assert cos(scab, scab2) > 0.4
    assert cos(scab, scab2) > cos(scab, rain) + 0.3


def test_hindi_spelling_variants_embed_identically():
    e = HashEmbedder()
    nukta = "छिड़काव"                       # precomposed ड़
    decomposed = "छिड" + "़" + "काव"       # ड + nukta
    plain = "छिडकाव"                        # nukta dropped
    chandrabindu, anusvara = "गेहूँ की बीमारी", "गेहूं की बीमारी"
    a, b, c = e.embed([nukta, decomposed, plain])
    assert a == b == c
    x, y = e.embed([chandrabindu, anusvara])
    assert x == y


def test_mixed_hindi_english_note_matches_either_language_part():
    e = HashEmbedder()
    note, hindi_query, english_query, other = e.embed([
        "Heavy rain within 12 hours of a spray: repeat within 7 days.\nभारी बारिश होने पर 7 दिन में छिड़काव दोहराएँ",
        "भारी बारिश छिड़काव दोहराएँ", "heavy rain repeat spray", "tomato virus whitefly",
    ])
    assert cos(note, hindi_query) > cos(note, other) + 0.2
    assert cos(note, english_query) > cos(note, other) + 0.2


def test_hash_embedder_rejects_tiny_dimension():
    with pytest.raises(ValueError):
        HashEmbedder(dim=4)


# ------------------------------------------------------------------ OpenAIEmbedder (httpx.MockTransport, no network)
def make_openai(handler, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    waits: list[float] = []
    emb = OpenAIEmbedder("sk-test-key", "text-embedding-3-small", client=client, sleep=waits.append, **kwargs)
    return emb, waits


def echo_handler(requests: list[dict], dim: int = 1536, shuffle: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append({"body": body, "auth": request.headers["authorization"], "url": str(request.url)})
        rows = []
        for i, text in enumerate(body["input"]):
            vec = [0.0] * dim
            vec[len(text) % dim] = 3.0                   # not unit length on purpose: the embedder normalises
            rows.append({"index": i, "embedding": vec})
        return httpx.Response(200, json={"data": list(reversed(rows)) if shuffle else rows})
    return handler


def test_openai_embedder_batches_orders_and_normalises():
    requests: list[dict] = []
    emb, _ = make_openai(echo_handler(requests, shuffle=True), batch_size=2)
    texts = ["a" * 1, "b" * 2, "c" * 3, "d" * 4, "e" * 5]
    out = emb.embed(texts)
    assert [len(r["body"]["input"]) for r in requests] == [2, 2, 1]
    assert requests[0]["url"] == "https://api.openai.com/v1/embeddings"
    assert requests[0]["auth"] == "Bearer sk-test-key"
    assert requests[0]["body"]["model"] == "text-embedding-3-small"
    assert emb.dim == 1536 and all(len(v) == 1536 for v in out)
    for i, vec in enumerate(out):                       # response order restored, vectors unit length
        assert vec[len(texts[i]) % 1536] == pytest.approx(1.0)


def test_openai_embedder_skips_empty_texts():
    requests: list[dict] = []
    emb, _ = make_openai(echo_handler(requests))
    out = emb.embed(["", "hello", "   "])
    assert requests[0]["body"]["input"] == ["hello"]
    assert not any(out[0]) and not any(out[2]) and any(out[1])
    requests.clear()
    emb.embed(["", " "])
    assert requests == []


def test_openai_embedder_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429 if calls["n"] == 1 else 503, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0] + [0.0] * 1535}]})

    emb, waits = make_openai(handler)
    assert emb.embed(["x"])[0][0] == pytest.approx(1.0)
    assert calls["n"] == 3
    assert waits == [0.5, 1.0]


def test_openai_embedder_gives_up_after_retries():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={})

    emb, _ = make_openai(handler, max_retries=2)
    with pytest.raises(EmbeddingError, match="status 500"):
        emb.embed(["x"])
    assert calls["n"] == 3


def test_openai_embedder_does_not_retry_client_errors_and_never_leaks_text(caplog):
    secret = "farmer Ramesh Kumar phone 99999 spray question"
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": f"bad input: {secret}"}})

    emb, _ = make_openai(handler)
    with caplog.at_level(logging.DEBUG), pytest.raises(EmbeddingError) as err:
        emb.embed([secret])
    assert calls["n"] == 1
    assert secret not in str(err.value) and "Ramesh" not in str(err.value)
    assert "Ramesh" not in caplog.text and "99999" not in caplog.text


def test_openai_embedder_transport_error_is_retried_and_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    emb, waits = make_openai(handler, max_retries=1)
    with pytest.raises(EmbeddingError, match="transport error"):
        emb.embed(["x"])
    assert waits == [0.5]


@pytest.mark.parametrize("payload", [{"unexpected": 1}, {"data": [{"index": 0, "embedding": [1.0, 2.0]}]}])
def test_openai_embedder_rejects_malformed_responses(payload):
    emb, _ = make_openai(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(EmbeddingError):
        emb.embed(["x"])


def test_openai_embedder_requires_a_key():
    with pytest.raises(ValueError):
        OpenAIEmbedder("")


# ------------------------------------------------------------------ build_embedder
def test_build_embedder_defaults_to_hash():
    assert isinstance(build_embedder(rag_settings()), HashEmbedder)


def test_build_embedder_openai_only_when_selected_and_key_configured(caplog):
    # selected but no key (or a placeholder key): offline fallback
    assert isinstance(build_embedder(rag_settings(embeddings_provider="openai")), HashEmbedder)
    placeholder = rag_settings(embeddings_provider="openai", openai_api_key="your-key-here")
    assert isinstance(build_embedder(placeholder), HashEmbedder)
    # a key alone does not switch providers
    assert isinstance(build_embedder(rag_settings(openai_api_key="sk-real-looking-123")), HashEmbedder)
    chosen = build_embedder(rag_settings(embeddings_provider="openai", openai_api_key="sk-real-looking-123",
                                         embeddings_model="text-embedding-3-large"))
    assert isinstance(chosen, OpenAIEmbedder) and chosen.dim == 3072 and chosen.model == "text-embedding-3-large"

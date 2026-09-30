import json

import httpx
import pytest

from app.core import embeddings as emb
from app.core import llm
from app.core.config import get_settings


@pytest.fixture
def fake_http(monkeypatch):
    """Route every httpx.AsyncClient through a MockTransport; `.responses` is a queue of replies."""

    class Seen(list):
        responses: list = []

    seen = Seen()
    seen.responses = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return seen.responses.pop(0)

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "verify"}))

    async def no_sleep(*_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    return seen


def _reply(vectors, shuffle=False):
    rows = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
    if shuffle:
        rows.reverse()
    return httpx.Response(200, json={"data": rows})


async def test_local_runtime_gets_its_own_model_name_and_no_key(fake_http):
    fake_http.responses.append(_reply([[0.1] * 1024]))
    p = emb.OpenAICompatibleEmbeddingProvider("BAAI/bge-m3", base_url="http://localhost:11434/v1")
    vec = await p.embed_query("hello")
    assert len(vec) == 1024 and p.dimensions == 1024
    req = fake_http[0]
    assert str(req.url) == "http://localhost:11434/v1/embeddings"
    assert json.loads(req.content)["model"] == "bge-m3", "Ollama knows bge-m3 by its tag, not the HuggingFace name"
    assert "authorization" not in req.headers


async def test_hosted_endpoint_keeps_the_catalog_name_and_sends_the_key(fake_http):
    fake_http.responses.append(_reply([[0.0] * 1024]))
    p = emb.OpenAICompatibleEmbeddingProvider("BAAI/bge-m3", base_url="https://api.jina.ai/v1", api_key="jk")
    await p.embed_query("x")
    assert json.loads(fake_http[0].content)["model"] == "BAAI/bge-m3"
    assert fake_http[0].headers["authorization"] == "Bearer jk"


async def test_batches_preserve_order_even_if_the_endpoint_reorders(fake_http):
    fake_http.responses += [_reply([[1.0, 0.0], [0.0, 1.0]], shuffle=True), _reply([[0.5, 0.5]])]
    p = emb.OpenAICompatibleEmbeddingProvider("custom-model", base_url="http://x/v1", batch_size=2)
    out = await p.embed_documents(["a", "b", "c"])
    assert len(fake_http) == 2 and json.loads(fake_http[0].content)["input"] == ["a", "b"]
    assert out == [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
    assert p.dimensions == 2, "an unknown model's dimension is learned from the first response"


async def test_a_vector_of_the_wrong_size_is_rejected_before_it_is_stored(fake_http):
    fake_http.responses.append(_reply([[0.0] * 10]))
    p = emb.OpenAICompatibleEmbeddingProvider("BAAI/bge-m3", base_url="http://x/v1")  # known: 1024
    with pytest.raises(emb.EmbeddingDimensionError, match="1024"):
        await p.embed_documents(["x"])


async def test_count_mismatch_and_http_errors_are_embedding_errors(fake_http):
    fake_http.responses.append(httpx.Response(200, json={"data": []}))
    p = emb.OpenAICompatibleEmbeddingProvider("m", base_url="http://x/v1")
    with pytest.raises(emb.EmbeddingError, match="0 vectors for 1"):
        await p.embed_documents(["x"])
    fake_http.responses.append(httpx.Response(404, text="model not found"))
    with pytest.raises(emb.EmbeddingError, match="404"):
        await p.embed_query("x")


async def test_empty_input_makes_no_request(fake_http):
    p = emb.OpenAICompatibleEmbeddingProvider("m", base_url="http://x/v1")
    assert await p.embed_documents([]) == [] and not fake_http


def test_provider_selection_and_key_rules(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "embedding_provider", "openai")
    monkeypatch.setattr(s, "embedding_model", "BAAI/bge-m3")
    monkeypatch.setattr(s, "embedding_api_key", "")
    monkeypatch.setattr(s, "openai_api_key", "sk-openai")
    emb.set_embedding_provider(None)
    try:
        # OpenAI itself: the OpenAI key is used
        monkeypatch.setattr(s, "embedding_base_url", "")
        assert emb.get_embedding_provider().api_key == "sk-openai"
        # another endpoint: the OpenAI key must NOT be sent there
        monkeypatch.setattr(s, "embedding_base_url", "http://localhost:11434/v1")
        emb.set_embedding_provider(None)
        assert emb.get_embedding_provider().api_key == ""
        # nothing usable configured
        monkeypatch.setattr(s, "embedding_base_url", "")
        monkeypatch.setattr(s, "openai_api_key", "")
        emb.set_embedding_provider(None)
        with pytest.raises(emb.EmbeddingError):
            emb.get_embedding_provider()
    finally:
        emb.set_embedding_provider(None)


def test_catalog_dimensions_and_defaults():
    assert emb.known_dimension("BAAI/bge-m3") == 1024
    assert emb.known_dimension("jina-code-embeddings-1.5b") == 768
    assert emb.known_dimension("something-else") is None
    assert emb.api_model_name("something-else", "http://localhost:11434/v1") == "something-else"

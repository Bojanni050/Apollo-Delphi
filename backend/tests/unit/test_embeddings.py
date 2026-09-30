import math

import pytest

from app.core.embeddings import MockEmbeddingProvider, get_embedding_provider
from app.services.embeddings.service import EmbeddingService


@pytest.mark.asyncio
async def test_mock_embedding_deterministic_and_normalized():
    provider = MockEmbeddingProvider(dimensions=32)
    a = await provider.embed_query("project budget is 30000")
    b = await provider.embed_query("project budget is 30000")
    assert a == b
    assert len(a) == 32
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)


@pytest.mark.asyncio
async def test_embed_documents_batch():
    provider = MockEmbeddingProvider(dimensions=16)
    vecs = await provider.embed_documents(["one", "two", "three"])
    assert len(vecs) == 3
    assert all(len(v) == 16 for v in vecs)


@pytest.mark.asyncio
async def test_different_texts_differ():
    provider = MockEmbeddingProvider(dimensions=64)
    a = await provider.embed_query("alpha")
    b = await provider.embed_query("beta")
    assert a != b


def test_provider_selection():
    provider = get_embedding_provider()
    assert provider.name == "mock"


@pytest.mark.asyncio
async def test_embedding_service_wrapper():
    service = EmbeddingService(MockEmbeddingProvider(dimensions=8))
    vecs = await service.embed_documents(["x", "y"])
    q = await service.embed_query("x")
    assert len(vecs) == 2 and len(q) == 8

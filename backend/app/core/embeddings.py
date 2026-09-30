"""Replaceable embedding provider abstraction."""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from app.core.config import get_settings
from app.core.llm import LLMError


class EmbeddingProvider(ABC):
    name: str = "base"
    dimensions: int = 0

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        ...


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic hash-based embedding for tests and offline development."""

    name = "mock"

    def __init__(self, dimensions: int | None = None):
        self.dimensions = dimensions or get_settings().embedding_dimensions

    def _embed_one(self, text: str) -> list[float]:
        tokens = [t for t in text.lower().split() if t]
        vec = [0.0] * self.dimensions
        for pos, tok in enumerate(tokens):
            h = hashlib.sha256(f"{pos}:{tok}".encode()).digest()
            idx = int.from_bytes(h[:4], "big") % self.dimensions
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            vec[idx] += sign * (1.0 + (h[5] % 10) / 10.0)
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"

    def __init__(self, model: str, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": texts},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        if resp.status_code != 200:
            raise LLMError(f"Embedding provider error {resp.status_code}: {resp.text[:300]}")
        return [item["embedding"] for item in resp.json()["data"]]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]


_embedding_instance: EmbeddingProvider | None = None


def set_embedding_provider(provider: EmbeddingProvider) -> None:
    global _embedding_instance
    _embedding_instance = provider


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_instance
    if _embedding_instance is not None:
        return _embedding_instance
    settings = get_settings()
    if settings.embedding_provider == "mock":
        _embedding_instance = MockEmbeddingProvider()
    elif settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise LLMError("EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY")
        _embedding_instance = OpenAIEmbeddingProvider(settings.embedding_model, settings.openai_api_key)
    else:
        raise LLMError(f"Unknown embedding provider: {settings.embedding_provider}")
    return _embedding_instance

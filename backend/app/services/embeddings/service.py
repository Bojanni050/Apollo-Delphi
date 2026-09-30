from __future__ import annotations

from app.core.embeddings import EmbeddingProvider, get_embedding_provider


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider | None = None):
        self.provider = provider or get_embedding_provider()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self.provider.embed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        return await self.provider.embed_query(text)

    @property
    def dimensions(self) -> int:
        return getattr(self.provider, "dimensions", 0) or len(self.provider.embed_query("dimension probe") or [])

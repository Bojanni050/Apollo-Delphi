"""Embedding providers for semantic indexing.

Application code depends only on :class:`EmbeddingProvider`, never on a vendor or a model
identifier. Every stored vector records the model and dimension it was produced with
(``document_chunks.embedding_model`` / ``embedding_dim``), so changing model can never
silently mix incompatible vectors: search only compares vectors of the active model, and
chunks from another model are reported as needing a re-index.

Providers
---------
``mock``
    Deterministic, hash based, no network. Not semantic: it exists so indexing, storage and
    retrieval are fully exercisable offline and in tests.

``openai`` (any OpenAI-compatible ``/embeddings`` endpoint)
    OpenAI itself, the Jina API, a local Ollama daemon, a ``llama-server``, vLLM, ...
    The identifier sent on the wire is resolved per endpoint (see :func:`api_model_name`):
    ``BAAI/bge-m3`` is called ``bge-m3`` by Ollama and ``bge-m3-Q8_0.gguf`` by llama-server,
    and sending the wrong one yields a 404 that looks like "model not found".
"""
from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import get_settings
from app.core.llm import LLMError, _post_json
from app.core.logging import get_logger

log = get_logger(__name__)

OPENAI_BASE_URL = "https://api.openai.com/v1"


class EmbeddingError(LLMError):
    """A user-correctable embedding problem (bad configuration, endpoint error)."""


class EmbeddingDimensionError(EmbeddingError):
    """A provider returned vectors whose shape is not usable."""


#: Models this application knows how to address, keyed by the configured model name.
#:
#: ``identifiers`` is the name to put on the wire per runtime (``None`` = that runtime cannot
#: serve the model). ``downloads`` says how to fetch the weights per runtime, where the
#: runtime can fetch them at all. Sizes are deliberately absent: a wrong size is worse than
#: none, so they are resolved from the actual download (see services/model_manager.py).
#: The asymmetry is real: the code model has an official GGUF and no Ollama tag; the
#: document model has an Ollama tag and only a community GGUF.
EMBEDDING_MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "BAAI/bge-m3": {
        "label": "BAAI bge-m3",
        "role": "document",
        "dimension": 1024,
        "note": "Multilingual documentation, Markdown and ADRs.",
        "identifiers": {"ollama": "bge-m3", "llamacpp": "bge-m3-Q8_0.gguf"},
        "downloads": {
            "ollama": {"tag": "bge-m3", "official": True},
            "llamacpp": {
                "repo": "gpustack/bge-m3-GGUF",
                "filename": "bge-m3-Q8_0.gguf",
                "official": False,
                "note": "Community GGUF conversion, not published by BAAI.",
            },
        },
    },
    "jina-code-embeddings-1.5b": {
        "label": "Jina Code Embeddings 1.5B",
        "role": "code",
        "dimension": 768,
        "note": "Source code and natural-language to code retrieval.",
        "identifiers": {"ollama": None, "llamacpp": "jina-code-embeddings-1.5b-Q8_0.gguf"},
        "downloads": {
            "llamacpp": {
                "repo": "jinaai/jina-code-embeddings-1.5b-GGUF",
                "filename": "jina-code-embeddings-1.5b-Q8_0.gguf",
                "official": True,
                "note": "Official Jina GGUF (Q8_0).",
            },
        },
    },
    "text-embedding-3-small": {
        "label": "OpenAI text-embedding-3-small",
        "role": "document",
        "dimension": 1536,
        "note": "Hosted by OpenAI; nothing to download.",
        "identifiers": {"ollama": None, "llamacpp": None},
        "downloads": {},
    },
}


def is_ollama_endpoint(base_url: str | None) -> bool:
    """Whether ``base_url`` is an Ollama runtime (its OpenAI layer lives under /v1 on the same host)."""
    if not base_url:
        return False
    return "11434" in base_url or "ollama" in base_url.lower()


def is_llamacpp_endpoint(base_url: str | None) -> bool:
    """Whether ``base_url`` is a llama.cpp ``llama-server``.

    Checked only AFTER the Ollama test and deliberately not a bare "is it localhost" test:
    Ollama also listens on localhost, and that would send a llama-server name to a daemon
    that has never heard of it.
    """
    if not base_url:
        return False
    lowered = base_url.lower()
    return "llama" in lowered or ":8080" in lowered


def api_model_name(model: str, base_url: str | None = None) -> str:
    """The identifier to send to ``base_url`` for the logical model ``model``."""
    entry = EMBEDDING_MODEL_CATALOG.get(model)
    if entry is None:
        return model  # unknown models are allowed, they just get no name translation
    identifiers = entry.get("identifiers") or {}
    if is_ollama_endpoint(base_url):
        tag = identifiers.get("ollama")
        if tag:
            return tag
    elif is_llamacpp_endpoint(base_url):
        local = identifiers.get("llamacpp")
        if local:
            return local
    return model


def known_dimension(model: str) -> int | None:
    entry = EMBEDDING_MODEL_CATALOG.get(model)
    return int(entry["dimension"]) if entry else None


class EmbeddingProvider(ABC):
    name: str = "base"
    #: Logical model name recorded next to every stored vector.
    model: str = ""
    #: Known vector size, or None until a first response reveals it.
    dimensions: int | None = None

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic hash-based embedding for tests and offline development."""

    name = "mock"

    def __init__(self, dimensions: int | None = None, model: str | None = None):
        s = get_settings()
        self.dimensions = dimensions or s.embedding_dimensions
        self.model = model or s.embedding_model

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


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """An OpenAI-compatible ``/embeddings`` endpoint (hosted or local).

    ``api_key`` may be empty for local runtimes; no Authorization header is sent then.
    """

    name = "openai"

    def __init__(
        self,
        model: str,
        base_url: str = OPENAI_BASE_URL,
        api_key: str = "",
        dimensions: int | None = None,
        batch_size: int = 32,
        timeout: float = 60.0,
    ):
        self.model = model
        self.base_url = (base_url or OPENAI_BASE_URL).rstrip("/")
        self.api_key = api_key
        self.batch_size = max(1, batch_size)
        self.timeout = timeout
        self.dimensions = dimensions or known_dimension(model)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        api_model = api_model_name(self.model, self.base_url)
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            try:
                data = await _post_json(
                    f"{self.base_url}/embeddings", {"model": api_model, "input": batch}, headers, self.timeout
                )
            except LLMError as exc:
                raise EmbeddingError(f"Embedding endpoint: {exc}") from exc
            rows = data.get("data") if isinstance(data, dict) else None
            if not isinstance(rows, list) or len(rows) != len(batch):
                raise EmbeddingError(
                    f"Embedding endpoint returned {len(rows) if isinstance(rows, list) else 'no'} vectors for {len(batch)} inputs."
                )
            # `index` is the OpenAI contract for ordering; fall back to arrival order.
            if all(isinstance(r, dict) and "index" in r for r in rows):
                rows = sorted(rows, key=lambda r: r["index"])
            for row in rows:
                vector = row.get("embedding") if isinstance(row, dict) else None
                if not isinstance(vector, list) or not vector:
                    raise EmbeddingError("Embedding endpoint returned a malformed vector.")
                vectors.append([float(x) for x in vector])
        self._validate(vectors)
        return vectors

    def _validate(self, vectors: list[list[float]]) -> None:
        """Every vector must have one consistent dimension, equal to the expected one when known."""
        for index, vector in enumerate(vectors):
            if self.dimensions is None:
                self.dimensions = len(vector)  # first response defines it
            if len(vector) != self.dimensions:
                raise EmbeddingDimensionError(
                    f"Embedding {index} has dimension {len(vector)}, expected {self.dimensions} for model {self.model!r}."
                )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts) if texts else []

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]


_instance: EmbeddingProvider | None = None


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Override the provider (tests); ``None`` drops the cached one so settings are re-read."""
    global _instance
    _instance = provider


def effective_embedding_key() -> str:
    """The embedding key, or the OpenAI key but only when talking to OpenAI itself.

    The OpenAI key is never sent to another embedding endpoint.
    """
    s = get_settings()
    if s.embedding_api_key:
        return s.embedding_api_key
    return s.openai_api_key if not s.embedding_base_url else ""


def _build() -> EmbeddingProvider:
    s = get_settings()
    if s.embedding_provider == "mock":
        return MockEmbeddingProvider()
    if s.embedding_provider == "openai":
        key = effective_embedding_key()
        if not s.embedding_base_url and not key:
            raise EmbeddingError(
                "No Base URL and no API key are set for the embedding model. Enter the Base URL of your local runtime "
                "(http://localhost:8080/v1 for llama-server, http://localhost:11434/v1 for Ollama) or an OpenAI API key"
            )
        return OpenAICompatibleEmbeddingProvider(
            s.embedding_model,
            base_url=s.embedding_base_url or OPENAI_BASE_URL,
            api_key=key,
            batch_size=s.embedding_batch_size,
        )
    raise EmbeddingError(f"Unknown embedding provider: {s.embedding_provider}")


def get_embedding_provider() -> EmbeddingProvider:
    global _instance
    if _instance is None:
        _instance = _build()
    return _instance

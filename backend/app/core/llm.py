"""Provider-independent LLM abstraction.

The active provider is selected by configuration (LLM_PROVIDER / LLM_MODEL).
Every stage of the Apollo pipeline calls ``get_llm_provider()`` and receives
an object implementing :class:`LLMProvider`. Structured outputs are requested
via JSON schemas and validated by the caller with Pydantic models.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete(self, system: str, user: str, response_schema: dict[str, Any] | None = None) -> str:
        """Return the model output as a string (JSON when response_schema given)."""
        ...

    async def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        """Request structured output and validate it against a Pydantic model."""
        raw = await self.complete(system, user, response_schema=schema.model_json_schema())
        try:
            data = json.loads(self._extract_json(raw))
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM returned invalid JSON: {exc}") from exc
        return schema.model_validate(data)

    @staticmethod
    def _extract_json(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return text[start : end + 1]
        if text.startswith("[") and text.endswith("]"):
            return text
        return text


class MockLLMProvider(LLMProvider):
    """Deterministic provider used for tests and offline development.

    It inspects the prompt for stage markers and returns well-formed structured
    outputs, so the full pipeline is exercisable without external services.
    """

    name = "mock"

    async def complete(self, system: str, user: str, response_schema: dict[str, Any] | None = None) -> str:
        marker = ""
        for key in ("stage:", "STAGE:"):
            idx = (system + "\n" + user).lower().find(key)
            if idx != -1:
                marker = (system + "\n" + user)[idx : idx + 80].lower()
                break
        log.debug("MockLLM stage marker: %s", marker)
        return json.dumps({"mock": True, "marker": marker})


class OpenAICompatibleLLMProvider(LLMProvider):
    """Minimal OpenAI-chat-completions compatible client (works with many providers)."""

    name = "openai"

    def __init__(self, model: str, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def complete(self, system: str, user: str, response_schema: dict[str, Any] | None = None) -> str:
        import httpx

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0.1}
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise LLMError(f"LLM provider error {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]


_llm_instance: LLMProvider | None = None


def set_llm_provider(provider: LLMProvider) -> None:
    global _llm_instance
    _llm_instance = provider


def get_llm_provider() -> LLMProvider:
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    settings = get_settings()
    if settings.llm_provider == "mock":
        _llm_instance = MockLLMProvider()
    elif settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise LLMError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        _llm_instance = OpenAICompatibleLLMProvider(settings.llm_model, settings.openai_api_key)
    else:
        raise LLMError(f"Unknown LLM provider: {settings.llm_provider}")
    return _llm_instance

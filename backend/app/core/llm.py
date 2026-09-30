"""Provider-independent LLM abstraction.

The active provider is selected by configuration (LLM_PROVIDER / LLM_MODEL).
Every stage of the Apollo pipeline calls ``get_llm_provider()`` and receives
an object implementing :class:`LLMProvider`. Structured outputs are requested
via JSON schemas and validated by the caller with Pydantic models.
"""

from __future__ import annotations

import asyncio
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


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


async def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float, attempts: int = 2) -> dict[str, Any]:
    """POST with one retry on timeouts, connection errors, 429 and 5xx. Raises LLMError."""
    import httpx

    last: str = ""
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            last = f"timed out after {timeout:.0f}s"
        except httpx.HTTPError as exc:
            last = f"could not reach the endpoint ({exc.__class__.__name__}: {exc})"
        else:
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError as exc:
                    raise LLMError(f"LLM endpoint returned a non-JSON response: {resp.text[:200]}") from exc
            last = f"HTTP {resp.status_code}: {resp.text[:300]}"
            if not _retryable(resp.status_code):
                break
        if attempt + 1 < attempts:
            await asyncio.sleep(1.0 * (attempt + 1))
    raise LLMError(f"LLM request to {url} failed: {last}")


class OpenAICompatibleLLMProvider(LLMProvider):
    """OpenAI ``/chat/completions`` client: OpenAI itself, Ollama, LM Studio, vLLM, OpenRouter, ...

    ``api_key`` may be empty for local runtimes; no Authorization header is sent then.
    """

    name = "openai"

    def __init__(self, model: str, api_key: str = "", base_url: str = "https://api.openai.com/v1", timeout: float = 120.0):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def complete(self, system: str, user: str, response_schema: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.1,
        }
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = await _post_json(f"{self.base_url}/chat/completions", payload, headers, self.timeout)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected response shape from LLM endpoint: {str(data)[:200]}") from exc


class AnthropicLLMProvider(LLMProvider):
    """Anthropic Messages API client."""

    name = "anthropic"
    API_VERSION = "2023-06-01"

    def __init__(self, model: str, api_key: str, base_url: str = "https://api.anthropic.com/v1", timeout: float = 120.0, max_tokens: int = 4096):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens

    async def complete(self, system: str, user: str, response_schema: dict[str, Any] | None = None) -> str:
        if response_schema is not None:
            system = (
                f"{system}\n\nRespond with a single JSON object only, no prose and no code fences, "
                f"matching this JSON schema:\n{json.dumps(response_schema)}"
            )
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0.1,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": self.API_VERSION}
        data = await _post_json(f"{self.base_url}/messages", payload, headers, self.timeout)
        try:
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError, AttributeError) as exc:
            raise LLMError(f"Unexpected response shape from Anthropic: {str(data)[:200]}") from exc


#: "main" is for reasoning (investigation, generation); "background" is the cheaper
#: tier for bulk work over many documents (claim extraction, Pulse).
TIERS = ("main", "background")
_instances: dict[str, LLMProvider] = {}


def set_llm_provider(provider: LLMProvider | None) -> None:
    """Override the provider for every tier (tests); ``None`` clears all cached providers."""
    _instances.clear()
    if provider is not None:
        for tier in TIERS:
            _instances[tier] = provider


def model_for(tier: str = "main") -> str:
    s = get_settings()
    return (s.background_llm_model or s.llm_model) if tier == "background" else s.llm_model


def _build(tier: str) -> LLMProvider:
    s = get_settings()
    model = model_for(tier)
    if s.llm_provider == "mock":
        return MockLLMProvider()
    if s.llm_provider == "openai":
        if not s.llm_base_url and not s.openai_api_key:
            raise LLMError("LLM_PROVIDER=openai requires OPENAI_API_KEY (or LLM_BASE_URL for a local runtime such as Ollama)")
        kwargs = {"base_url": s.llm_base_url} if s.llm_base_url else {}
        return OpenAICompatibleLLMProvider(model, s.openai_api_key, timeout=s.llm_timeout_seconds, **kwargs)
    if s.llm_provider == "anthropic":
        if not s.anthropic_api_key:
            raise LLMError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        return AnthropicLLMProvider(model, s.anthropic_api_key, timeout=s.llm_timeout_seconds)
    raise LLMError(f"Unknown LLM provider: {s.llm_provider}")


def get_llm_provider(tier: str = "main") -> LLMProvider:
    if tier not in TIERS:
        raise ValueError(f"Unknown LLM tier: {tier}")
    if tier not in _instances:
        _instances[tier] = _build(tier)
    return _instances[tier]

"""List the models a provider offers, so the settings page can show a picker.

Most endpoints only list ids. Some (OpenRouter, EdenAI) also say what a model is: a name, a description, the context
length and what it costs per token. That is kept (prices converted to USD per 1M tokens) so the picker can show it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.llm import LLMError, http_verify

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"


#: Descriptions are cut here: the picker shows two lines and a "read more", not an essay.
MAX_DESCRIPTION = 800


@dataclass
class ModelInfo:
    id: str
    name: str | None = None
    provider: str | None = None
    description: str | None = None
    context_length: int | None = None
    #: USD per 1M tokens; None when the endpoint does not say. 0 means free.
    input_per_million: float | None = None
    output_per_million: float | None = None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None  # OpenRouter's routers report -1 for "varies"


def _per_million(price_per_token: Any) -> float | None:
    price = _number(price_per_token)
    return None if price is None else round(price * 1_000_000, 6)


def model_info(entry: dict[str, Any]) -> ModelInfo | None:
    """One entry of a /models answer as a ModelInfo (OpenAI-style, Anthropic, OpenRouter and EdenAI shapes)."""
    model_id = entry.get("id") or entry.get("name") or entry.get("model")
    if not model_id:
        return None
    model_id = str(model_id)
    name = entry.get("name") or entry.get("display_name") or entry.get("model_name")
    owner = entry.get("owned_by")
    provider = owner if owner and owner != "system" else (model_id.split("/", 1)[0] if "/" in model_id else None)
    description = str(entry.get("description") or "").strip()
    pricing = entry.get("pricing") if isinstance(entry.get("pricing"), dict) else {}
    top = entry.get("top_provider") if isinstance(entry.get("top_provider"), dict) else {}
    context = _number(entry.get("context_length") or top.get("context_length") or entry.get("max_input_tokens"))
    return ModelInfo(
        id=model_id,
        name=str(name) if name and str(name) != model_id else None,
        provider=str(provider) if provider else None,
        description=(description[:MAX_DESCRIPTION].rstrip() + "…" if len(description) > MAX_DESCRIPTION else description) or None,
        context_length=int(context) if context else None,
        input_per_million=_per_million(pricing.get("prompt", pricing.get("input_cost_per_token"))),
        output_per_million=_per_million(pricing.get("completion", pricing.get("output_cost_per_token"))),
    )


async def list_models(provider: str, base_url: str = "", api_key: str = "", timeout: float = 15.0) -> list[str]:
    return [m.id for m in await list_model_infos(provider, base_url, api_key, timeout)]


async def list_model_infos(provider: str, base_url: str = "", api_key: str = "", timeout: float = 15.0) -> list[ModelInfo]:
    if provider == "anthropic":
        url = f"{(base_url or ANTHROPIC_BASE_URL).rstrip('/')}/models?limit=100"
        if not api_key:
            raise LLMError("Enter an Anthropic API key first")
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    elif provider == "openai":
        url = f"{(base_url or OPENAI_BASE_URL).rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        if not api_key and not base_url:
            raise LLMError("Enter an API key, or a base URL for a local runtime")
    else:
        return []

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=http_verify()) as client:
            resp = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise LLMError(f"Could not reach {url}: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        raise LLMError(f"{url} answered HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        body: Any = resp.json()
    except ValueError as exc:
        raise LLMError("The endpoint returned a non-JSON response") from exc

    entries = body.get("data") if isinstance(body, dict) else body
    if not isinstance(entries, list):
        entries = []
    infos: dict[str, ModelInfo] = {}
    for entry in entries:
        info = model_info(entry) if isinstance(entry, dict) else None
        if info:
            infos.setdefault(info.id, info)
    return sorted(infos.values(), key=lambda m: m.id)

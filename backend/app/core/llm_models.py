"""List the models a provider offers, so the settings page can show a picker."""
from __future__ import annotations

from typing import Any

import httpx

from app.core.llm import LLMError

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"


async def list_models(provider: str, base_url: str = "", api_key: str = "", timeout: float = 15.0) -> list[str]:
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
        async with httpx.AsyncClient(timeout=timeout) as client:
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
    ids = {str(e.get("id") or e.get("name") or e.get("model")) for e in entries if isinstance(e, dict) and (e.get("id") or e.get("name") or e.get("model"))}
    return sorted(ids)

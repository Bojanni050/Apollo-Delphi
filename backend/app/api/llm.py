from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.config import get_settings
from app.core.llm import TIERS, LLMError, get_llm_provider, model_for
from app.core.llm_models import list_models
from app.services import llm_settings

router = APIRouter(prefix="/llm", tags=["llm"])


class TierStatus(BaseModel):
    tier: str
    provider: str
    model: str
    configured: bool
    error: str | None = None


class LLMStatus(BaseModel):
    provider: str
    base_url: str | None
    tiers: list[TierStatus]


class LLMTestResult(BaseModel):
    ok: bool
    tier: str
    model: str
    reply: str | None = None
    error: str | None = None


class LLMSettingsOut(BaseModel):
    provider: str
    model: str
    background_model: str
    base_url: str
    timeout_seconds: float
    openai_key_set: bool
    anthropic_key_set: bool


class LLMSettingsUpdate(BaseModel):
    """Every field optional: only the fields sent are changed. A key of ``""`` clears that key."""

    provider: str | None = None
    model: str | None = None
    background_model: str | None = None
    base_url: str | None = None
    timeout_seconds: float | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


class ModelList(BaseModel):
    models: list[str]
    error: str | None = None


_FIELD_MAP = {
    "provider": "llm_provider",
    "model": "llm_model",
    "background_model": "background_llm_model",
    "base_url": "llm_base_url",
    "timeout_seconds": "llm_timeout_seconds",
    "openai_api_key": "openai_api_key",
    "anthropic_api_key": "anthropic_api_key",
}


def _settings_out() -> LLMSettingsOut:
    s = get_settings()
    return LLMSettingsOut(
        provider=s.llm_provider,
        model=s.llm_model,
        background_model=s.background_llm_model,
        base_url=s.llm_base_url,
        timeout_seconds=s.llm_timeout_seconds,
        openai_key_set=bool(s.openai_api_key),
        anthropic_key_set=bool(s.anthropic_api_key),
    )


@router.get("/settings", response_model=LLMSettingsOut)
def get_llm_settings():
    """Current effective settings. API keys are never returned, only whether one is set."""
    return _settings_out()


@router.put("/settings", response_model=LLMSettingsOut)
def update_llm_settings(body: LLMSettingsUpdate, db: Session = Depends(get_session)):
    updates = {_FIELD_MAP[name]: getattr(body, name) for name in body.model_fields_set if getattr(body, name) is not None}
    try:
        llm_settings.save(db, updates)
    except llm_settings.SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _settings_out()


@router.get("/models", response_model=ModelList)
async def available_models(provider: str | None = None, base_url: str | None = None):
    """Models offered by the (saved) provider. ``provider``/``base_url`` let the page look before saving."""
    s = get_settings()
    provider = provider or s.llm_provider
    base_url = s.llm_base_url if base_url is None else base_url
    key = s.anthropic_api_key if provider == "anthropic" else s.openai_api_key
    try:
        return ModelList(models=await list_models(provider, base_url, key, timeout=min(s.llm_timeout_seconds, 15.0)))
    except LLMError as exc:
        return ModelList(models=[], error=str(exc))


@router.get("/status", response_model=LLMStatus)
def llm_status():
    """What is configured. Never contacts the provider and never returns keys."""
    s = get_settings()
    tiers = []
    for tier in TIERS:
        try:
            get_llm_provider(tier)
            tiers.append(TierStatus(tier=tier, provider=s.llm_provider, model=model_for(tier), configured=True))
        except LLMError as exc:
            tiers.append(TierStatus(tier=tier, provider=s.llm_provider, model=model_for(tier), configured=False, error=str(exc)))
    return LLMStatus(provider=s.llm_provider, base_url=s.llm_base_url or None, tiers=tiers)


@router.post("/test", response_model=LLMTestResult)
async def llm_test(tier: str = "main"):
    """One tiny round trip to prove the configured model answers."""
    if tier not in TIERS:
        tier = "main"
    model = model_for(tier)
    try:
        reply = await get_llm_provider(tier).complete("Answer with the single word: pong.", "ping")
    except LLMError as exc:
        return LLMTestResult(ok=False, tier=tier, model=model, error=str(exc))
    return LLMTestResult(ok=True, tier=tier, model=model, reply=reply.strip()[:200])

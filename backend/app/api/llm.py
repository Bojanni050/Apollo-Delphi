from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.config import get_settings
from app.core.llm import TIERS, LLMError, get_llm_provider, tier_config
from app.core.llm_models import list_model_infos
from app.services import llm_settings

router = APIRouter(prefix="/llm", tags=["llm"])


class TierStatus(BaseModel):
    tier: str
    provider: str
    model: str
    base_url: str
    configured: bool
    inherits: bool = False
    error: str | None = None


class LLMStatus(BaseModel):
    tiers: list[TierStatus]


class LLMTestResult(BaseModel):
    ok: bool
    tier: str
    model: str
    reply: str | None = None
    error: str | None = None


class TierSettings(BaseModel):
    """What was configured for one tier (``""`` on the background tier means "same as main")."""

    provider: str
    model: str
    base_url: str
    api_key_set: bool


class LLMSettingsOut(BaseModel):
    main: TierSettings
    background: TierSettings
    timeout_seconds: float


class TierUpdate(BaseModel):
    """Only the fields sent are changed. ``api_key`` of ``""`` clears the key."""

    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class LLMSettingsUpdate(BaseModel):
    main: TierUpdate | None = None
    background: TierUpdate | None = None
    timeout_seconds: float | None = None


class ModelInfoOut(BaseModel):
    id: str
    name: str | None = None
    provider: str | None = None
    description: str | None = None
    context_length: int | None = None
    #: USD per 1M tokens; None = not stated, 0 = free.
    input_per_million: float | None = None
    output_per_million: float | None = None


class ModelList(BaseModel):
    models: list[str]
    #: The same models with what the endpoint says about them (price, context, description) when it does.
    items: list[ModelInfoOut] = []
    error: str | None = None


def _model_list(infos) -> ModelList:
    return ModelList(models=[m.id for m in infos], items=[ModelInfoOut(**vars(m)) for m in infos])


_TIER_FIELDS = {
    "main": {"provider": "llm_provider", "model": "llm_model", "base_url": "llm_base_url", "api_key": "llm_api_key"},
    "background": {
        "provider": "background_llm_provider",
        "model": "background_llm_model",
        "base_url": "background_llm_base_url",
        "api_key": "background_llm_api_key",
    },
}


def _settings_out() -> LLMSettingsOut:
    s = get_settings()
    main_key = bool(tier_config("main").api_key)
    return LLMSettingsOut(
        main=TierSettings(provider=s.llm_provider, model=s.llm_model, base_url=s.llm_base_url, api_key_set=main_key),
        background=TierSettings(
            provider=s.background_llm_provider,
            model=s.background_llm_model,
            base_url=s.background_llm_base_url,
            api_key_set=bool(s.background_llm_api_key),
        ),
        timeout_seconds=s.llm_timeout_seconds,
    )


@router.get("/settings", response_model=LLMSettingsOut)
def get_llm_settings():
    """Configured settings per tier. API keys are never returned, only whether one is set."""
    return _settings_out()


@router.put("/settings", response_model=LLMSettingsOut)
def update_llm_settings(body: LLMSettingsUpdate, db: Session = Depends(get_session)):
    updates: dict[str, object] = {}
    for tier in TIERS:
        part: TierUpdate | None = getattr(body, tier)
        if part is None:
            continue
        for name in part.model_fields_set:
            value = getattr(part, name)
            if value is not None:
                updates[_TIER_FIELDS[tier][name]] = value
    if body.timeout_seconds is not None:
        updates["llm_timeout_seconds"] = body.timeout_seconds
    try:
        llm_settings.save(db, updates)
    except llm_settings.SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _settings_out()


@router.get("/models", response_model=ModelList)
async def available_models(tier: str = "main", provider: str | None = None, base_url: str | None = None):
    """Models offered by a tier's endpoint. ``provider``/``base_url`` let the page look before saving."""
    if tier not in TIERS:
        tier = "main"
    cfg = tier_config(tier)
    try:
        infos = await list_model_infos(
            provider or cfg.provider,
            cfg.base_url if base_url is None else base_url,
            cfg.api_key,
            timeout=min(get_settings().llm_timeout_seconds, 15.0),
        )
    except LLMError as exc:
        return ModelList(models=[], error=str(exc))
    return _model_list(infos)


class ModelsRequest(BaseModel):
    """What the settings page has typed so far: it need not be saved to look at the models."""

    tier: str = "main"
    provider: str | None = None
    base_url: str | None = None
    #: A key typed but not saved yet. Sent in the body, never in a URL.
    api_key: str | None = None


@router.post("/models", response_model=ModelList)
async def models_for_draft(body: ModelsRequest):
    """Models offered by the endpoint as typed in the form, before anything is saved.

    The key typed in the form is used for that endpoint. The tier's *saved* key is used only while provider and
    base URL are still the saved ones: a stored key must not be sent to an address someone is merely trying out.
    """
    tier = body.tier if body.tier in TIERS else "main"
    cfg = tier_config(tier)
    provider = body.provider or cfg.provider
    base_url = cfg.base_url if body.base_url is None else body.base_url
    if body.api_key:
        key = body.api_key
    else:
        key = cfg.api_key if (provider, base_url) == (cfg.provider, cfg.base_url) else ""
    try:
        infos = await list_model_infos(provider, base_url, key, timeout=min(get_settings().llm_timeout_seconds, 15.0))
    except LLMError as exc:
        return ModelList(models=[], error=str(exc))
    return _model_list(infos)


@router.get("/status", response_model=LLMStatus)
def llm_status():
    """What each tier runs on. Never contacts the provider and never returns keys."""
    tiers = []
    for tier in TIERS:
        cfg = tier_config(tier)
        try:
            get_llm_provider(tier)
            error = None
        except LLMError as exc:
            error = str(exc)
        tiers.append(
            TierStatus(
                tier=tier,
                provider=cfg.provider,
                model=cfg.model,
                base_url=cfg.base_url,
                configured=error is None,
                inherits=cfg.inherits,
                error=error,
            )
        )
    return LLMStatus(tiers=tiers)


@router.post("/test", response_model=LLMTestResult)
async def llm_test(tier: str = "main"):
    """One tiny round trip to prove the tier's model answers."""
    if tier not in TIERS:
        tier = "main"
    model = tier_config(tier).model
    try:
        reply = await get_llm_provider(tier).complete("Answer with the single word: pong.", "ping")
    except LLMError as exc:
        return LLMTestResult(ok=False, tier=tier, model=model, error=str(exc))
    return LLMTestResult(ok=True, tier=tier, model=model, reply=reply.strip()[:200])

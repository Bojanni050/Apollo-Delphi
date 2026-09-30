from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.llm import TIERS, LLMError, get_llm_provider, model_for

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

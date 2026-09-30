from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.config import get_settings
from app.core.embeddings import EmbeddingError, effective_embedding_key, get_embedding_provider
from app.services import llm_settings, model_manager
from app.services.embeddings import status as index

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


class EmbeddingSettingsOut(BaseModel):
    provider: str
    model: str
    base_url: str
    api_key_set: bool
    batch_size: int
    runtime: str


class EmbeddingSettingsUpdate(BaseModel):
    """Only the fields sent are changed. ``api_key`` of ``""`` clears the key."""

    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    batch_size: int | None = None
    runtime: str | None = None


class IndexStatusOut(BaseModel):
    provider: str | None
    model: str | None
    dimensions: int | None
    error: str | None
    chunks_total: int
    chunks_current: int
    documents_indexed: int
    documents_stale: int
    by_model: dict[str, int]


class EmbeddingTestOut(BaseModel):
    ok: bool
    model: str | None = None
    dimensions: int | None = None
    millis: int | None = None
    error: str | None = None


class PullRequest(BaseModel):
    runtime: str
    model: str


_FIELDS = {
    "provider": "embedding_provider",
    "model": "embedding_model",
    "base_url": "embedding_base_url",
    "api_key": "embedding_api_key",
    "batch_size": "embedding_batch_size",
    "runtime": "embedding_runtime",
}


def _settings_out() -> EmbeddingSettingsOut:
    s = get_settings()
    return EmbeddingSettingsOut(
        provider=s.embedding_provider,
        model=s.embedding_model,
        base_url=s.embedding_base_url,
        api_key_set=bool(effective_embedding_key()),
        batch_size=s.embedding_batch_size,
        runtime=s.embedding_runtime,
    )


@router.get("/settings", response_model=EmbeddingSettingsOut)
def get_embedding_settings():
    """Configured embedding settings. The API key is never returned, only whether one is set."""
    return _settings_out()


@router.put("/settings", response_model=EmbeddingSettingsOut)
def update_embedding_settings(body: EmbeddingSettingsUpdate, db: Session = Depends(get_session)):
    updates = {_FIELDS[n]: getattr(body, n) for n in body.model_fields_set if getattr(body, n) is not None}
    try:
        llm_settings.save(db, updates)
    except llm_settings.SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _settings_out()


@router.get("/status", response_model=IndexStatusOut)
def embedding_status(workspace_id: int | None = None, db: Session = Depends(get_session)):
    """The active model and how much of the vector index was built with it."""
    return IndexStatusOut(**index.index_status(db, workspace_id).__dict__)


@router.post("/test", response_model=EmbeddingTestOut)
async def test_embedding():
    """Embed one short text with the active model: proves the endpoint answers and reveals the dimension."""
    try:
        provider = get_embedding_provider()
        started = time.monotonic()
        vector = await provider.embed_query("Delphi embedding probe")
    except EmbeddingError as exc:
        return EmbeddingTestOut(ok=False, error=str(exc))
    return EmbeddingTestOut(
        ok=True, model=provider.model, dimensions=len(vector), millis=int((time.monotonic() - started) * 1000)
    )


@router.post("/reindex")
async def reindex(workspace_id: int | None = None, everything: bool = False, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Re-embed documents with the active model (only the stale ones unless ``everything``)."""
    try:
        return await index.reindex(db, workspace_id, everything)
    except EmbeddingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/catalog")
def embedding_catalog(runtime: str | None = None) -> dict[str, Any]:
    """Recommended models as a local runtime can serve and fetch them, plus runtime availability."""
    try:
        selected = model_manager.get_runtime(runtime) if runtime else model_manager.active_runtime()
    except model_manager.ModelManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "runtime": selected.id,
        "runtimes": model_manager.describe_runtimes(),
        "models": model_manager.catalog_for_runtime(selected.id),
    }


def _pull_out(progress) -> dict[str, Any]:
    """A pull's progress plus the follow-up: a finished download changes nothing by itself.

    The stored vectors were produced by the previous model and stay stale until the app is
    pointed at the new one and documents are re-indexed, so the operator is told instead of
    assuming the switch is done.
    """
    data = progress.as_dict()
    data["reindex_recommended"] = progress.status == "completed"
    return data


@router.get("/models/pull")
def pull_status(runtime: str, model: str) -> dict[str, Any]:
    return _pull_out(model_manager.get_pull_status(runtime, model))


@router.post("/models/pull")
def pull_model(body: PullRequest) -> dict[str, Any]:
    """Start downloading a recommended model to a local runtime (poll GET /models/pull for progress)."""
    try:
        return _pull_out(model_manager.start_pull(body.runtime, body.model))
    except model_manager.ModelManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

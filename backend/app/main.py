from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analysis, ask, delphi, documents, embeddings, github, issues, knowledge, llm, pulse, retrieval, search, system, weave, workspaces
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()

app = FastAPI(title="Apollo", version="0.1.0", description="AI document reasoning, investigation and synthesis system")

app.add_middleware(
    CORSMiddleware,
    # The dev (5173) and preview (4173) servers, reached as localhost or as 127.0.0.1: browsers treat the two as
    # different origins, so both must be allowed. Any other port on a loopback address is fine too.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix=settings.api_prefix)
app.include_router(search.router, prefix=settings.api_prefix)
app.include_router(analysis.router, prefix=settings.api_prefix)
app.include_router(issues.router, prefix=settings.api_prefix)
app.include_router(knowledge.router, prefix=settings.api_prefix)
app.include_router(ask.router, prefix=settings.api_prefix)
app.include_router(delphi.router, prefix=settings.api_prefix)
app.include_router(pulse.router, prefix=settings.api_prefix)
app.include_router(weave.router, prefix=settings.api_prefix)
app.include_router(embeddings.router, prefix=settings.api_prefix)
app.include_router(retrieval.router, prefix=settings.api_prefix)
app.include_router(system.router, prefix=settings.api_prefix)
app.include_router(llm.router, prefix=settings.api_prefix)
app.include_router(workspaces.router, prefix=settings.api_prefix)
app.include_router(github.router, prefix=settings.api_prefix)


def _load_runtime_settings() -> None:
    """Apply settings chosen in the UI (app_settings) over the environment."""
    from app.db.session import SessionLocal
    from app.services import llm_settings

    db = SessionLocal()
    try:
        llm_settings.load_overrides(db)
    except Exception as exc:  # table missing before migrations ran, etc.
        log.warning("Could not load stored settings: %s", exc)
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    settings.ensure_upload_dir()
    from app.db.session import engine, init_db

    if engine.dialect.name != "postgresql":  # PostgreSQL is built by Alembic (docker-compose, app.serve)
        init_db()
    _load_runtime_settings()
    try:
        from app.services.documents.index_queue import recover_interrupted_indexing

        if recover_interrupted_indexing():
            log.info("Documents left half-indexed by a stopped app are pending again")
    except Exception as exc:  # the table may not exist yet (before migrations)
        log.warning("Could not recover interrupted indexing: %s", exc)
    try:
        from app.services.analysis.service import recover_interrupted_analyses

        if recover_interrupted_analyses():
            log.info("Analyses that were running when the app stopped are marked as failed")
    except Exception as exc:
        log.warning("Could not recover interrupted analyses: %s", exc)
    log.info("Apollo started (environment=%s, llm=%s/%s, embeddings=%s/%s)", settings.environment, settings.llm_provider, settings.llm_model, settings.embedding_provider, settings.embedding_model)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
    }

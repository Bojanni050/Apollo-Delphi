from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analysis, ask, documents, embeddings, github, issues, knowledge, llm, pulse, search, workspaces
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()

app = FastAPI(title="Apollo", version="0.1.0", description="AI document reasoning, investigation and synthesis system")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
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
app.include_router(pulse.router, prefix=settings.api_prefix)
app.include_router(embeddings.router, prefix=settings.api_prefix)
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
    if not settings.database_url.startswith("postgresql"):
        from app.db.session import init_db

        init_db()
    _load_runtime_settings()
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

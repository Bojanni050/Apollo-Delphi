from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}
    return {"pool_pre_ping": True}


_engine_url = os.environ.get("APOLLO_DATABASE_URL") or get_settings().database_url
engine = create_engine(_engine_url, **_engine_kwargs(_engine_url))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  ensure models are registered

    Base.metadata.create_all(bind=engine)

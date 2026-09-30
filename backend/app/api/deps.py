from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import get_db


def get_session() -> Session:
    yield from get_db()

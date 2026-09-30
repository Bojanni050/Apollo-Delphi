"""Vector storage abstraction.

The primary target is PostgreSQL + pgvector. The pgvector column type is
used when the active dialect is postgresql. Other dialects (notably sqlite,
used by the offline test suite) fall back to a JSON-encoded column so the
same SQLAlchemy models and application code work in both environments.
"""

from __future__ import annotations

import json

from sqlalchemy import Text, TypeDecorator
from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.types import DateTime, TypeEngine

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment]


class JSONEncodedVector(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return json.dumps([float(v) for v in value])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


def vector_column(dimensions: int | None = None) -> TypeEngine:
    """Vector column; ``None`` = any dimension (vectors of different models live side by side)."""
    if Vector is not None:
        return Vector(dimensions) if dimensions else Vector()
    return JSONEncodedVector()


try:
    from pgvector.sqlalchemy import Vector  # noqa: F811

    if hasattr(ischema_names, "__setitem__"):
        ischema_names["vector"] = Vector
except Exception:  # pragma: no cover
    pass

__all__ = ["vector_column", "JSONEncodedVector"]

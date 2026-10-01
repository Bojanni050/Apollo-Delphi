from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class QAEntry(Base):
    """A question asked in a werkmap and the cited answer it received. Kept so answers stay inspectable."""

    __tablename__ = "qa_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    #: The question this one follows up on; the chain of parents is the conversation.
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("qa_entries.id", ondelete="SET NULL"), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text)
    #: For a follow-up: the question rewritten so it stands on its own ("And when?" -> "When is the harbour budget due?").
    #: This is what retrieval searched for. NULL for a first question.
    standalone_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str] = mapped_column(Text)
    #: False when the documents do not answer the question (no model call was needed or the model said so).
    answered: Mapped[bool] = mapped_column(Boolean, default=True)
    #: True when every claim could be tied to a cited source (see services/ask/service.py).
    grounded: Mapped[bool] = mapped_column(Boolean, default=True)
    citations: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of cited sources
    warnings: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    search_mode: Mapped[str] = mapped_column(String(16), default="hybrid")
    model_provider: Mapped[str] = mapped_column(String(64), default="")
    model_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

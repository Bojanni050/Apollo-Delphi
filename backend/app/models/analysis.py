from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    stats: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    claims = relationship("Claim", backref="analysis_run", cascade="all, delete-orphan")
    issues = relationship("Issue", backref="analysis_run", cascade="all, delete-orphan")
    knowledge_items = relationship("KnowledgeItem", backref="analysis_run", cascade="all, delete-orphan")

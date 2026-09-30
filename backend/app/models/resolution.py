from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Resolution(Base):
    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="unresolved")
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_refs: Mapped[str | None] = mapped_column(Text, nullable=True)
    unresolved_uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str] = mapped_column(String(32), default="apollo")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    issue = relationship("Issue", back_populates="resolutions")
    human_decisions: Mapped[list["HumanDecision"]] = relationship(back_populates="resolution", cascade="all, delete-orphan")


class HumanDecision(Base):
    __tablename__ = "human_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resolution_id: Mapped[int] = mapped_column(ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(128), default="user")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    resolution = relationship("Resolution", back_populates="human_decisions")

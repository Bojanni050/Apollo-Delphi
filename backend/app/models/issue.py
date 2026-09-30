from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    issue_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    evidence_links: Mapped[list[IssueEvidence]] = relationship(back_populates="issue", cascade="all, delete-orphan")
    claim_links: Mapped[list[IssueClaim]] = relationship(back_populates="issue", cascade="all, delete-orphan")
    investigations: Mapped[list["Investigation"]] = relationship(back_populates="issue", cascade="all, delete-orphan")
    resolutions: Mapped[list["Resolution"]] = relationship(back_populates="issue", cascade="all, delete-orphan")


class IssueEvidence(Base):
    __tablename__ = "issue_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False, index=True)
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    issue = relationship("Issue", back_populates="evidence_links")
    evidence = relationship("Evidence")


class IssueClaim(Base):
    __tablename__ = "issue_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), default="conflicting")

    issue = relationship("Issue", back_populates="claim_links")
    claim = relationship("Claim", back_populates="issue_links")

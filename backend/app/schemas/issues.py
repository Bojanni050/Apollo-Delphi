from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    evidence_type: str
    page_number: int | None
    section: str | None
    line_start: int | None = None
    line_end: int | None = None
    original_text: str


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    statement: str
    subject: str | None
    predicate: str | None
    value: str | None
    unit: str | None
    status: str
    confidence: float


class ResolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    issue_id: int
    status: str
    conclusion: str | None
    reasoning: str | None
    explanation_type: str | None
    confidence: float
    unresolved_uncertainty: str | None
    resolved_by: str
    created_at: dt.datetime


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_run_id: int
    issue_type: str
    title: str
    question: str | None
    status: str
    severity: str
    created_at: dt.datetime


class IssueDetail(IssueOut):
    description: str | None
    claims: list[ClaimOut] = []
    evidence: list[EvidenceOut] = []
    resolution: ResolutionOut | None = None


class ResolveRequest(BaseModel):
    decision: str | None = None
    note: str | None = None

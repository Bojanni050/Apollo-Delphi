from __future__ import annotations

import os
import tempfile

os.environ["APOLLO_DATABASE_URL"] = "sqlite:///./test_apollo.db"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["WORKSPACES_ROOT"] = tempfile.mkdtemp(prefix="apollo_test_workspaces_")
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="apollo_test_uploads_")

import pytest
from fastapi.testclient import TestClient

from app.db.session import Base, SessionLocal, engine, init_db
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_tables(db):
    from app.models import (
        AnalysisRun,
        Claim,
        ClaimEvidence,
        Document,
        DocumentChunk,
        Evidence,
        GeneratedDocument,
        HumanDecision,
        Investigation,
        Issue,
        IssueClaim,
        IssueEvidence,
        KnowledgeItem,
        PulseItem,
        PulseRun,
        Resolution,
        VerificationFinding,
        Workspace,
    )

    for table in (
        PulseItem,
        PulseRun,
        VerificationFinding,
        HumanDecision,
        Resolution,
        Investigation,
        IssueEvidence,
        IssueClaim,
        Issue,
        ClaimEvidence,
        KnowledgeItem,
        Claim,
        Evidence,
        DocumentChunk,
        GeneratedDocument,
        AnalysisRun,
        Document,
    ):
        db.query(table).delete()
    db.commit()
    yield

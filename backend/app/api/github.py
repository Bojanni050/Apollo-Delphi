from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.github import GitHubIngestRequest, GitHubIngestResult
from app.services.documents.indexer import IndexingService
from app.services.github.client import GitHubIngestError
from app.services.github.service import github_ingest_service

router = APIRouter(prefix="/github", tags=["github"])


@router.post("/ingest", response_model=GitHubIngestResult, status_code=201)
async def ingest_repository(body: GitHubIngestRequest, db: Session = Depends(get_session)):
    """Fetch a GitHub repository's docs/config/code and index it into the workspace.

    Files are registered as documents (source_type='github') and indexed
    immediately, so analysis can compare them against uploaded documents and
    surface discrepancies (contradictions, open questions).
    """
    try:
        result = github_ingest_service.ingest_repo(
            db, body.repo_url, workspace_id=body.workspace_id, branch=body.branch
        )
    except GitHubIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not result["document_ids"]:
        raise HTTPException(
            status_code=400,
            detail="Geen bruikbare tekstbestanden gevonden in de repository",
        )

    indexer = IndexingService()
    for doc_id in result["document_ids"]:
        try:
            await indexer.index_document(db, doc_id)
        except Exception as exc:  # indexing failure is persisted per-document
            result["errors"].append(f"indexing doc {doc_id}: {exc}")

    return GitHubIngestResult(**result)

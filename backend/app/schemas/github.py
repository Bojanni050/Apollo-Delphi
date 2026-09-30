from __future__ import annotations

from pydantic import BaseModel, Field


class GitHubIngestRequest(BaseModel):
    repo_url: str = Field(min_length=3, max_length=512)
    workspace_id: int | None = None
    branch: str | None = None


class GitHubIngestResult(BaseModel):
    repository: str
    branch: str
    files_selected: int
    documents_created: int
    document_ids: list[int] = []
    errors: list[str] = []

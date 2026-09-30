from __future__ import annotations

import json
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Document

from app.services.github.client import (
    GitHubClient,
    GitHubIngestError,
    parse_repo_url,
    select_text_files,
)

log = get_logger(__name__)

MAX_DIGEST_CHARS = 400_000


class GitHubIngestService:
    """Downloads a repository and registers it as ONE document.

    The full repo content (docs, config, code) is fetched once and combined
    into a single structured digest. The interface shows one document row
    per repository, not one per file. The digest keeps per-file sections so
    claims stay traceable to concrete repo paths.
    """

    def ingest_repo(
        self,
        db: Session,
        repo_url: str,
        workspace_id: int | None = None,
        branch: str | None = None,
    ) -> dict:
        owner, repo = parse_repo_url(repo_url)
        token = get_settings().github_token or None
        client = GitHubClient(token=token)

        info = client.repo_info(owner, repo)
        default_branch = info.get("default_branch", "main")
        branch = branch or default_branch

        tree = client.default_branch_tree(owner, repo)
        if tree.get("truncated"):
            log.warning("Repository tree is truncated for %s/%s", owner, repo)
        paths = select_text_files(tree)

        sections: list[str] = []
        errors: list[str] = []
        total_chars = 0
        included: list[str] = []

        for path in paths:
            try:
                content = client.fetch_file(owner, repo, path)
            except GitHubIngestError as exc:
                errors.append(f"{path}: {exc}")
                continue
            text = content.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            section = f"## FILE: {path}\n\n{text}"
            if total_chars + len(section) > MAX_DIGEST_CHARS:
                remaining = MAX_DIGEST_CHARS - total_chars
                if remaining > 2000:
                    section = section[:remaining] + "\n\n[... afgekapt, bestand te lang ...]"
                    sections.append(section)
                    included.append(path)
                total_chars = MAX_DIGEST_CHARS
                break
            sections.append(section)
            included.append(path)
            total_chars += len(section)

        if not sections:
            raise GitHubIngestError("Geen bruikbare tekstinhoud gevonden in de repository")

        digest = (
            f"# Repository: {owner}/{repo} (branch: {branch})\n\n"
            + "\n\n".join(sections)
        )

        doc = Document(
            workspace_id=workspace_id,
            filename=f"github:{owner}/{repo}@{branch}",
            stored_filename="-",
            file_type="md",
            file_size=len(digest.encode()),
            content_hash="",
            title=f"{owner}/{repo}",
            doc_metadata=json.dumps(
                {
                    "github": {
                        "owner": owner,
                        "repo": repo,
                        "branch": branch,
                        "files": included,
                        "files_total": len(paths),
                    }
                }
            ),
            indexing_status="pending",
            source_type="github",
            source_url=f"https://github.com/{owner}/{repo}/tree/{branch}",
            repo_path=None,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        return {
            "repository": f"{owner}/{repo}",
            "branch": branch,
            "files_selected": len(paths),
            "documents_created": 1,
            "document_ids": [doc.id],
            "errors": errors,
        }

    def get_document_content(self, doc: Document) -> bytes | None:
        """GitHub documents fetch fresh content on demand (not stored on disk)."""
        if doc.source_type != "github":
            return None
        meta = json.loads(doc.doc_metadata or "{}").get("github", {})
        owner, repo, branch = meta.get("owner"), meta.get("repo"), meta.get("branch")
        if not (owner and repo):
            return None
        token = get_settings().github_token or None
        client = GitHubClient(token=token)
        tree = client.default_branch_tree(owner, repo)
        paths = select_text_files(tree)
        sections: list[str] = []
        total_chars = 0
        for path in paths:
            try:
                content = client.fetch_file(owner, repo, path)
            except GitHubIngestError:
                continue
            text = content.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            section = f"## FILE: {path}\n\n{text}"
            if total_chars + len(section) > MAX_DIGEST_CHARS:
                break
            sections.append(section)
            total_chars += len(section)
        if not sections:
            return None
        digest = f"# Repository: {owner}/{repo} (branch: {branch})\n\n" + "\n\n".join(sections)
        return digest.encode()


github_ingest_service = GitHubIngestService()

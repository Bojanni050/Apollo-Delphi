"""Bring everything that belongs to no werkmap into one.

Before werkmappen existed, documents, analyses and generated documents had no owner. They stay
visible only while no werkmap is selected (see the scoping rule: omitting `workspace_id` selects
what belongs to no werkmap). Adopting moves the whole set together, so analyses keep pointing at
the documents they were made from:

* documents,
* analysis runs (and with them their claims, issues and knowledge),
* generated documents.

Uploaded originals are also copied into the werkmap's repository (``Inbox/``) and committed, as
for any new upload. Documents ingested from GitHub have no uploaded original and are not copied.
Nothing is deleted, and only things that currently belong to no werkmap are touched, so running it
again is harmless.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import AnalysisRun, Document, GeneratedDocument, Workspace
from app.services import workspace_repo

log = get_logger(__name__)


def unassigned_counts(db: Session) -> dict[str, int]:
    return {
        "documents": db.query(Document).filter(Document.workspace_id.is_(None)).count(),
        "analysis_runs": db.query(AnalysisRun).filter(AnalysisRun.workspace_id.is_(None)).count(),
        "generated_documents": db.query(GeneratedDocument).filter(GeneratedDocument.workspace_id.is_(None)).count(),
    }


def adopt_unassigned(db: Session, ws: Workspace) -> dict:
    docs = db.query(Document).filter(Document.workspace_id.is_(None)).order_by(Document.id).all()
    runs = db.query(AnalysisRun).filter(AnalysisRun.workspace_id.is_(None)).all()
    generated = db.query(GeneratedDocument).filter(GeneratedDocument.workspace_id.is_(None)).all()

    for row in (*docs, *runs, *generated):
        row.workspace_id = ws.id
    db.commit()  # ownership first: it is the part that must not be half done

    mirrored, not_mirrored = 0, []
    uploads = [d for d in docs if d.source_type != "github" and not d.inbox_path]
    if uploads:
        try:
            if ws.working_dir is None:
                ws.working_dir = str(workspace_repo.init_repo(workspace_repo.default_working_dir(ws.id, ws.name)))
            repo = Path(ws.working_dir)
            workspace_repo.init_repo(repo)  # also fine for an existing repository
        except (OSError, workspace_repo.GitError) as exc:
            log.warning("Could not prepare the repository of werkmap %s: %s", ws.id, exc)
            repo = None
            not_mirrored = [{"document_id": d.id, "filename": d.filename, "reason": f"repository: {exc}"} for d in uploads]
        if repo is not None:
            stored_dir = get_settings().ensure_upload_dir()
            for d in uploads:
                path = stored_dir / d.stored_filename
                try:
                    data = path.read_bytes()
                except OSError:
                    not_mirrored.append({"document_id": d.id, "filename": d.filename, "reason": "original file not found"})
                    continue
                try:
                    d.inbox_path = workspace_repo.store_in_inbox(repo, d.filename, data)
                    mirrored += 1
                except OSError as exc:
                    not_mirrored.append({"document_id": d.id, "filename": d.filename, "reason": str(exc)})
        db.commit()

    return {
        "documents": len(docs),
        "analysis_runs": len(runs),
        "generated_documents": len(generated),
        "mirrored_to_repository": mirrored,
        "not_mirrored": not_mirrored,
    }

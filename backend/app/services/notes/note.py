"""A note the user writes themselves.

"Notitie" is the place for the user's own notes: a short title and a body of Markdown, stored as a
``GeneratedDocument`` of kind ``note`` — visible on the Notities page — and written into the werkmap's
git repository as ``Notes/<slug>.md``, so it is a real file among the other documents, with its own
commit. No model is involved: the words are the user's own.
"""

from __future__ import annotations

import re

from pathlib import Path
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Workspace
from app.models.generated_document import GeneratedDocument
from app.services import workspace_repo

log = get_logger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")[:60]
    return slug or "notitie"


class NoteService:
    def create_note(self, db: Session, workspace_id: int, title: str, content: str) -> GeneratedDocument:
        """Add a note of the user's own words to a werkmap. Raises ValueError when the werkmap
        does not exist."""
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError("Werkmap niet gevonden")

        doc = GeneratedDocument(
            workspace_id=workspace_id,
            title=title,
            status="drafted",
            doc_kind="note",
            content=content,
            verification_status="pending",
            revision=0,
            generation_metadata='{"source": "user"}',
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        self._store_in_repo(workspace, doc)
        return doc

    def _store_in_repo(self, workspace: Workspace, doc: GeneratedDocument) -> None:
        """Write the note into the werkmap as ``Notes/<slug>.md``, its own commit. Failing
        here must not cost the user their note (it is already in the database)."""
        try:
            if workspace.working_dir is None:
                workspace.working_dir = str(workspace_repo.init_repo(workspace_repo.default_working_dir(workspace.id, workspace.name)))
            notes = Path(workspace.working_dir) / "Notes"
            notes.mkdir(parents=True, exist_ok=True)
            path = notes / f"{_slug(doc.title)}.md"
            stem = _slug(doc.title)
            n = 1
            while path.exists():
                n += 1
                path = notes / f"{stem}-{n}.md"
            body = doc.content or ""
            header = f"---\ntitle: {doc.title}\nmade_by: user\n---\n\n"
            path.write_text(header + body, encoding="utf-8")
            rel = path.relative_to(workspace.working_dir).as_posix()
            from app.services.workspace_repo import _commit_paths

            _commit_paths(Path(workspace.working_dir), [rel], f"Add note: {doc.title[:60]}")
        except (OSError, workspace_repo.GitError) as exc:
            log.warning("Could not store the note of werkmap %s in its repository: %s", workspace.id, exc)

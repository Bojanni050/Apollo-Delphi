"""Delphi Weave: how the documents of a werkmap hang together, as the user has accepted it in Delphi Pulse.

Nothing is computed here: the groups, type folders, tags and connections are what accepted Pulse suggestions wrote into the
documents. A suggestion that is still open is not part of the weave until the user accepts it.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.models import Document, Workspace
from app.models.document import READY_STATUSES
from app.schemas.weave import WeaveConnectionOut, WeaveDocumentOut, WeaveOut
from app.services.workspace_repo import INBOX_DIR

router = APIRouter(tags=["weave"])

RELATIONS = ("relates-to", "supports", "contradicts", "extends")


@router.get("/workspaces/{workspace_id}/weave", response_model=WeaveOut)
def get_weave(workspace_id: int, db: Session = Depends(get_session)):
    if db.get(Workspace, workspace_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    docs = (
        db.query(Document)
        .filter(Document.workspace_id == workspace_id, Document.indexing_status.in_(READY_STATUSES))
        .order_by(Document.id)
        .all()
    )
    known = {d.id for d in docs}
    documents: list[WeaveDocumentOut] = []
    connections: dict[tuple[int, int, str], WeaveConnectionOut] = {}
    for d in docs:
        meta = d.metadata_dict
        folder = d.inbox_path.split("/")[0] if d.inbox_path and "/" in d.inbox_path else None
        documents.append(
            WeaveDocumentOut(
                id=d.id,
                filename=d.filename,
                group=d.group_name,
                folder=None if folder in (None, INBOX_DIR) else folder,
                tags=[str(t) for t in meta.get("tags", [])],
            )
        )
        for c in meta.get("connections", []):
            target, relation = c.get("document_id"), c.get("relation")
            if target not in known or target == d.id or relation not in RELATIONS:
                continue
            # A pair of documents that point at each other with the same relation is one line, not two.
            key = (min(d.id, target), max(d.id, target), relation)
            connections.setdefault(key, WeaveConnectionOut(source=d.id, target=target, relation=relation, why=str(c.get("why", ""))))
    return WeaveOut(documents=documents, connections=list(connections.values()))

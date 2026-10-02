from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.llm import LLMError
from app.models import Workspace
from app.models.delphi_chat import DelphiChatMessage
from app.schemas.delphi_chat import (
    DelphiChatOut,
    DelphiChatRequest,
    DelphiMessageOut,
    DelphiOracleRequest,
)
from app.schemas.notes import NoteCreateRequest
from app.models.generated_document import GeneratedDocument
from app.schemas.generated import GeneratedDocumentOut
from app.services.delphi_chat.oracle import DelphiOracleService
from app.services.notes.note import NoteService
from app.services.delphi_chat.service import DelphiChatService

router = APIRouter(prefix="/delphi", tags=["delphi"])


def _out(m: DelphiChatMessage) -> DelphiMessageOut:
    return DelphiMessageOut(
        id=m.id,
        workspace_id=m.workspace_id,
        parent_id=m.parent_id,
        role=m.role,
        content=m.content,
        refusal=m.refusal,
        created_at=m.created_at,
    )


@router.post("/chat", response_model=DelphiChatOut, status_code=201)
async def chat(body: DelphiChatRequest, db: Session = Depends(get_session)):
    """Talk to Delphi, the chat agent of one werkmap: its documents and Apollo itself, nothing else."""
    if db.get(Workspace, body.workspace_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    parent = None
    if body.follow_up_of is not None:
        parent = db.get(DelphiChatMessage, body.follow_up_of)
        if parent is None:
            raise HTTPException(status_code=404, detail="The message to follow up on was not found")
        if parent.workspace_id != body.workspace_id:
            raise HTTPException(status_code=400, detail="A follow-up belongs to the werkmap of the conversation")
    try:
        result = await DelphiChatService().chat(db, body.message, body.workspace_id, parent=parent)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return DelphiChatOut(user_message=_out(result.user_message), reply=_out(result.reply))


@router.post("/note", response_model=GeneratedDocumentOut, status_code=201)
async def add_note(body: NoteCreateRequest, db: Session = Depends(get_session)):
    """Add a note the user writes themselves: a document of the werkmap (Notities page) and a
    markdown file in its repository (Notes/)."""
    try:
        doc = NoteService().create_note(db, body.workspace_id, body.title, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return doc


@router.post("/oracle", response_model=GeneratedDocumentOut, status_code=201)
async def make_oracle(body: DelphiOracleRequest, db: Session = Depends(get_session)):
    """Turn an exchange with Delphi into an oracle: a document of the werkmap (Oracles page) and a
    markdown file in its repository (Oracles/)."""
    try:
        doc = await DelphiOracleService().make_oracle(db, body.workspace_id, body.reply_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return doc


@router.get("/history", response_model=list[DelphiMessageOut])
def history(workspace_id: int, limit: int = 200, db: Session = Depends(get_session)):
    """The recent turns of a werkmap's conversations, oldest first (the chat opens on the last one)."""
    rows = (
        db.query(DelphiChatMessage)
        .filter(DelphiChatMessage.workspace_id == workspace_id)
        .order_by(DelphiChatMessage.id.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [_out(m) for m in reversed(rows)]

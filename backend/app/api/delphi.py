from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.llm import LLMError
from app.models import Workspace
from app.models.delphi_chat import DelphiChatMessage
from app.schemas.delphi_chat import DelphiChatOut, DelphiChatRequest, DelphiMessageOut
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

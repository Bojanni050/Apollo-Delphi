from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.codecheck import CodecheckRequest
from app.services.codecheck.service import CodecheckError
from app.services.codecheck.verdicts import CodecheckEngine, CodecheckResult
from app.services.github.client import GitHubIngestError

router = APIRouter(prefix="/codecheck", tags=["codecheck"])


@router.post("/run", response_model=CodecheckResult)
async def run_codecheck(body: CodecheckRequest, db: Session = Depends(get_session)):
    """Leg documenten naast repositories: per bewering uit de docs een oordeel
    (bevestigd, tegengesproken, niet_gevonden) met het codebewijs erbij."""
    try:
        return await CodecheckEngine().run(
            db,
            workspace_id=body.workspace_id,
            document_ids=body.document_ids,
            repo_refs=[r.model_dump(exclude_none=True) for r in body.repos],
        )
    except CodecheckError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GitHubIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

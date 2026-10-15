from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.schemas.codecheck import CodecheckRequest, CodecheckStartOut
from app.services.codecheck.progress import codecheck_progress
from app.services.codecheck.service import CodecheckError
from app.services.codecheck.verdicts import CodecheckEngine, CodecheckResult
from app.services.github.client import GitHubIngestError

log = get_logger(__name__)

router = APIRouter(prefix="/codecheck", tags=["codecheck"])


@router.post("/run", response_model=None)
async def run_codecheck(
    body: CodecheckRequest,
    background: bool = Query(False, description="Direct terugkeren met een run-id; volg hem op GET /codecheck/{id}/progress"),
    db: Session = Depends(get_session),
):
    """Leg documenten naast repositories: per bewering uit de docs een oordeel
    (bevestigd, tegengesproken, niet_gevonden) met het codebewijs erbij.

    Met ``background=true`` gebeurt dat op de achtergrond en meldt de run wat hij doet; de pagina ziet de oordelen
    verschijnen zodra ze er zijn (elke bewering is een LLM-aanroep en kan even duren).
    """
    refs = [r.model_dump(exclude_none=True) for r in body.repos]
    if background:
        if codecheck_progress.running_for(body.workspace_id) is not None:
            raise HTTPException(status_code=409, detail="Er loopt al een codecheck in deze werkmap")
        progress = codecheck_progress.start(body.workspace_id)
        threading.Thread(
            target=_execute_in_background,
            args=(progress.run_id, body.workspace_id, body.document_ids, refs),
            daemon=True,
            name=f"codecheck-{progress.run_id}",
        ).start()
        return CodecheckStartOut(run_id=progress.run_id)
    try:
        return await CodecheckEngine().run(
            db,
            workspace_id=body.workspace_id,
            document_ids=body.document_ids,
            repo_refs=refs,
        )
    except CodecheckError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GitHubIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _execute_in_background(run_id: int, workspace_id: int | None, document_ids: list[int], repo_refs: list[dict]) -> None:
    """De codecheck zelf, op zijn eigen thread met zijn eigen database-sessie. Een fout komt op de voortgang."""
    db = SessionLocal()
    try:
        asyncio.run(
            CodecheckEngine().run(
                db,
                workspace_id=workspace_id,
                document_ids=document_ids,
                repo_refs=repo_refs,
                run_id=run_id,
            )
        )
    except Exception as exc:  # al gemeld aan de pagina; hier alleen het log
        log.exception("Codecheck %s failed", run_id)
        codecheck_progress.fail(run_id, str(exc)[:500])
    finally:
        db.close()


@router.get("/running")
def running_codecheck(workspace_id: int | None = None):
    """De codecheck die in deze werkmap loopt (null als er geen is): de pagina pakt hem zo weer op."""
    progress = codecheck_progress.running_for(workspace_id)
    return codecheck_progress.snapshot(progress) if progress else None


@router.get("/{run_id}/progress")
def codecheck_run_progress(run_id: int, since: int = 0):
    """Wat de run doet: fase, document, tellers, de getoetste beweringen en (als hij klaar is) het resultaat."""
    progress = codecheck_progress.get(run_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Codecheck-run niet gevonden")
    return codecheck_progress.snapshot(progress, since)

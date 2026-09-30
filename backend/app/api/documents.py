from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.documents import DocumentOut
from app.schemas.generated import GeneratedDocumentOut
from app.services.documents.indexer import IndexingError, IndexingService
from app.services.documents.service import DocumentValidationError, document_service
from app.services.generation.service import GenerationService
from app.services.knowledge.service import KnowledgeService
from app.services.verification.service import VerificationService
from app.schemas.generated import FindingOut

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    workspace_id: int | None = None,
    db: Session = Depends(get_session),
):
    data = await file.read()
    try:
        doc = document_service.create_document(db, file.filename or "upload", data, workspace_id=workspace_id)
    except DocumentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(workspace_id: int | None = None, db: Session = Depends(get_session)):
    return document_service.list_documents(db, workspace_id=workspace_id)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_session)):
    doc = document_service.get_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_session)):
    if not document_service.delete_document(db, document_id):
        raise HTTPException(status_code=404, detail="Document not found")


@router.post("/{document_id}/index", response_model=DocumentOut)
async def index_document(document_id: int, db: Session = Depends(get_session)):
    doc = document_service.get_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        return await IndexingService().index_document(db, document_id)
    except IndexingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/generate", response_model=GeneratedDocumentOut, status_code=status.HTTP_201_CREATED)
async def generate_document(
    title: str = "Synthesized Report",
    analysis_run_id: int | None = None,
    workspace_id: int | None = None,
    db: Session = Depends(get_session),
):
    try:
        doc = await GenerationService().generate(db, title, analysis_run_id, workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    knowledge = KnowledgeService().get_knowledge_state(db, analysis_run_id, workspace_id)
    VerificationService().verify(db, doc, knowledge)
    db.refresh(doc)
    return doc


@router.get("/generated/list", response_model=list[GeneratedDocumentOut])
def list_generated_documents(workspace_id: int | None = None, db: Session = Depends(get_session)):
    """Generated documents of one werkmap; omitted = those that belong to no werkmap."""
    from app.models import GeneratedDocument

    return db.query(GeneratedDocument).filter(GeneratedDocument.workspace_id == workspace_id).order_by(GeneratedDocument.id.desc()).all()


@router.get("/generated/{generated_id}", response_model=GeneratedDocumentOut)
def get_generated_document(generated_id: int, db: Session = Depends(get_session)):
    from app.models import GeneratedDocument

    doc = db.get(GeneratedDocument, generated_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Generated document not found")
    return doc


@router.get("/generated/{generated_id}/verification", response_model=list[FindingOut])
def get_verification(generated_id: int, db: Session = Depends(get_session)):
    from app.models import GeneratedDocument

    doc = db.get(GeneratedDocument, generated_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Generated document not found")
    return doc.verification_findings

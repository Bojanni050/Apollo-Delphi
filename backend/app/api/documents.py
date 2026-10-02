from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.config import get_settings
from app.models import Document, DocumentChunk
from app.schemas.documents import (
    DocumentHtmlOut, DocumentOut, DocumentTextOut, FolderFileRequest, FolderScanOut, FolderScanRequest, IndexQueueOut, IndexQueueRequest,
)
from app.services.documents.index_queue import index_queue
from app.services.documents.reading import cached_text
from app.services.extraction.base import ExtractionError
from app.services.documents import folder_import
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
    #: For a file of an uploaded folder: its path inside that folder ("docs/adr/001.md"). Names the document.
    relative_path: str | None = Form(default=None),
    db: Session = Depends(get_session),
):
    data = await file.read()
    try:
        doc = document_service.create_document(
            db, file.filename or "upload", data, workspace_id=workspace_id, relative_path=relative_path
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return doc


def _queue_out(added: int = 0) -> IndexQueueOut:
    return IndexQueueOut(**vars(index_queue.status()), added=added)


@router.post("/index-queue", response_model=IndexQueueOut)
async def queue_indexing(body: IndexQueueRequest, db: Session = Depends(get_session)):
    """Index documents in the background and return at once.

    Every queued document is first read (extracted, cut into fragments: a fraction of a second, after which it can be read
    and searched by words), then the documents are embedded one after the other (seconds per fragment on a CPU). Progress:
    GET /documents/index-queue.
    """
    query = db.query(Document.id)
    if body.document_ids is not None:
        query = query.filter(Document.id.in_(body.document_ids))
    else:
        # what still has to be read or embedded (a failed one is tried again)
        query = query.filter(Document.workspace_id == body.workspace_id, Document.indexing_status.in_(("pending", "parsed", "failed")))
    ids = [row[0] for row in query.order_by(Document.id)]
    return _queue_out(added=index_queue.enqueue(ids))


@router.get("/index-queue", response_model=IndexQueueOut)
def indexing_progress():
    return _queue_out()


def _folder_import_allowed() -> None:
    if not get_settings().folder_browse_enabled:
        raise HTTPException(status_code=403, detail="Importing folders from disk is switched off (FOLDER_BROWSE_ENABLED=false)")


@router.post("/folder/scan", response_model=FolderScanOut)
def scan_folder(body: FolderScanRequest):
    """List a folder of this machine, recursively: what would be imported (with hashes) and what is skipped, and why."""
    _folder_import_allowed()
    try:
        root = folder_import.resolve_root(body.path)
        scan = folder_import.scan_folder(root)
    except folder_import.FolderImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FolderScanOut(
        root=str(root),
        name=root.name or str(root),
        files=[{"path": f.path, "size": f.size, "content_hash": f.content_hash} for f in scan.files],
        skipped=[{"path": path, "reason": reason} for path, reason in scan.skipped],
        truncated=scan.truncated,
    )


@router.post("/folder/file", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def import_folder_file(body: FolderFileRequest, db: Session = Depends(get_session)):
    """Import one file of a scanned folder, named by its path in it ("<folder name>/docs/a.md")."""
    _folder_import_allowed()
    try:
        root = folder_import.resolve_root(body.root)
        data = folder_import.read_file(root, body.path)
        inside = body.path.replace("\\", "/").strip("/")
        return document_service.create_document(
            db, inside.rsplit("/", 1)[-1], data, workspace_id=body.workspace_id,
            relative_path=f"{root.name or 'map'}/{inside}",
        )
    except (folder_import.FolderImportError, DocumentValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=list[DocumentOut])
def list_documents(workspace_id: int | None = None, db: Session = Depends(get_session)):
    return document_service.list_documents(db, workspace_id=workspace_id)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_session)):
    doc = document_service.get_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{document_id}/text", response_model=DocumentTextOut)
def get_document_text(document_id: int, db: Session = Depends(get_session)):
    """The extracted text of a document with its pages and fragments, for the reading pane."""
    doc = document_service.get_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        readable = cached_text(doc, document_service.extract)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="The stored file of this document is gone")
    except (DocumentValidationError, ExtractionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).order_by(DocumentChunk.chunk_index).all()
    return DocumentTextOut(
        id=doc.id,
        workspace_id=doc.workspace_id,
        filename=doc.filename,
        title=doc.title,
        file_type=doc.file_type,
        source_type=doc.source_type,
        text=readable.text,
        line_count=readable.line_count,
        pages=[{"page_number": p.page_number, "line": p.line} for p in readable.pages],
        chunks=[
            {"id": c.id, "chunk_index": c.chunk_index, "section": c.section, "page_number": c.page_number,
             "line_start": c.line_start, "line_end": c.line_end}
            for c in chunks
        ],
        truncated=readable.truncated,
    )


_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}


def _document_bytes(db: Session, document_id: int):
    doc = document_service.get_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        return doc, document_service.read_file(doc)
    except (FileNotFoundError, DocumentValidationError):
        raise HTTPException(status_code=404, detail="The stored file of this document is gone")


@router.get("/{document_id}/file")
def get_document_file(document_id: int, db: Session = Depends(get_session)):
    """The original file, shown inline (the reading pane shows a PDF in the viewer of the browser)."""
    doc, data = _document_bytes(db, document_id)
    return Response(
        content=data,
        media_type=_MEDIA_TYPES.get(doc.file_type, "application/octet-stream"),
        headers={
            "Content-Disposition": "inline; filename*=UTF-8''" + quote(doc.filename.rsplit("/", 1)[-1]),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{document_id}/html", response_model=DocumentHtmlOut)
def get_document_html(document_id: int, db: Session = Depends(get_session)):
    """A Word document as HTML (headings, lists, tables, bold and italic), for the formatted view of the reading pane."""
    import io

    import mammoth

    doc, data = _document_bytes(db, document_id)
    if doc.file_type != "docx":
        raise HTTPException(status_code=415, detail="Only Word documents are converted to HTML")
    try:
        result = mammoth.convert_to_html(io.BytesIO(data))
    except Exception as exc:  # a broken or password protected file
        raise HTTPException(status_code=422, detail=f"The Word file cannot be converted: {exc}")
    return DocumentHtmlOut(html=result.value, warnings=len(result.messages))


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
def list_generated_documents(workspace_id: int | None = None, doc_kind: str | None = None, db: Session = Depends(get_session)):
    """Generated documents of one werkmap; omitted = those that belong to no werkmap.
    `doc_kind` filters by kind: "report" = made from the knowledge state, "note" = made from a Delphi chat."""
    from app.models import GeneratedDocument

    query = db.query(GeneratedDocument).filter(GeneratedDocument.workspace_id == workspace_id)
    if doc_kind is not None:
        query = query.filter(GeneratedDocument.doc_kind == doc_kind)
    return query.order_by(GeneratedDocument.id.desc()).all()


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

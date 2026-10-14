from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Document
from app.services.github.client import TEXT_EXTENSIONS
from app.services.github.service import github_ingest_service

log = get_logger(__name__)

#: Maximaal zoveel repo's per codecheck (afgesproken met Bo).
MAX_REPOS = 4

#: Extensies die als code tellen (zelfde lijst als de selectie bij import).
CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".toml",
    ".cfg", ".ini", ".html", ".css", ".sql", ".sh",
}

_SECTION_RE = re.compile(r"^## FILE:\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class DigestSection:
    path: str
    kind: str  #: "docs", "code" of "other"
    text: str


def classify_path(path: str) -> str:
    """Docs of code, aan de hand van het pad (zelfde regels als bij import)."""
    lower = path.lower()
    ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
    stem = lower.rsplit(".", 1)[0]
    if ext in TEXT_EXTENSIONS or stem.endswith("readme") or lower == "license":
        return "docs"
    if ext in CODE_EXTENSIONS or ext == ".env.example":
        return "code"
    return "other"


def split_digest(digest: str) -> list[DigestSection]:
    """Knip een repo-digest in secties per bestand (``## FILE: pad``-koppen)."""
    matches = list(_SECTION_RE.finditer(digest))
    sections: list[DigestSection] = []
    for i, m in enumerate(matches):
        body = digest[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(digest)]
        path = m.group(1).strip()
        sections.append(DigestSection(path=path, kind=classify_path(path), text=body.strip()))
    return sections


class CodecheckError(Exception):
    pass


def resolve_repo_digest(db: Session, workspace_id: int | None, ref: dict) -> tuple[Document, str]:
    """Geef (document, digest-tekst) voor een repo-verwijzing.

    ``ref`` is ``{"document_id": n}`` (al geïmporteerd) of ``{"url": ...}``
    (wordt nu geïmporteerd in dezelfde werkmap, zodat codecheck hem de
    volgende keer aanbiedt).
    """
    if "document_id" in ref:
        doc = db.get(Document, ref["document_id"])
        if doc is None or doc.workspace_id != workspace_id or doc.source_type != "github":
            raise CodecheckError("Gekozen repository hoort niet bij deze werkmap")
        content = github_ingest_service.get_document_content(doc)
        if content is None:
            raise CodecheckError(f"Kon {doc.filename} niet opnieuw ophalen van GitHub")
        return doc, content.decode("utf-8", errors="replace")
    if "url" in ref:
        result = github_ingest_service.ingest_repo(db, ref["url"], workspace_id=workspace_id)
        doc = db.get(Document, result["document_ids"][0])
        content = github_ingest_service.get_document_content(doc)
        if content is None:
            raise CodecheckError(f"Kon {result['repository']} niet lezen na het importeren")
        return doc, content.decode("utf-8", errors="replace")
    raise CodecheckError("Geef per repo een document_id of een url")

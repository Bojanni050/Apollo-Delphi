from __future__ import annotations

import datetime as dt
import json

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import AnalysisRun, Claim, Document, GeneratedDocument, Issue, Workspace

log = get_logger(__name__)


class ReportError(Exception):
    """The report cannot be built (e.g. the analysis run does not exist)."""


#: Typographic characters the built-in PDF fonts (Latin-1) do not know, mapped to a plain equivalent.
_TRANSLATIONS = str.maketrans(
    {
        "\u2018": "'", "\u2019": "'", "\u201a": ",", "\u201b": "'",
        "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
        "\u2013": "-", "\u2014": "-", "\u2015": "-", "\u2026": "...", "\u2022": "-",
        "\u20ac": "EUR", "\u00a0": " ", "\u200b": "",
    }
)


def _latin1(text: str) -> str:
    """Make text safe for the built-in PDF fonts: known punctuation is replaced, the rest falls back to '?'."""
    return text.translate(_TRANSLATIONS).encode("latin-1", "replace").decode("latin-1")


def _document_names(db: Session, document_ids: set[int]) -> dict[int, str]:
    if not document_ids:
        return {}
    rows = db.query(Document.id, Document.filename).filter(Document.id.in_(document_ids)).all()
    return {row[0]: row[1] for row in rows}


def build_report_markdown(db: Session, run: AnalysisRun) -> tuple[str, str]:
    """The report of one analysis run as (title, markdown).

    Deterministic: built from the run's own issues, claims and evidence, so it needs no model and works offline.
    """
    stats = json.loads(run.stats) if run.stats else {}
    workspace = db.get(Workspace, run.workspace_id) if run.workspace_id is not None else None
    workspace_name = workspace.name if workspace else "zonder werkmap"
    created = run.completed_at or run.started_at or dt.datetime.now(dt.timezone.utc)
    date_nl = created.strftime("%d-%m-%Y")

    title = f"Analysevindingen - {workspace_name} ({date_nl})"

    issues = db.query(Issue).filter(Issue.analysis_run_id == run.id).order_by(Issue.id).all()
    contradictions = [i for i in issues if i.issue_type == "contradiction"]
    open_questions = [i for i in issues if i.issue_type == "open_question"]

    # every document that is named anywhere in the report, in one query
    document_ids: set[int] = set()
    for issue in issues:
        for link in issue.evidence_links:
            if link.evidence is not None:
                document_ids.add(link.evidence.document_id)
        for link in issue.claim_links:
            if link.claim is not None:
                document_ids.add(link.claim.document_id)
    names = _document_names(db, document_ids)

    lines: list[str] = [f"# {title}", ""]
    lines.append(f"Werkmap: {workspace_name}")
    lines.append(f"Datum: {date_nl}")
    groups = stats.get("groups")
    lines.append(f"Beperkt tot: {', '.join(groups) if groups else 'alle documenten'}")
    lines.append("")

    lines.append("## Samenvatting")
    lines.append("")
    lines.append(f"- Documenten: {stats.get('documents_analyzed', 0)}")
    lines.append(f"- Beweringen: {stats.get('claims', 0)}")
    lines.append(f"- Open vragen: {stats.get('open_questions', 0)}")
    lines.append(f"- Tegenstrijdigheden: {stats.get('contradictions', 0)}")
    lines.append("")

    lines.append(f"## Tegenstrijdigheden ({len(contradictions)})")
    lines.append("")
    if not contradictions:
        lines.append("Geen tegenstrijdigheden gevonden.")
        lines.append("")
    for issue in contradictions:
        meta = _json_dict(issue.issue_metadata)
        key = meta.get("key") or issue.title
        value_a = meta.get("value_a", "?")
        value_b = meta.get("value_b", "?")
        lines.append(f"### {key}: {value_a} vs {value_b}")
        lines.append("")
        for link in issue.claim_links:
            claim = link.claim
            if claim is None:
                continue
            doc = names.get(claim.document_id, f"document #{claim.document_id}")
            lines.append(f"- {claim.statement} ({doc})")
        quote = _issue_quote(issue)
        if quote:
            lines.append("")
            lines.append(f"Bewijs: \"{quote}\"")
        lines.append("")

    lines.append(f"## Open vragen ({len(open_questions)})")
    lines.append("")
    if not open_questions:
        lines.append("Geen open vragen gevonden.")
        lines.append("")
    for issue in open_questions:
        question = issue.question or issue.title
        lines.append(f"### {question}")
        lines.append("")
        doc = _issue_document(issue, names)
        if doc:
            lines.append(f"Bron: {doc}")
        quote = _issue_quote(issue)
        if quote:
            lines.append("")
            lines.append(f"Bewijs: \"{quote}\"")
        lines.append("")

    return title, "\n".join(lines).strip() + "\n"


def _json_dict(raw: str | None) -> dict:
    try:
        value = json.loads(raw) if raw else {}
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _issue_quote(issue: Issue) -> str | None:
    for link in issue.evidence_links:
        if link.evidence is not None and link.evidence.original_text:
            return _one_line(link.evidence.original_text)
    return None


def _issue_document(issue: Issue, names: dict[int, str]) -> str | None:
    for link in issue.evidence_links:
        if link.evidence is not None:
            return names.get(link.evidence.document_id, f"document #{link.evidence.document_id}")
    for link in issue.claim_links:
        if link.claim is not None:
            return names.get(link.claim.document_id, f"document #{link.claim.document_id}")
    return None


def _one_line(text: str, limit: int = 400) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "\u2026"


def build_and_store_report(db: Session, analysis_run_id: int) -> GeneratedDocument:
    """Build the report of a run and store it as a generated document (so it can be downloaded again later)."""
    run = db.get(AnalysisRun, analysis_run_id)
    if run is None:
        raise ReportError("Analyse-run niet gevonden")
    title, content = build_report_markdown(db, run)
    doc = GeneratedDocument(
        workspace_id=run.workspace_id,
        title=title,
        status="drafted",
        doc_kind="report",
        outline=None,
        content=content,
        verification_status="pending",
        revision=0,
        generation_metadata=json.dumps({"analysis_run_id": run.id, "source": "analysis_report"}),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def render_pdf(markdown: str, title: str = "") -> bytes:
    """Render report markdown (headings, bullets, paragraphs) to PDF bytes.

    Uses the built-in fonts, so nothing has to be installed; typographic characters are folded to Latin-1.
    """
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    def write(size: int, style: str, line_height: int, text: str, indent: float = 0.0) -> None:
        # Always start at the left margin: multi_cell leaves the cursor on the right otherwise, and a following
        # cell would then have no width left.
        pdf.set_font("helvetica", style, size)
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(0, line_height, text=text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if title:
        pdf.set_text_color(120, 120, 120)
        write(10, "B", 5, _latin1(title))
        pdf.set_text_color(20, 20, 20)
        pdf.ln(3)

    for kind, text in _parse_markdown(markdown):
        safe = _latin1(text)
        if kind == "h1":
            pdf.ln(1)
            write(18, "B", 9, safe)
            pdf.ln(2)
        elif kind == "h2":
            pdf.ln(2)
            write(14, "B", 7, safe)
            pdf.ln(1)
        elif kind == "h3":
            pdf.ln(1)
            write(12, "B", 6, safe)
        elif kind == "bullet":
            write(11, "", 6, "- " + safe, indent=4.0)
        elif kind == "blank":
            pdf.ln(4)
        else:
            write(11, "", 6, safe)
    return bytes(pdf.output())


def _parse_markdown(markdown: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for raw_line in markdown.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            result.append(("blank", ""))
            continue
        if line.startswith("### "):
            result.append(("h3", line[4:].strip()))
        elif line.startswith("## "):
            result.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            result.append(("h1", line[2:].strip()))
        elif line.lstrip().startswith(("- ", "* ")):
            indent = "  " if line.startswith("  ") else ""
            result.append(("bullet", indent + line.lstrip()[2:].strip()))
        else:
            result.append(("paragraph", line.strip()))
    return result

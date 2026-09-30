from __future__ import annotations

import asyncio
import json
import re

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import LLMError, LLMProvider, get_llm_provider
from app.core.logging import get_logger
from app.models import AnalysisRun, GeneratedDocument, KnowledgeItem
from app.services.knowledge.service import KnowledgeService

log = get_logger(__name__)


class OutlineSection(BaseModel):
    heading: str
    points: list[str] = Field(default_factory=list)


class DocumentOutline(BaseModel):
    title: str
    sections: list[OutlineSection] = Field(default_factory=list)


class GenerationService:
    """Pipeline: resolved knowledge → requirements → outline → draft.

    The draft is synthesized from the knowledge state (not raw chunks) and each
    statement keeps traceability to knowledge items.
    """

    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm or get_llm_provider()

    async def generate(self, db: Session, title: str, analysis_run_id: int | None = None) -> GeneratedDocument:
        items = KnowledgeService().get_knowledge_state(db, analysis_run_id)
        if not items:
            raise ValueError("No knowledge state available; run an analysis first")

        outline = await self._plan(title, items)
        content = await self._draft(outline, items)

        doc = GeneratedDocument(
            title=outline.title,
            status="drafted",
            outline=outline.model_dump_json(),
            content=content,
            verification_status="pending",
            revision=0,
            generation_metadata=json.dumps(
                {
                    "analysis_run_id": items[0].analysis_run_id,
                    "knowledge_items_used": len(items),
                    "model_provider": self.llm.name,
                    "model": get_settings().llm_model,
                }
            ),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    async def _plan(self, title: str, items: list[KnowledgeItem]) -> DocumentOutline:
        if get_settings().llm_provider == "mock":
            return self._deterministic_outline(title, items)
        system = (
            "You are a document planning engine. Stage: document_planning. "
            "Build an outline for a synthesized report based strictly on the provided "
            "knowledge state. Group facts, derived conclusions and decisions into coherent "
            "sections; list unresolved questions in a dedicated final section."
        )
        user = (
            f"Report title: {title}\n\nKnowledge state:\n"
            + "\n".join(f"- [{i.item_type}] {i.statement}" for i in items)
            + "\n\nRespond as JSON {title, sections: [{heading, points: []}]}."
        )
        try:
            return await self.llm.complete_json(system, user, DocumentOutline)
        except (LLMError, ValidationError) as exc:
            log.warning("Outline planning failed (%s); falling back to deterministic outline", exc)
            return self._deterministic_outline(title, items)

    def _deterministic_outline(self, title: str, items: list[KnowledgeItem]) -> DocumentOutline:
        by_type: dict[str, list[KnowledgeItem]] = {}
        for it in items:
            by_type.setdefault(it.item_type, []).append(it)

        sections = []
        facts = by_type.get("fact", [])
        if facts:
            sections.append(OutlineSection(heading="Established Facts", points=[f.statement for f in facts]))
        conclusions = by_type.get("derived_conclusion", []) + [
            it for it in by_type.get("resolved_contradiction", [])
        ]
        if conclusions:
            sections.append(
                OutlineSection(heading="Resolved Findings", points=[f"{it.statement}" for it in conclusions])
            )
        unresolved = by_type.get("unresolved_question", []) + by_type.get("remaining_contradiction", [])
        if unresolved:
            sections.append(
                OutlineSection(
                    heading="Open Questions and Unresolved Issues",
                    points=[it.statement for it in unresolved],
                )
            )
        return DocumentOutline(title=title, sections=sections)

    async def _draft(self, outline: DocumentOutline, items: list[KnowledgeItem]) -> str:
        if get_settings().llm_provider == "mock":
            return self._deterministic_draft(outline, items)
        system = (
            "You are a document drafting engine. Stage: document_drafting. "
            "Write a coherent, readable report from the outline and knowledge state. "
            "Do not introduce facts that are not in the knowledge state. "
            "Where a statement relies on a source, cite it as [source:<id>]. "
            "Present unresolved items explicitly as unresolved; never state them as facts."
        )
        user = (
            f"Outline:\n{outline.model_dump_json()}\n\nKnowledge state (id | type | statement):\n"
            + "\n".join(f"[ki:{i.id}] {i.item_type}: {i.statement}" for i in items)
        )
        try:
            raw = await self.llm.complete(system, user)
        except LLMError as exc:
            log.warning("Drafting failed (%s); falling back to deterministic draft", exc)
            return self._deterministic_draft(outline, items)
        return _extract_markdown(raw)

    def _deterministic_draft(self, outline: DocumentOutline, items: list[KnowledgeItem]) -> str:
        by_id = {i.id: i for i in items}
        unresolved = {self._norm(it.statement) for it in items if it.item_type in ("unresolved_question", "remaining_contradiction")}
        lines = [f"# {outline.title}", ""]
        for section in outline.sections:
            lines.append(f"## {section.heading}")
            lines.append("")
            for point in section.points:
                if self._norm(point) in unresolved:
                    lines.append(f"- [UNRESOLVED] {point}")
                else:
                    lines.append(f"- {point}")
            lines.append("")
        return "\n".join(lines)

    def _norm(self, s: str) -> str:
        import re

        return re.sub(r"\s+", " ", s.strip().lower()).rstrip(".")


def _extract_markdown(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("markdown"):
            text = text[8:]
    return text.strip()

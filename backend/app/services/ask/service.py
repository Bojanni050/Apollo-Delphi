"""Ask a question in a werkmap and get an answer that cites its sources.

Pipeline: hybrid retrieval inside the werkmap -> numbered sources -> the main model answers using ONLY
those sources and marks every statement with ``[n]`` -> the answer is *checked* before it is returned:

* a marker that points at a source that was never offered is removed and reported (a model can invent a
  citation as easily as a fact; a citation the reader cannot follow is worse than none);
* an answer with no valid citation at all is marked ``grounded = false``;
* every number in the answer must occur in the sources it cites, otherwise it is reported. This catches
  the most damaging kind of mistake in documents about budgets, dates and quantities;
* when the sources do not contain the answer the model must say ``NO_ANSWER`` and the reader is told so,
  instead of receiving a plausible guess (Apollo prefers explicit uncertainty over fabricated certainty).

Nothing is hidden: the cited fragments are returned verbatim next to the answer, and every question with
its answer is stored (``qa_entries``) so it can be inspected later.

With the mock provider (offline, no language model) the answer is *extractive*: the best matching sentences
of the retrieved sources, each cited. It is labelled as such by ``model_provider = "mock"``.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import LLMProvider, get_llm_provider, tier_config
from app.core.logging import get_logger
from app.models import Document
from app.models.qa import QAEntry
from app.services.search.service import SearchService, query_terms

log = get_logger(__name__)

NO_ANSWER_MARKER = "NO_ANSWER"
NO_ANSWER_TEXT = "In de documenten van deze werkmap staat hier niets over."
MAX_SOURCE_CHARS = 1500

_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_NUMBER_RE = re.compile(r"\d[\d.,]*\d|\d")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")

SYSTEM_PROMPT = (
    "You answer questions about a collection of documents. Use ONLY the numbered sources you are given; "
    "never use outside knowledge. After every statement, cite the sources that support it as [n] "
    "(several: [1][3]). Cite only sources that really support the statement. If sources disagree, say so "
    "and cite each side. If the sources do not contain the answer, reply with exactly NO_ANSWER and nothing "
    "else. Answer in the language of the question. Be concise."
)


@dataclass
class Source:
    n: int
    chunk_id: int
    document_id: int
    document_filename: str
    page_number: int | None
    section: str | None
    excerpt: str
    line_start: int | None = None
    line_end: int | None = None
    match: str = "semantic"


@dataclass
class AnswerResult:
    entry: QAEntry
    citations: list[Source]
    warnings: list[str]
    sources_considered: int


# -- pure helpers (unit tested) ----------------------------------------------------------------------


def parse_citations(text: str, source_count: int) -> tuple[str, list[int], list[int]]:
    """Return (text without invalid markers, valid cited numbers in first-use order, invalid numbers)."""
    valid: list[int] = []
    invalid: list[int] = []

    def keep(match: re.Match) -> str:
        numbers = [int(x) for x in re.split(r"\s*,\s*", match.group(1))]
        good = [n for n in numbers if 1 <= n <= source_count]
        for n in numbers:
            if n in good:
                if n not in valid:
                    valid.append(n)
            elif n not in invalid:
                invalid.append(n)
        return "".join(f"[{n}]" for n in good)  # a marker with only bad numbers disappears entirely

    cleaned = _CITATION_RE.sub(keep, text)
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)  # tidy the gap a removed marker leaves
    return cleaned, valid, invalid


def _normalise_number(token: str) -> str:
    return re.sub(r"[.,]", "", token)


def numbers_in(text: str) -> set[str]:
    """Numbers as digit strings with thousands/decimal separators removed ('250,000' and '250.000' agree)."""
    without_markers = _CITATION_RE.sub(" ", text)
    return {_normalise_number(t) for t in _NUMBER_RE.findall(without_markers)}


def unsupported_numbers(answer: str, source_texts: list[str]) -> list[str]:
    """Numbers (two or more digits) in the answer that appear in none of the given sources."""
    known: set[str] = set()
    for text in source_texts:
        known |= numbers_in(text)
    return sorted(n for n in numbers_in(answer) if len(n) >= 2 and n not in known)


def best_sentence(question: str, text: str) -> tuple[str, int]:
    """The sentence of ``text`` sharing the most search terms with ``question`` (and that overlap)."""
    terms = set(query_terms(question))
    best, best_overlap = "", 0
    for sentence in (s.strip() for s in _SENTENCE_RE.split(text)):
        if not sentence:
            continue
        words = {w.strip(".,'-").lower() for w in re.findall(r"\w[\w.,'-]*\w|\w", sentence)}
        overlap = len(terms & words)
        if overlap > best_overlap:
            best, best_overlap = sentence, overlap
    return best, best_overlap


def extractive_answer(question: str, sources: list[Source], max_sentences: int = 3) -> str | None:
    """Offline answer: the best matching sentence of the top sources, each cited. None when nothing matches."""
    parts: list[tuple[int, str]] = []
    for source in sources:
        sentence, overlap = best_sentence(question, source.excerpt)
        if overlap and sentence:
            parts.append((overlap, f"{sentence.rstrip('.')}. [{source.n}]"))
    if not parts:
        return None
    parts.sort(key=lambda p: -p[0])  # stable: equal overlap keeps retrieval order
    return " ".join(text for _, text in parts[:max_sentences])


def build_prompt(question: str, sources: list[Source]) -> str:
    lines = ["Sources:"]
    for s in sources:
        where = f"file: {s.document_filename}" + (f", page {s.page_number}" if s.page_number else "")
        lines.append(f"[{s.n}] ({where})\n{s.excerpt}")
    lines.append(f"\nQuestion: {question}")
    return "\n\n".join(lines)


# -- service -----------------------------------------------------------------------------------------


class AskService:
    def __init__(self, search: SearchService | None = None, llm: LLMProvider | None = None):
        self.search = search or SearchService()
        self._llm = llm

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = get_llm_provider("main")
        return self._llm

    async def ask(self, db: Session, question: str, workspace_id: int | None = None) -> AnswerResult:
        question = question.strip()
        settings = get_settings()
        scope = [r[0] for r in db.query(Document.id).filter(Document.workspace_id == workspace_id)]
        hits = await self.search.search(db, question, top_k=settings.ask_top_k, document_ids=scope) if scope else []
        sources = [
            Source(
                n=i,
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_filename=h.document_filename,
                page_number=h.page_number,
                section=h.section,
                line_start=h.line_start,
                line_end=h.line_end,
                excerpt=h.excerpt[:MAX_SOURCE_CHARS],
                match=h.match,
            )
            for i, h in enumerate(hits, start=1)
        ]
        cfg = tier_config("main")
        provider_name = cfg.provider
        mode = self.search.mode_used if scope else "hybrid"

        warnings: list[str] = []
        answered, grounded, cited_numbers = True, True, []
        llm = self.llm if sources else None  # no sources: no model call (and no need for one to be configured)
        if llm is not None:
            provider_name = llm.name
        if not sources:
            answer, answered = NO_ANSWER_TEXT, False
        elif llm.name == "mock":
            text = extractive_answer(question, sources)
            if text is None:
                answer, answered = NO_ANSWER_TEXT, False
            else:
                answer, cited_numbers, _ = parse_citations(text, len(sources))
        else:
            raw = (await llm.complete(SYSTEM_PROMPT, build_prompt(question, sources))).strip()
            if raw.upper().startswith(NO_ANSWER_MARKER):
                answer, answered = NO_ANSWER_TEXT, False
            else:
                answer, cited_numbers, invalid = parse_citations(raw, len(sources))
                for n in invalid:
                    warnings.append(f"Het antwoord verwees naar bron [{n}], die niet bestaat; die verwijzing is verwijderd.")
                if not cited_numbers:
                    grounded = False
                    warnings.append("Het antwoord bevat geen geldige bronvermelding en is daarom niet te controleren.")

        citations = [s for s in sources if s.n in cited_numbers]
        if answered:
            checked_against = citations or sources
            for number in unsupported_numbers(answer, [s.excerpt for s in checked_against]):
                grounded = False
                warnings.append(
                    f"Het getal {number} staat niet in de aangehaalde bronnen: controleer het antwoord zelf."
                )

        entry = QAEntry(
            workspace_id=workspace_id,
            question=question,
            answer=answer,
            answered=answered,
            grounded=grounded,
            citations=json.dumps([asdict(c) for c in citations], ensure_ascii=False),
            warnings=json.dumps(warnings, ensure_ascii=False),
            search_mode=mode,
            model_provider=provider_name,
            model_name=cfg.model,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return AnswerResult(entry=entry, citations=citations, warnings=warnings, sources_considered=len(sources))

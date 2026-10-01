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

A question can follow up on an earlier answer. The earlier turns of the conversation are then used for two
things only: the follow-up is rewritten into a question that stands on its own (so "And when is it due?" can
retrieve the right fragments), and the model sees the turns as context for what is being asked. They are never a
source: every statement must still be backed by a freshly retrieved, numbered fragment, and the checks above
apply unchanged.

With the mock provider (offline, no language model) the answer is *extractive*: the best matching sentences
of the retrieved sources, each cited. It is labelled as such by ``model_provider = "mock"``.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import LLMError, LLMProvider, get_llm_provider, tier_config
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
MAX_STANDALONE_CHARS = 500

SYSTEM_PROMPT = (
    "You answer questions about a collection of documents. Use ONLY the numbered sources you are given; "
    "never use outside knowledge. After every statement, cite the sources that support it as [n] "
    "(several: [1][3]). Cite only sources that really support the statement. If sources disagree, say so "
    "and cite each side. If the sources do not contain the answer, reply with exactly NO_ANSWER and nothing "
    "else. Answer in the language of the question. Be concise."
)

REWRITE_SYSTEM_PROMPT = (
    "You rewrite the last question of a conversation so that it can be understood without the conversation: "
    "replace pronouns and references like 'it', 'that', 'and then' by what they refer to. Keep the language "
    "of the question. Do not answer it and do not add anything that was not asked. Reply with the rewritten "
    "question only."
)


@dataclass
class Turn:
    """One earlier question of the conversation and the answer it received."""

    question: str
    answer: str
    #: What retrieval searched for, when that question was itself a follow-up.
    standalone: str | None = None


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


def strip_citations(text: str) -> str:
    """The text without [n] markers: the numbers of an earlier answer mean nothing in a new set of sources."""
    return re.sub(r"[ \t]+([.,;:!?])", r"\1", _CITATION_RE.sub("", text)).strip()


def fallback_standalone(turns: list[Turn], question: str) -> str:
    """Offline rewrite: the previous question's topic in front of the follow-up, so retrieval still finds it."""
    if not turns:
        return question
    last = turns[-1]
    return f"{last.standalone or last.question} {question}"[:MAX_STANDALONE_CHARS]


def _conversation_lines(turns: list[Turn]) -> list[str]:
    lines = []
    for t in turns:
        lines.append(f"Q: {t.question}")
        lines.append(f"A: {strip_citations(t.answer)}")
    return lines


def build_rewrite_prompt(turns: list[Turn], question: str) -> str:
    return "\n".join(["Conversation:", *_conversation_lines(turns), "", f"Last question: {question}"])


def build_prompt(question: str, sources: list[Source], turns: list[Turn] | None = None, standalone: str | None = None) -> str:
    parts = []
    if turns:
        parts.append(
            "Conversation so far (context for the question only; it is NOT a source and must not be cited):\n"
            + "\n".join(_conversation_lines(turns))
        )
    lines = ["Sources:"]
    for s in sources:
        where = f"file: {s.document_filename}" + (f", page {s.page_number}" if s.page_number else "")
        lines.append(f"[{s.n}] ({where})\n{s.excerpt}")
    parts.append("\n\n".join(lines))
    asked = f"Question: {question}"
    if standalone and standalone != question:
        asked += f"\n(The question on its own: {standalone})"
    parts.append(asked)
    return "\n\n".join(parts)


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

    def _turns(self, db: Session, parent: QAEntry | None) -> list[Turn]:
        """The conversation leading up to ``parent`` (inclusive), oldest first, at most ``ask_history_turns``."""
        turns: list[Turn] = []
        seen: set[int] = set()
        entry = parent
        while entry is not None and len(turns) < get_settings().ask_history_turns and entry.id not in seen:
            seen.add(entry.id)
            turns.append(Turn(entry.question, entry.answer, entry.standalone_question))
            entry = db.get(QAEntry, entry.parent_id) if entry.parent_id else None
        return list(reversed(turns))

    async def _standalone(self, turns: list[Turn], question: str) -> str:
        """Rewrite a follow-up into a question that stands on its own; falls back to a keyword-style join."""
        if self.llm.name != "mock":
            try:
                rewritten = (await self.llm.complete(REWRITE_SYSTEM_PROMPT, build_rewrite_prompt(turns, question))).strip()
            except LLMError as exc:
                log.warning("Could not rewrite follow-up question (%s); using the fallback", exc)
            else:
                rewritten = rewritten.splitlines()[0].strip() if rewritten else ""
                if rewritten and len(rewritten) <= MAX_STANDALONE_CHARS:
                    return rewritten
        return fallback_standalone(turns, question)

    async def ask(
        self, db: Session, question: str, workspace_id: int | None = None, parent: QAEntry | None = None
    ) -> AnswerResult:
        question = question.strip()
        settings = get_settings()
        turns = self._turns(db, parent)
        standalone = await self._standalone(turns, question) if turns else None
        search_query = standalone or question
        scope = [r[0] for r in db.query(Document.id).filter(Document.workspace_id == workspace_id)]
        hits = await self.search.search(db, search_query, top_k=settings.ask_top_k, document_ids=scope) if scope else []
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
            text = extractive_answer(search_query, sources)
            if text is None:
                answer, answered = NO_ANSWER_TEXT, False
            else:
                answer, cited_numbers, _ = parse_citations(text, len(sources))
        else:
            raw = (await llm.complete(SYSTEM_PROMPT, build_prompt(question, sources, turns, standalone))).strip()
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
            parent_id=parent.id if parent else None,
            question=question,
            standalone_question=standalone,
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

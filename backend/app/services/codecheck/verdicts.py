from __future__ import annotations

import asyncio
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import LLMError, LLMProvider, get_llm_provider
from app.core.logging import get_logger
from app.models import Document, DocumentChunk
from app.services.analysis.claim_extraction import ExtractedClaim, get_claim_extractor
from app.services.codecheck.progress import codecheck_progress
from app.services.codecheck.service import (
    MAX_REPOS,
    CodecheckError,
    DigestSection,
    resolve_repo_digest,
    split_digest,
)

log = get_logger(__name__)

#: Hooguit zoveel documenten per check ("een paar", ook een kostengrens:
#: elk document levert beweringen die elk een oordeel kosten).
MAX_DOCUMENTS = 10

#: Hooguit zoveel beweringen per check: elk oordeel is een LLM-aanroep.
MAX_CLAIMS = 50

#: Bewijsstukken per bewering.
EVIDENCE_TOP_K = 3

#: Teken per bewijsfragment (lokaal modelvriendelijk).
SNIPPET_CHARS = 600

Verdict = Literal["bevestigd", "tegengesproken", "niet_gevonden"]


class CodeEvidence(BaseModel):
    repo: str = Field(description="Bestandsnaam van het repo-document (github:owner/repo@branch)")
    path: str = Field(description="Pad van het codebestand in de repo")
    snippet: str = Field(description="Fragment code als bewijs")
    score: int = Field(description="Aantal overlappende termen (hoger = sterker)")


class CheckedClaim(BaseModel):
    document_id: int
    filename: str
    statement: str
    quote: str
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None
    #: "llm" of "heuristic" (offline/mock, of geen overlappende code: dan valt er niets te beoordelen).
    method: Literal["llm", "heuristic"] = "heuristic"
    evidence: list[CodeEvidence] = Field(default_factory=list)


class SkippedDocument(BaseModel):
    document_id: int
    filename: str
    reason: str


class CodecheckSummary(BaseModel):
    documents: int = 0
    repos: int = 0
    claims: int = 0
    bevestigd: int = 0
    tegengesproken: int = 0
    niet_gevonden: int = 0
    #: True als er meer beweringen waren dan MAX_CLAIMS (alleen de eerste zijn getoetst).
    truncated: bool = False


class CodecheckResult(BaseModel):
    repos: list[str] = Field(default_factory=list)
    checked: list[CheckedClaim] = Field(default_factory=list)
    skipped_documents: list[SkippedDocument] = Field(default_factory=list)
    summary: CodecheckSummary = Field(default_factory=CodecheckSummary)


class CodecheckJudgeVerdict(BaseModel):
    verdict: Verdict
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str | None = None


_TOKEN_RE = re.compile(r"[a-z0-9]+")

#: Vulwoorden die niets zeggen over overeenkomst (Nederlands + Engels + code-ruis).
_STOPWORDS = frozenset(
    "de het een van en of in op te is zijn was worden wordt met voor door als ook niet geen dit die dat deze deze eraan erbij "
    "the a an of and or in on to is are was were be been with for by as also not no this that these those it its into over under "
    "from file src lib var tmp usr home app data true false null none new".split()
)


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2 and t not in _STOPWORDS}


def _window(text: str, tokens: set[str], size: int = SNIPPET_CHARS) -> str:
    """Fragment rond de eerste termtreffer (deterministisch)."""
    lower = text.lower()
    hits = [lower.find(t) for t in tokens if len(t) >= 2]
    hits = [h for h in hits if h != -1]
    if not hits:
        return text[:size].strip()
    start = max(0, min(hits) - size // 3)
    return text[start : start + size].strip()


def find_evidence(
    statement: str,
    value: str | None,
    code_sections: list[tuple[str, DigestSection]],
    top_k: int = EVIDENCE_TOP_K,
) -> list[CodeEvidence]:
    """Zoek code die over de bewering gaat: termoverlap (+bonus bij letterlijke waarde).

    Deterministisch en offline bruikbaar; het oordeel (llm of heuristisch)
    gebruikt dit als bewijs. Zonder overlap is er geen bewijs.
    """
    claim_tokens = _tokens(statement)
    if value and len(value) >= 3:
        claim_tokens |= _tokens(value)
    if not claim_tokens:
        return []
    scored: list[CodeEvidence] = []
    for repo, section in code_sections:
        section_tokens = _tokens(section.text)
        overlap = claim_tokens & section_tokens
        score = len(overlap)
        literal = bool(value and len(value) >= 3 and value.lower() in section.text.lower())
        if literal:
            score += 4
        if score > 0:
            scored.append(
                CodeEvidence(
                    repo=repo,
                    path=section.path,
                    snippet=_window(section.text, claim_tokens | ({value.lower()} if value else set())),
                    score=score,
                )
            )
    scored.sort(key=lambda e: (-e.score, e.path))
    return scored[:top_k]


def heuristic_verdict(statement: str, value: str | None, evidence: list[CodeEvidence]) -> CodecheckJudgeVerdict:
    """Offline oordeel (mock-stand): alleen wat letterlijk aantoonbaar is.

    Een heuristiek kan nooit een tegenspraak vaststellen (daar is begrip
    voor nodig), dus het antwoord is "bevestigd" bij sterk bewijs en anders
    "niet_gevonden". Eerlijk in plaats van slim.
    """
    if not evidence:
        return CodecheckJudgeVerdict(
            verdict="niet_gevonden",
            confidence=0.2,
            reasoning="Geen overlappende code gevonden voor deze bewering.",
        )
    top = evidence[0]
    literal = bool(value and len(value) >= 3 and value.lower() in top.snippet.lower())
    if top.score >= 5 or literal:
        return CodecheckJudgeVerdict(
            verdict="bevestigd",
            confidence=0.55,
            reasoning=f"De termen uit de bewering komen voor in {top.path} (offline oordeel, geen model).",
        )
    return CodecheckJudgeVerdict(
        verdict="niet_gevonden",
        confidence=0.4,
        reasoning=f"Alleen zwakke overlap met {top.path}; te weinig voor een oordeel.",
    )


class CodecheckEngine:
    """Toets beweringen uit documenten aan code uit repo's.

    Beweringen komen uit de bestaande claim-extractie (LLM of heuristisch
    bij mock), bewijs uit slice-1-codesecties via termoverlap, het oordeel
    van het redeneer-model (main-tier) of van de heurisitiek bij mock.
    """

    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm

    async def run(
        self,
        db: Session,
        workspace_id: int | None,
        document_ids: list[int],
        repo_refs: list[dict],
        run_id: int | None = None,
    ) -> CodecheckResult:
        if not document_ids:
            raise CodecheckError("Kies minstens één document om te toetsen")
        if len(document_ids) > MAX_DOCUMENTS:
            raise CodecheckError(f"Hooguit {MAX_DOCUMENTS} documenten per check")
        if not repo_refs:
            raise CodecheckError("Kies minstens één repository om tegen te toetsen")
        if len(repo_refs) > MAX_REPOS:
            raise CodecheckError(f"Hooguit {MAX_REPOS} repositories per check")

        docs = self._load_docs(db, workspace_id, document_ids)
        codecheck_progress.update(run_id, stage="lezen", documents_total=len(docs))
        codecheck_progress.event(run_id, "stage", f"Repositories lezen ({len(repo_refs)})")
        code_sections = self._load_code(db, workspace_id, repo_refs)
        codecheck_progress.event(run_id, "stage", f"Code ingelezen ({len(code_sections)} bestanden); beweringen zoeken")

        extractor = get_claim_extractor()
        claims: list[tuple[Document, ExtractedClaim]] = []
        skipped: list[SkippedDocument] = []
        for number, doc in enumerate(docs, start=1):
            codecheck_progress.update(run_id, current_document=doc.filename)
            codecheck_progress.event(run_id, "document", f"Beweringen zoeken in {doc.filename} ({number} van {len(docs)})")
            text = self._doc_text(db, doc)
            if not text.strip():
                skipped.append(
                    SkippedDocument(
                        document_id=doc.id,
                        filename=doc.filename,
                        reason="geen tekst gevonden (document nog niet gelezen?)",
                    )
                )
                codecheck_progress.update(run_id, documents_done=number)
                continue
            # De LLM-extractor beheert zijn eigen event-loop; in async-context via een thread.
            before = len(claims)
            for claim in await asyncio.to_thread(extractor.extract, text):
                claims.append((doc, claim))
            codecheck_progress.update(run_id, documents_done=number)
            codecheck_progress.event(run_id, "stage", f"{doc.filename}: {len(claims) - before} beweringen")

        truncated = len(claims) > MAX_CLAIMS
        claims = claims[:MAX_CLAIMS]

        use_llm = get_settings().llm_provider != "mock"
        llm = self.llm or (get_llm_provider() if use_llm else None)

        codecheck_progress.update(run_id, stage="toetsen", current_document=None)
        codecheck_progress.event(run_id, "stage", f"Toetsen: {len(claims)} beweringen tegen de code")

        checked: list[CheckedClaim] = []
        for doc, claim in claims:
            evidence = find_evidence(claim.statement, claim.value, code_sections)
            if not evidence:
                result_claim = CheckedClaim(
                    document_id=doc.id,
                    filename=doc.filename,
                    statement=claim.statement,
                    quote=claim.quote,
                    verdict="niet_gevonden",
                    confidence=0.2,
                    reasoning=(
                        "De repositories bevatten geen code"
                        if not code_sections
                        else "Geen overlappende code gevonden voor deze bewering"
                    ),
                    method="heuristic",
                    evidence=[],
                )
            elif not use_llm:
                judged = heuristic_verdict(claim.statement, claim.value, evidence)
                result_claim = self._checked(doc, claim, judged, evidence, method="heuristic")
            else:
                assert llm is not None
                result_claim = await self._judge(llm, doc, claim, evidence)
            checked.append(result_claim)
            codecheck_progress.add_result(run_id, result_claim)

        counts = {"bevestigd": 0, "tegengesproken": 0, "niet_gevonden": 0}
        for c in checked:
            counts[c.verdict] += 1
        result = CodecheckResult(
            repos=sorted({repo for repo, _ in code_sections}),
            checked=checked,
            skipped_documents=skipped,
            summary=CodecheckSummary(
                documents=len(docs),
                repos=len(repo_refs),
                claims=len(checked),
                truncated=truncated,
                **counts,
            ),
        )
        codecheck_progress.finish(run_id, result)
        return result

    def _load_docs(self, db: Session, workspace_id: int | None, document_ids: list[int]) -> list[Document]:
        docs: list[Document] = []
        for doc_id in document_ids:
            doc = db.get(Document, doc_id)
            if doc is None or doc.workspace_id != workspace_id:
                raise CodecheckError(f"Document {doc_id} hoort niet bij deze werkmap")
            if doc.source_type == "github":
                raise CodecheckError(
                    f"{doc.filename} is een repository-overzicht; kies geüploade documenten als docs en repo's via repos"
                )
            docs.append(doc)
        return docs

    def _load_code(
        self, db: Session, workspace_id: int | None, repo_refs: list[dict]
    ) -> list[tuple[str, DigestSection]]:
        sections: list[tuple[str, DigestSection]] = []
        for ref in repo_refs:
            doc, digest = resolve_repo_digest(db, workspace_id, ref)
            for section in split_digest(digest):
                if section.kind == "code":
                    sections.append((doc.filename, section))
        return sections

    @staticmethod
    def _doc_text(db: Session, doc: Document) -> str:
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
        return "\n\n".join(c.content for c in chunks if c.content)

    @staticmethod
    def _checked(
        doc: Document,
        claim: ExtractedClaim,
        judged: CodecheckJudgeVerdict,
        evidence: list[CodeEvidence],
        method: Literal["llm", "heuristic"],
    ) -> CheckedClaim:
        return CheckedClaim(
            document_id=doc.id,
            filename=doc.filename,
            statement=claim.statement,
            quote=claim.quote,
            verdict=judged.verdict,
            confidence=judged.confidence,
            reasoning=judged.reasoning,
            method=method,
            evidence=evidence,
        )

    async def _judge(
        self, llm: LLMProvider, doc: Document, claim: ExtractedClaim, evidence: list[CodeEvidence]
    ) -> CheckedClaim:
        system = (
            "You are a code-compliance checker. Stage: codecheck_judge. "
            "Given one documented claim and code excerpts, judge whether the code confirms it, "
            "contradicts it, or says nothing about it. Never invent code. "
            "Prefer niet_gevonden over a forced verdict."
        )
        lines = [f"Claim: {claim.statement}"]
        if claim.value:
            lines.append(f"Value: {claim.value}")
        lines.append("")
        for i, ev in enumerate(evidence):
            lines.append(f"[Code {i}] {ev.repo} {ev.path}:\n{ev.snippet}")
        lines.append("")
        lines.append(
            'Respond as JSON with keys verdict ("bevestigd", "tegengesproken" or "niet_gevonden"), '
            "confidence (0-1) and reasoning."
        )
        try:
            judged = await llm.complete_json(system, "\n".join(lines), CodecheckJudgeVerdict)
            return self._checked(doc, claim, judged, evidence, method="llm")
        except (LLMError, ValidationError) as exc:
            log.warning("Codecheck-oordeel mislukt voor '%s': %s", claim.statement[:80], exc)
            return CheckedClaim(
                document_id=doc.id,
                filename=doc.filename,
                statement=claim.statement,
                quote=claim.quote,
                verdict="niet_gevonden",
                confidence=0.0,
                reasoning="Het oordeel-model gaf geen bruikbaar antwoord, dus deze bewering blijft ongetoetst.",
                method="llm",
                evidence=evidence,
            )

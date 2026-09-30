from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import GeneratedDocument, KnowledgeItem, VerificationFinding

log = get_logger(__name__)


class VerificationService:
    """Verifies a generated document against the knowledge state.

    Checks: unsupported claims (statements not traceable to knowledge),
    unresolved items presented as facts, contradictions with resolved
    knowledge, and duplicated information. Returns structured findings.
    """

    def verify(self, db: Session, doc: GeneratedDocument, knowledge: list[KnowledgeItem]) -> list[VerificationFinding]:
        findings: list[VerificationFinding] = []
        statements = self._statements(doc.content or "")
        known = {self._norm(k.statement): k for k in knowledge}
        unresolved = {self._norm(k.statement) for k in knowledge if k.item_type in ("unresolved_question", "remaining_contradiction")}

        for statement in statements:
            s = self._norm(statement)
            if not s:
                continue
            if statement.strip().startswith("[UNRESOLVED]"):
                continue
            if s in unresolved:
                findings.append(
                    VerificationFinding(
                        generated_document_id=doc.id,
                        severity="error",
                        finding_type="unresolved_presented_as_fact",
                        statement=statement,
                        evidence=None,
                        expected="The statement should be presented as unresolved.",
                        recommendation="Rewrite the statement to reflect that it is unresolved.",
                    )
                )
                continue
            if not self._supported(s, known):
                findings.append(
                    VerificationFinding(
                        generated_document_id=doc.id,
                        severity="warning",
                        finding_type="unsupported_claim",
                        statement=statement,
                        evidence=None,
                        expected="Every factual statement should trace to a knowledge item.",
                        recommendation="Remove the statement or add supporting evidence to the knowledge state.",
                    )
                )

        dupes = self._duplicates(statements)
        for dupe in dupes:
            findings.append(
                VerificationFinding(
                    generated_document_id=doc.id,
                    severity="info",
                    finding_type="duplicated_information",
                    statement=dupe,
                    recommendation="Remove the duplicated statement.",
                )
            )

        for f in findings:
            f.generated_document_id = doc.id
            db.add(f)
        errors = sum(1 for f in findings if f.severity == "error")
        warnings = sum(1 for f in findings if f.severity == "warning")
        if errors:
            doc.verification_status = "failed"
        elif warnings:
            doc.verification_status = "passed_with_warnings"
        else:
            doc.verification_status = "passed"
        db.commit()
        return findings

    def _statements(self, content: str) -> list[str]:
        bullets = re.findall(r"^\s*[-*]\s+(.+)$", content, re.MULTILINE)
        return [b.strip() for b in bullets if b.strip()]

    def _norm(self, s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower()).rstrip(".")

    def _supported(self, statement_norm: str, known: dict[str, KnowledgeItem]) -> bool:
        for k_norm, k in known.items():
            if k_norm == statement_norm:
                return True
            if k.item_type in ("fact", "resolved_contradiction", "derived_conclusion", "decision") and (
                k_norm in statement_norm or statement_norm in k_norm
            ):
                return True
        return False

    def _duplicates(self, statements: list[str]) -> list[str]:
        seen: dict[str, int] = {}
        for s in statements:
            key = self._norm(s)
            seen[key] = seen.get(key, 0) + 1
        return [s for s in statements if seen[self._norm(s)] > 1]

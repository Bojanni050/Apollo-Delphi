from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.logging import get_logger

from ..analysis.claim_extraction import ExtractedClaim, normalize_value

log = get_logger(__name__)

_QUESTION_MARKERS = re.compile(
    r"\bTBD\b|\bto be determined\b|\bto be decided\b|\bunknown\b|\bunclear\b|"
    r"\bnot yet (?:decided|confirmed|determined)\b|\bopen question\b|\bneeds? to be clarified\b",
    re.IGNORECASE,
)


@dataclass
class DetectedOpenQuestion:
    question: str
    marker: str
    source_quote: str


@dataclass
class DetectedContradiction:
    claim_a: ExtractedClaim
    claim_b: ExtractedClaim
    key: str
    value_a: str
    value_b: str


def detect_open_questions(text: str) -> list[DetectedOpenQuestion]:
    """Detect passages that explicitly signal unanswered questions."""
    found: list[DetectedOpenQuestion] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n{2,}", text):
        s = sentence.strip()
        if not s:
            continue
        m = _QUESTION_MARKERS.search(s)
        if m:
            found.append(DetectedOpenQuestion(question=s, marker=m.group(0), source_quote=s))
    return found


def claim_key(claim: ExtractedClaim) -> str | None:
    if claim.subject and claim.value:
        subject = re.sub(r"\s+", " ", claim.subject.strip().lower())
        subject = re.sub(r"^(the|a|an)\s+", "", subject)
        return subject
    return None


def detect_contradictions(claims: list[tuple[ExtractedClaim, int]]) -> list[DetectedContradiction]:
    """Detect conflicting claims: same subject+predicate, different normalized values.

    ``claims`` is a list of (claim, document_id). Claims from the same document
    are not treated as cross-source contradictions.
    """
    by_key: dict[str, list[tuple[ExtractedClaim, int]]] = {}
    for claim, doc_id in claims:
        key = claim_key(claim)
        if not key:
            continue
        by_key.setdefault(key, []).append((claim, doc_id))

    contradictions: list[DetectedContradiction] = []
    seen_pairs: set[tuple[str, str]] = set()
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, doc_a = group[i]
                b, doc_b = group[j]
                if doc_a == doc_b:
                    continue
                if not a.value or not b.value:
                    continue
                va, vb = normalize_value(a.value), normalize_value(b.value)
                if va == vb:
                    continue
                pair_key = tuple(sorted([a.quote, b.quote]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                contradictions.append(
                    DetectedContradiction(claim_a=a, claim_b=b, key=key, value_a=va, value_b=vb)
                )
    return contradictions

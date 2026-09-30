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


def _category(claim: ExtractedClaim) -> str | None:
    if claim.qualifiers and claim.qualifiers.startswith("category:"):
        return claim.qualifiers.split(":", 1)[1]
    return None


def _subjects_related(a: str, b: str) -> bool:
    """True when one subject contains the other ('frontend' vs 'apollo frontend')."""
    return a in b or b in a


def detect_entity_contradictions(claims: list[tuple[ExtractedClaim, int]]) -> list[DetectedContradiction]:
    """Detect conflicting technology claims across documents.

    Two claims contradict when they concern the same category (framework,
    database, ...) with related subjects but assert different entities,
    e.g. 'the frontend is Vue' vs 'the frontend is React'.
    """
    contradictions: list[DetectedContradiction] = []
    seen_pairs: set[tuple[str, str]] = set()
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            a, doc_a = claims[i]
            b, doc_b = claims[j]
            if doc_a == doc_b:
                continue
            cat_a, cat_b = _category(a), _category(b)
            if not cat_a or cat_a != cat_b:
                continue
            if a.value is None or b.value is None:
                continue
            va, vb = a.value.strip().lower(), b.value.strip().lower()
            if va == vb:
                continue
            key_a = claim_key(a)
            key_b = claim_key(b)
            if not key_a or not key_b or not _subjects_related(key_a, key_b):
                continue
            pair_key = tuple(sorted([a.quote, b.quote]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            contradictions.append(
                DetectedContradiction(claim_a=a, claim_b=b, key=f"{key_a}:{cat_a}", value_a=va, value_b=vb)
            )
    return contradictions


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

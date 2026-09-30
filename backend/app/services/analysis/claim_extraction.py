from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.llm import LLMError, LLMProvider, get_llm_provider
from app.core.logging import get_logger

log = get_logger(__name__)


class ExtractedClaim(BaseModel):
    statement: str = Field(description="A single factual statement from the text")
    subject: str | None = Field(default=None, description="Subject/entity the claim is about")
    predicate: str | None = Field(default=None, description="What is asserted about the subject")
    value: str | None = Field(default=None, description="The asserted value, if any")
    unit: str | None = Field(default=None, description="Unit of the value, if any")
    qualifiers: str | None = Field(default=None, description="Conditions or temporal qualifiers")
    quote: str = Field(description="The supporting passage in the source text")
    confidence: float = Field(default=0.6)


class ClaimList(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)


class ClaimExtractorBackend(ABC):
    name: str = "base"

    @abstractmethod
    def extract(self, text: str) -> list[ExtractedClaim]:
        ...


class LLMClaimExtractor(ClaimExtractorBackend):
    """Extracts claims using structured LLM output validated against Pydantic."""

    name = "llm"

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_llm_provider("background")

    def extract(self, text: str) -> list[ExtractedClaim]:
        if not text.strip():
            return []
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._extract_async(text))
        finally:
            loop.close()

    async def _extract_async(self, text: str) -> list[ExtractedClaim]:
        system = (
            "You are a precise information-extraction engine. Stage: claim_extraction. "
            "Extract explicit factual claims from the user-provided document text. "
            "Only extract statements directly supported by the text; never invent facts. "
            "For each claim include the exact supporting quote."
        )
        all_claims: list[ExtractedClaim] = []
        for start in range(0, len(text), 6000):
            window = text[start : start + 6000]
            user = (
                "Extract all factual claims from the following text and respond as "
                f'JSON {{"claims": [...]}} matching the schema.\n\n{window}'
            )
            try:
                result = await self.provider.complete_json(system, user, ClaimList)
            except (LLMError, ValidationError) as exc:
                log.warning("Claim extraction window failed: %s", exc)
                continue
            all_claims.extend(result.claims)
        return all_claims


_VALUE_RE = re.compile(
    r"^(?P<subject>.+?)\s+(?P<predicate>is|are|was|were|will be|has|have|costs?|totals?|in|of)\s+"
    r"(?P<value>[\d.,]+)\s*(?P<unit>[%€$£]|percent|EUR|USD|weeks?|days?|months?|hours?|people|persons)?\b(?P<rest>.*)$",
    re.IGNORECASE,
)
_QUESTION_MARKERS = re.compile(
    r"\bTBD\b|\bto be determined\b|\bto be decided\b|\bunknown\b|\bunclear\b|\bnot yet (?:decided|confirmed|determined)\b",
    re.IGNORECASE,
)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


class HeuristicClaimExtractor(ClaimExtractorBackend):
    """Deterministic, pattern-based extraction used with the mock LLM provider.

    A real analyzer operating on actual document text so the full pipeline is
    functional offline. Extracted claims are labeled extractor=heuristic.
    """

    name = "heuristic"

    def extract(self, text: str) -> list[ExtractedClaim]:
        claims: list[ExtractedClaim] = []
        seen_quotes: set[str] = set()
        for claim in self._extract_table_rows(text):
            if claim.quote not in seen_quotes:
                seen_quotes.add(claim.quote)
                claims.append(claim)
        for sentence in _sentences(text):
            s = sentence.strip()
            if len(s) < 10:
                continue
            m = _VALUE_RE.match(s)
            if not m:
                entity_claim = extract_entity_claim(s)
                if entity_claim is not None and entity_claim.quote not in seen_quotes:
                    seen_quotes.add(entity_claim.quote)
                    claims.append(entity_claim)
                continue
            subject = m.group("subject").strip().rstrip(",:;")
            value = m.group("value")
            unit = (m.group("unit") or "").strip() or None
            if unit and unit.lower() == "percent":
                unit = "%"
            rest = (m.group("rest") or "").strip()
            if len(rest) > 120:
                rest = rest[:120]
            if s in seen_quotes:
                continue
            seen_quotes.add(s)
            claims.append(
                ExtractedClaim(
                    statement=s,
                    subject=subject,
                    predicate=m.group("predicate").lower(),
                    value=value,
                    unit=unit,
                    qualifiers=rest or None,
                    quote=s,
                    confidence=0.7,
                )
            )
        return claims


def normalize_value(value: str) -> str:
    cleaned = value.replace(",", "").strip()
    try:
        num = float(cleaned)
        return str(int(num)) if num == int(num) else str(num)
    except ValueError:
        return cleaned.lower()


def get_claim_extractor() -> ClaimExtractorBackend:
    if get_settings().llm_provider == "mock":
        return HeuristicClaimExtractor()
    return LLMClaimExtractor()


_ENTITY_CLAIM_RE = re.compile(
    r"^(?P<subject>.+?)\s+(?P<predicate>written in|built with|powered by|supports?|uses?|is|are|was|were)\s+"
    r"(?P<value>[A-Za-z][A-Za-z0-9 .+/#-]{0,40})\.?\s*$",
    re.IGNORECASE,
)
_ENTITY_CATEGORY = {
    "react": "framework", "vue": "framework", "angular": "framework",
    "svelte": "framework", "next.js": "framework", "sveltekit": "framework",
    "postgresql": "database", "mysql": "database", "mongodb": "database",
    "sqlite": "database", "mariadb": "database", "redis": "database",
    "fastapi": "backend", "django": "backend", "flask": "backend",
    "express": "backend", "node.js": "backend",
    "python": "language", "typescript": "language", "javascript": "language",
    "tailwind": "styling", "bootstrap": "styling",
}
_KNOWN_ENTITIES = set(_ENTITY_CATEGORY)


def extract_entity_claim(sentence: str) -> ExtractedClaim | None:
    """Extract 'X is/uses <entity>' claims where <entity> is a known technology."""
    m = _ENTITY_CLAIM_RE.match(sentence.strip())
    if not m:
        return None
    value = m.group("value").strip().rstrip(".")
    if value.lower() not in _KNOWN_ENTITIES:
        # try the last token as the entity ("written in Vue.js 3" -> "vue.js")
        last = value.split()[-1].rstrip(".").lower() if value.split() else ""
        if last not in _KNOWN_ENTITIES:
            return None
        value = value.split()[-1].rstrip(".")
    subject = m.group("subject").strip().rstrip(",:;")
    return ExtractedClaim(
        statement=sentence.strip(),
        subject=subject,
        predicate=m.group("predicate").lower(),
        value=value,
        unit=None,
        qualifiers=f"category:{_ENTITY_CATEGORY[value.lower()]}",
        quote=sentence.strip(),
        confidence=0.7,
    )


_TABLE_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")


def _extract_table_rows(self, text: str) -> list[ExtractedClaim]:
    """Markdown table rows like '| Frontend | React, TypeScript |' become
    one claim per recognized entity in the value cell."""
    claims: list[ExtractedClaim] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= {"|", "-", " ", ":"}:
            continue
        m = _TABLE_ROW_RE.match(line)
        if not m:
            continue
        subject = m.group(1).strip().rstrip(":")
        value_text = m.group(2).strip()
        if not subject or not value_text:
            continue
        for token in re.split(r"[,;/+]|\s+and\s+", value_text):
            token = token.strip().rstrip("().").lower()
            token = re.sub(r"\s*\(.*$", "", token).strip()
            if token in _ENTITY_CATEGORY:
                claims.append(
                    ExtractedClaim(
                        statement=f"{subject} is {token}",
                        subject=subject,
                        predicate="is",
                        value=token,
                        unit=None,
                        qualifiers=f"category:{_ENTITY_CATEGORY[token]}",
                        quote=line,
                        confidence=0.6,
                    )
                )
    return claims


HeuristicClaimExtractor._extract_table_rows = _extract_table_rows

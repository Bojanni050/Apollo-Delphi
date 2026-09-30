from app.services.analysis.claim_extraction import ExtractedClaim, HeuristicClaimExtractor
from app.services.issues.detection import detect_contradictions, detect_entity_contradictions


def _entity_claim(subject, value, category, quote=None, doc=None):
    return ExtractedClaim(
        statement=f"{subject} is {value}",
        subject=subject,
        predicate="is",
        value=value,
        qualifiers=f"category:{category}",
        quote=quote or f"{subject} is {value}",
    )


def test_entity_claim_extraction_sentence():
    claims = HeuristicClaimExtractor().extract("The Apollo frontend is written in Vue.\nThe database is MongoDB.")
    values = {c.value.lower() for c in claims}
    assert "vue" in values
    assert "mongodb" in values


def test_entity_claim_extraction_table_rows():
    text = "| Frontend | React, TypeScript, Vite |\n| Database | PostgreSQL + pgvector |"
    claims = HeuristicClaimExtractor().extract(text)
    values = {c.value.lower() for c in claims}
    assert "react" in values
    assert "postgresql" in values


def test_entity_contradiction_framework_conflict():
    a = _entity_claim("The Apollo frontend", "Vue", "framework", quote="written in Vue")
    b = _entity_claim("Frontend", "react", "framework", quote="| Frontend | React |")
    found = detect_entity_contradictions([(a, 1), (b, 2)])
    assert len(found) == 1
    assert {found[0].value_a, found[0].value_b} == {"vue", "react"}


def test_entity_contradiction_database_conflict():
    a = _entity_claim("The database", "MongoDB", "database")
    b = _entity_claim("Database", "postgresql", "database", quote="| Database | PostgreSQL |")
    found = detect_entity_contradictions([(a, 1), (b, 2)])
    assert len(found) == 1


def test_no_entity_contradiction_same_value():
    a = _entity_claim("The database", "PostgreSQL", "database")
    b = _entity_claim("Database", "postgresql", "database", quote="| Database | PostgreSQL |")
    assert detect_entity_contradictions([(a, 1), (b, 2)]) == []


def test_no_entity_contradiction_unrelated_subjects():
    a = _entity_claim("The frontend", "Vue", "framework")
    b = _entity_claim("The database", "MongoDB", "database")
    assert detect_entity_contradictions([(a, 1), (b, 2)]) == []


def test_no_entity_contradiction_within_same_document():
    a = _entity_claim("The frontend", "Vue", "framework")
    b = _entity_claim("Frontend", "react", "framework", quote="| Frontend | React |")
    assert detect_entity_contradictions([(a, 1), (b, 1)]) == []


def test_value_detector_also_catches_entity_conflicts():
    """The generic value detector also flags vue vs react (same subject key,
    different values) - which is correct behavior, not a false positive."""
    a = _entity_claim("The frontend", "Vue", "framework")
    b = _entity_claim("Frontend", "react", "framework", quote="| Frontend | React |")
    found = detect_contradictions([(a, 1), (b, 2)])
    assert len(found) == 1
    assert {found[0].value_a, found[0].value_b} == {"vue", "react"}

from app.services.analysis.claim_extraction import (
    ExtractedClaim,
    HeuristicClaimExtractor,
    normalize_value,
)


def test_extracts_numeric_claims():
    text = "The total budget is 30,000 EUR. The team will deliver in 12 weeks. Some unrelated prose follows."
    claims = HeuristicClaimExtractor().extract(text)
    statements = [c.statement for c in claims]
    assert any("30,000" in s for s in statements)
    assert any("12 weeks" in s for s in statements)


def test_claim_fields_populated():
    claims = HeuristicClaimExtractor().extract("The project budget is 30000 EUR for the build.")
    assert claims
    c = claims[0]
    assert c.subject == "The project budget"
    assert c.value == "30000"
    assert c.unit == "EUR"
    assert c.quote == c.statement


def test_no_claims_from_plain_prose():
    claims = HeuristicClaimExtractor().extract("This document describes the general approach without facts.")
    assert claims == []


def test_normalize_value():
    assert normalize_value("30,000") == "30000"
    assert normalize_value("25") == "25"
    assert normalize_value("2.5") == "2.5"


def test_extracted_claim_model_validation():
    c = ExtractedClaim(statement="s", quote="q", confidence=0.5)
    assert c.qualifiers is None

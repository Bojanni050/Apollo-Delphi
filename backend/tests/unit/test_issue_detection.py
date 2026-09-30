from app.services.issues.detection import (
    detect_contradictions,
    detect_open_questions,
)
from app.services.analysis.claim_extraction import ExtractedClaim


def _claim(subject, value, quote=None, unit="EUR"):
    return ExtractedClaim(
        statement=f"{subject} is {value} {unit}",
        subject=subject,
        predicate="is",
        value=value,
        unit=unit,
        quote=quote or f"{subject} is {value} {unit}",
    )


def test_contradiction_detected_across_documents():
    contradictions = detect_contradictions([(_claim("The budget", "25000"), 1), (_claim("The budget", "30000"), 2)])
    assert len(contradictions) == 1
    c = contradictions[0]
    assert {c.value_a, c.value_b} == {"25000", "30000"}


def test_no_contradiction_within_same_document():
    contradictions = detect_contradictions([(_claim("The budget", "25000"), 1), (_claim("The budget", "30000"), 1)])
    assert contradictions == []


def test_no_contradiction_when_values_agree():
    contradictions = detect_contradictions([(_claim("The budget", "30000"), 1), (_claim("The budget", "30,000"), 2)])
    assert contradictions == []


def test_no_contradiction_for_different_subjects():
    contradictions = detect_contradictions([(_claim("The budget", "25000"), 1), (_claim("The timeline", "30000"), 2)])
    assert contradictions == []


def test_open_question_detection():
    found = detect_open_questions("The final delivery date is TBD. The owner is to be decided next week. Budget confirmed.")
    texts = [f.question for f in found]
    assert any("TBD" in t for t in texts)
    assert any("to be decided" in t for t in texts)


def test_no_false_open_questions():
    assert detect_open_questions("The budget is 30000 EUR.") == []

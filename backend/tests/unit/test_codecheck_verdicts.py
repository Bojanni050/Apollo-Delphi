"""Slice 2, zuiver: bewijs zoeken en offline oordelen (geen db, geen netwerk)."""

from app.services.codecheck.service import DigestSection
from app.services.codecheck.verdicts import find_evidence, heuristic_verdict


def _code(path: str, text: str) -> tuple[str, DigestSection]:
    return ("github:owner/repo@main", DigestSection(path=path, kind="code", text=text))


def test_find_evidence_ranks_best_overlap_first():
    sections = [
        _code("src/other.py", "def unrelated():\n    return 1\n"),
        _code("src/db.py", "DATABASE_URL = 'postgresql://db:5432/app'\nconnect_postgresql(timeout=30)\n"),
    ]
    found = find_evidence("De applicatie gebruikt PostgreSQL als database", "PostgreSQL", sections)
    assert found and found[0].path == "src/db.py"
    assert found[0].score >= 5
    assert "postgresql" in found[0].snippet.lower()


def test_find_evidence_empty_without_overlap():
    sections = [_code("src/app.py", "print('hoi')\n")]
    assert find_evidence("Het budget is 250000 EUR", "250000", sections) == []


def test_heuristic_confirms_on_strong_evidence():
    sections = [_code("src/db.py", "ENGINE = 'postgresql'\nDATABASE_URL = 'postgresql://db/app'\n")]
    evidence = find_evidence("De applicatie gebruikt PostgreSQL als database", "PostgreSQL", sections)
    judged = heuristic_verdict("De applicatie gebruikt PostgreSQL als database", "PostgreSQL", evidence)
    assert judged.verdict == "bevestigd"
    assert judged.confidence > 0.5


def test_heuristic_never_contradicts():
    sections = [_code("src/app.py", "print('hoi wereld')\n")]
    for statement in ("De app print hoi", "Het budget is 250000 EUR"):
        judged = heuristic_verdict(statement, None, find_evidence(statement, None, sections))
        assert judged.verdict in ("bevestigd", "niet_gevonden"), "een heuristiek stelt nooit een tegenspraak vast"


def test_heuristic_not_found_without_evidence():
    judged = heuristic_verdict("Iets onvindbaars", None, [])
    assert judged.verdict == "niet_gevonden"

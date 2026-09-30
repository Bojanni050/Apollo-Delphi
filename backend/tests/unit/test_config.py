import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    "raw, expected",
    [
        (".pdf,.docx,.txt,.md", [".pdf", ".docx", ".txt", ".md"]),  # format used by .env.example
        (" .pdf , .md ", [".pdf", ".md"]),
        ('[".txt", ".md"]', [".txt", ".md"]),  # JSON still works
    ],
)
def test_allowed_extensions_accepts_comma_separated_and_json(monkeypatch, raw, expected):
    monkeypatch.setenv("ALLOWED_EXTENSIONS", raw)
    assert Settings(_env_file=None).allowed_extensions == expected


def test_env_example_parses(tmp_path, monkeypatch):
    """The documented `cp .env.example .env` must yield a working configuration."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[3] / ".env.example"
    monkeypatch.delenv("ALLOWED_EXTENSIONS", raising=False)
    assert Settings(_env_file=example).allowed_extensions == [".pdf", ".docx", ".txt", ".md"]

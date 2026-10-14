from app.services.codecheck.service import MAX_REPOS, classify_path, split_digest


def test_classify_docs_and_code():
    assert classify_path("README.md") == "docs"
    assert classify_path("docs/usage.rst") == "docs"
    assert classify_path("src/app.py") == "code"
    assert classify_path("frontend/src/api.ts") == "code"
    assert classify_path("config/settings.yaml") == "code"
    assert classify_path("logo.png") == "other"


def test_split_digest_keeps_sections():
    digest = (
        "# Repository: owner/repo (branch: main)\n\n"
        "## FILE: README.md\n\nDe app start met start.cmd.\n\n"
        "## FILE: src/app.py\n\nprint('hoi')\n"
    )
    sections = split_digest(digest)
    assert [(s.path, s.kind) for s in sections] == [
        ("README.md", "docs"),
        ("src/app.py", "code"),
    ]
    assert "start.cmd" in sections[0].text
    assert "print" in sections[1].text


def test_max_repos_is_four():
    assert MAX_REPOS == 4

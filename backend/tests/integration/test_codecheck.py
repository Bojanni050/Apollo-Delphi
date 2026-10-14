"""Codecheck slice 2: POST /codecheck/run legt docs naast repo's (mock-stand, offline)."""
import io
import json

from app.models import Document
from app.services.github.service import github_ingest_service

DIGEST = (
    "# Repository: owner/repo (branch: main)\n\n"
    "## FILE: README.md\n\nDe app gebruikt PostgreSQL als database.\n\n"
    "## FILE: src/db.py\n\nENGINE = 'postgresql'\nDATABASE_URL = 'postgresql://db/app'\n"
)

DOC_TEXT = "# Visie\n\n| Database | PostgreSQL |\n| Frontend | React |\n\nThe budget is 250000 EUR.\n"


def _setup(client, db, monkeypatch):
    ws = client.post("/api/workspaces", json={"name": "Codecheck"}).json()["id"]
    doc = client.post(
        "/api/documents", params={"workspace_id": ws}, files={"file": ("visie.md", io.BytesIO(DOC_TEXT.encode()), "text/plain")}
    ).json()
    client.post(f"/api/documents/{doc['id']}/index")
    repo = Document(
        workspace_id=ws,
        filename="github:owner/repo@main",
        stored_filename="-",
        file_type="md",
        file_size=len(DIGEST.encode()),
        content_hash="x",
        title="owner/repo",
        doc_metadata=json.dumps({"github": {"owner": "owner", "repo": "repo", "branch": "main"}}),
        indexing_status="indexed",
        source_type="github",
        source_url="https://github.com/owner/repo/tree/main",
        repo_path=None,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    monkeypatch.setattr(github_ingest_service, "get_document_content", lambda _doc: DIGEST.encode())
    return ws, doc["id"], repo.id


def test_run_judges_each_claim_with_evidence(client, db, monkeypatch):
    ws, doc_id, repo_id = _setup(client, db, monkeypatch)
    resp = client.post(
        "/api/codecheck/run",
        json={"workspace_id": ws, "document_ids": [doc_id], "repos": [{"document_id": repo_id}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["claims"] >= 2
    s = body["summary"]
    assert s["bevestigd"] + s["tegengesproken"] + s["niet_gevonden"] == s["claims"]
    assert s["bevestigd"] >= 1, "postgresql staat letterlijk in src/db.py"
    assert s["niet_gevonden"] >= 1, "react komt in geen enkele codesectie voor"
    assert all(c["method"] == "heuristic" for c in body["checked"])
    pg = next(c for c in body["checked"] if "postgresql" in c["statement"].lower())
    assert pg["verdict"] == "bevestigd" and pg["evidence"] and pg["evidence"][0]["path"] == "src/db.py"


def test_unknown_document_is_rejected(client, db, monkeypatch):
    ws, _, repo_id = _setup(client, db, monkeypatch)
    resp = client.post(
        "/api/codecheck/run",
        json={"workspace_id": ws, "document_ids": [99999], "repos": [{"document_id": repo_id}]},
    )
    assert resp.status_code == 400


def test_repo_digest_as_docs_side_is_rejected(client, db, monkeypatch):
    ws, _, repo_id = _setup(client, db, monkeypatch)
    resp = client.post(
        "/api/codecheck/run",
        json={"workspace_id": ws, "document_ids": [repo_id], "repos": [{"document_id": repo_id}]},
    )
    assert resp.status_code == 400


def test_empty_docs_and_five_repos_are_rejected(client, db, monkeypatch):
    ws, doc_id, repo_id = _setup(client, db, monkeypatch)
    assert (
        client.post("/api/codecheck/run", json={"workspace_id": ws, "document_ids": [], "repos": [{"document_id": repo_id}]}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/codecheck/run",
            json={"workspace_id": ws, "document_ids": [doc_id], "repos": [{"document_id": repo_id}] * 5},
        ).status_code
        == 422
    )

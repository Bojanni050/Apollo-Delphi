import io
import subprocess
from pathlib import Path


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def _upload(client, ws_id, name, content="Project Alpha budget is 100 EUR."):
    resp = client.post(
        "/api/documents",
        params={"workspace_id": ws_id},
        files={"file": (name, io.BytesIO(content.encode()), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_workspace_is_a_git_repo_with_inbox(client):
    ws = client.post("/api/workspaces", json={"name": "Mijn Werkmap"}).json()
    repo = Path(ws["working_dir"])
    assert (repo / ".git").is_dir()
    assert (repo / "Inbox").is_dir()
    assert "Initialize werkmap" in _git(repo, "log", "--format=%s")


def test_upload_lands_in_inbox_and_is_committed(client, db):
    ws = client.post("/api/workspaces", json={"name": "Inbox test"}).json()
    repo = Path(ws["working_dir"])
    _upload(client, ws["id"], "notes.txt")
    _upload(client, ws["id"], "notes.txt", "second version, different text")

    from app.models import Document

    docs = db.query(Document).filter(Document.workspace_id == ws["id"]).order_by(Document.id).all()
    assert [d.inbox_path for d in docs] == ["Inbox/notes.txt", "Inbox/notes-2.txt"]
    assert all(d.repo_path is None for d in docs), "repo_path belongs to GitHub-sourced documents"

    assert (repo / "Inbox" / "notes.txt").read_text() == "Project Alpha budget is 100 EUR."
    assert (repo / "Inbox" / "notes-2.txt").exists(), "same filename must never overwrite"
    assert _git(repo, "status", "--porcelain").strip() == ""
    subjects = _git(repo, "log", "--format=%s").splitlines()
    assert "Add Inbox/notes.txt" in subjects and "Add Inbox/notes-2.txt" in subjects

    history = client.get(f"/api/workspaces/{ws['id']}/history").json()
    assert [c["message"] for c in history][:2] == ["Add Inbox/notes-2.txt", "Add Inbox/notes.txt"]


def test_deleting_document_or_workspace_keeps_files(client):
    ws = client.post("/api/workspaces", json={"name": "Nooit weg"}).json()
    repo = Path(ws["working_dir"])
    doc = _upload(client, ws["id"], "keep.txt")
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.delete(f"/api/workspaces/{ws['id']}").status_code == 204
    assert (repo / "Inbox" / "keep.txt").exists()


def test_existing_folder_can_be_used_and_relative_path_rejected(client, tmp_path):
    ws = client.post("/api/workspaces", json={"name": "Eigen map", "working_dir": str(tmp_path / "mine")}).json()
    assert Path(ws["working_dir"]) == (tmp_path / "mine")
    assert (tmp_path / "mine" / ".git").is_dir()
    bad = client.post("/api/workspaces", json={"name": "x", "working_dir": "relative/dir"})
    assert bad.status_code == 400

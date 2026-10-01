"""Documents that belong to no werkmap can be moved into one, together with what was derived from them."""
import io
import subprocess
from pathlib import Path

from app.core.config import get_settings
from app.models import Document

A1 = "Harbour Initial Budget\n\nThe total approved budget is 25000 EUR for the harbour.\n"
A2 = "Harbour Revised Budget\n\nThis revised proposal supersedes the initial budget proposal.\nThe total approved budget is 30000 EUR for the harbour.\n"
OTHER = "Library note\n\nThe library opens at 9 o'clock.\n"


def _ws(client, name):
    return client.post("/api/workspaces", json={"name": name}).json()


def _doc(client, ws_id, name, text):
    params = {"workspace_id": ws_id} if ws_id else {}
    d = client.post("/api/documents", params=params, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}).json()
    assert client.post(f"/api/documents/{d['id']}/index").json()["indexing_status"] == "indexed"
    return d["id"]


def _legacy_world(client):
    """Two unassigned documents with an analysis, knowledge and a generated report: the pre-werkmap state."""
    d1, d2 = _doc(client, None, "a1.txt", A1), _doc(client, None, "a2.txt", A2)
    run = client.post("/api/analysis").json()
    client.post("/api/knowledge/build", params={"analysis_run_id": run["id"]})
    gen = client.post("/api/documents/generate", params={"title": "Legacy report"}).json()
    return d1, d2, run, gen


def _git_log(repo):
    return subprocess.run(["git", "-C", str(repo), "log", "--format=%s"], capture_output=True, text=True).stdout.splitlines()


def test_unassigned_counts(client):
    assert client.get("/api/workspaces/unassigned").json() == {"documents": 0, "analysis_runs": 0, "generated_documents": 0}
    _legacy_world(client)
    assert client.get("/api/workspaces/unassigned").json() == {"documents": 2, "analysis_runs": 1, "generated_documents": 1}


def test_adopt_moves_documents_and_everything_derived_from_them(client, db):
    d1, d2, run, gen = _legacy_world(client)
    ws = _ws(client, "Haven")
    mine = _doc(client, ws["id"], "mine.txt", OTHER)  # already belongs to the werkmap
    other = _ws(client, "Elders")
    foreign = _doc(client, other["id"], "foreign.txt", OTHER)  # belongs to another werkmap

    result = client.post(f"/api/workspaces/{ws['id']}/adopt-unassigned").json()
    assert (result["documents"], result["analysis_runs"], result["generated_documents"]) == (2, 1, 1)
    assert result["mirrored_to_repository"] == 2 and result["not_mirrored"] == []

    # everything is now the werkmap's...
    assert {d["id"] for d in client.get("/api/documents", params={"workspace_id": ws["id"]}).json()} == {d1, d2, mine}
    issues = client.get("/api/issues", params={"workspace_id": ws["id"]}).json()
    assert issues and {i["analysis_run_id"] for i in issues} == {run["id"]}
    assert client.get("/api/knowledge", params={"workspace_id": ws["id"]}).json()
    assert [g["id"] for g in client.get("/api/documents/generated/list", params={"workspace_id": ws["id"]}).json()] == [gen["id"]]
    hits = client.get("/api/search", params={"q": "total approved budget", "workspace_id": ws["id"], "top_k": 10}).json()["results"]
    assert {h["document_filename"] for h in hits} >= {"a1.txt", "a2.txt"}

    # ...and nothing is left without an owner, while other werkmappen are untouched
    assert client.get("/api/workspaces/unassigned").json() == {"documents": 0, "analysis_runs": 0, "generated_documents": 0}
    assert client.get("/api/issues").json() == [] and client.get("/api/knowledge").json() == []
    assert [d["id"] for d in client.get("/api/documents", params={"workspace_id": other["id"]}).json()] == [foreign]


def test_adopted_originals_are_committed_to_the_werkmap_repository(client, db):
    _legacy_world(client)
    ws = _ws(client, "Haven")
    client.post(f"/api/workspaces/{ws['id']}/adopt-unassigned")
    repo = Path(ws["working_dir"])
    assert {p.name for p in (repo / "Inbox").iterdir() if p.is_file() and p.name != ".gitkeep"} == {"a1.txt", "a2.txt"}
    subjects = _git_log(repo)
    assert "Add Inbox/a1.txt" in subjects and "Add Inbox/a2.txt" in subjects
    db.expire_all()
    assert sorted(d.inbox_path for d in db.query(Document).filter(Document.workspace_id == ws["id"])) == ["Inbox/a1.txt", "Inbox/a2.txt"]
    assert (repo / "Inbox" / "a1.txt").read_text() == A1


def test_adopting_again_is_a_no_op(client):
    _legacy_world(client)
    ws = _ws(client, "Haven")
    client.post(f"/api/workspaces/{ws['id']}/adopt-unassigned")
    commits = len(_git_log(Path(ws["working_dir"])))
    second = client.post(f"/api/workspaces/{ws['id']}/adopt-unassigned").json()
    assert second == {"documents": 0, "analysis_runs": 0, "generated_documents": 0, "mirrored_to_repository": 0, "not_mirrored": []}
    assert len(_git_log(Path(ws["working_dir"]))) == commits


def test_a_missing_original_is_reported_but_ownership_still_moves(client):
    d1, d2, _, _ = _legacy_world(client)
    ws = _ws(client, "Haven")
    from app.db.session import SessionLocal

    with SessionLocal() as s:
        stored = s.get(Document, d1).stored_filename
    (get_settings().ensure_upload_dir() / stored).unlink()

    result = client.post(f"/api/workspaces/{ws['id']}/adopt-unassigned").json()
    assert result["documents"] == 2 and result["mirrored_to_repository"] == 1
    assert [(n["document_id"], n["reason"]) for n in result["not_mirrored"]] == [(d1, "original file not found")]
    assert d1 in {d["id"] for d in client.get("/api/documents", params={"workspace_id": ws["id"]}).json()}


def test_github_documents_move_but_are_not_copied_into_the_repository(client, db):
    gh = Document(
        filename="README.md", stored_filename="gh-1", file_type="md", file_size=1, content_hash="h",
        indexing_status="indexed", source_type="github", source_url="https://github.com/x/y", repo_path="README.md",
    )
    db.add(gh)
    db.commit()
    gh_id = gh.id
    ws = _ws(client, "Haven")
    result = client.post(f"/api/workspaces/{ws['id']}/adopt-unassigned").json()
    assert result["documents"] == 1 and result["mirrored_to_repository"] == 0 and result["not_mirrored"] == []
    db.expire_all()
    moved = db.get(Document, gh_id)
    assert moved.workspace_id == ws["id"] and moved.inbox_path is None


def test_unknown_werkmap_is_a_404_and_nothing_moves(client):
    _legacy_world(client)
    assert client.post("/api/workspaces/9999/adopt-unassigned").status_code == 404
    assert client.get("/api/workspaces/unassigned").json()["documents"] == 2

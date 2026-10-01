"""Files of an uploaded folder: their path names the document and is kept under the werkmap's Inbox."""
import io
import subprocess
from pathlib import Path

import pytest

from app.services import workspace_repo


def _ws(client):
    return client.post("/api/workspaces", json={"name": "w"}).json()


def _upload(client, ws_id, filename, text, relative_path=None):
    data = {"relative_path": relative_path} if relative_path is not None else None
    return client.post(
        "/api/documents", params={"workspace_id": ws_id}, data=data,
        files={"file": (filename, io.BytesIO(text.encode()), "text/plain")},
    )


def test_the_relative_path_names_the_document_and_the_inbox_keeps_the_folders(client):
    ws = _ws(client)
    resp = _upload(client, ws["id"], "001.md", "# Decision\nWe use PostgreSQL.", "docs/adr/001.md")
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["filename"] == "docs/adr/001.md" and doc["file_type"] == "md" and len(doc["content_hash"]) == 64
    stored = Path(ws["working_dir"]) / "Inbox" / "docs" / "adr" / "001.md"
    assert stored.read_text() == "# Decision\nWe use PostgreSQL."
    log = subprocess.run(["git", "log", "--format=%s"], cwd=ws["working_dir"], capture_output=True, text=True).stdout
    assert "Add Inbox/docs/adr/001.md" in log


def test_same_file_name_in_different_folders_stays_apart(client):
    ws = _ws(client)
    a = _upload(client, ws["id"], "README.md", "alpha", "a/README.md").json()
    b = _upload(client, ws["id"], "README.md", "beta", "b/README.md").json()
    assert (a["filename"], b["filename"]) == ("a/README.md", "b/README.md")
    root = Path(ws["working_dir"]) / "Inbox"
    assert (root / "a" / "README.md").read_text() == "alpha" and (root / "b" / "README.md").read_text() == "beta"


def test_backslashes_and_odd_segments_are_normalised():
    assert workspace_repo.clean_relative_path(r"docs\sub dir\.\x.md") == "docs/sub dir/x.md"
    assert workspace_repo.clean_relative_path("a//b/c.md") == "a/b/c.md"
    assert workspace_repo.clean_relative_path("dir/<weird>.md") == "dir/_weird_.md"
    assert workspace_repo.clean_relative_path("") is None and workspace_repo.clean_relative_path(None) is None
    assert workspace_repo.clean_relative_path("./") is None


@pytest.mark.parametrize("path", ["../x.md", "a/../../x.md", "/etc/x.md", r"C:\x.md", "C:/x.md", "a/" * 20 + "x.md"])
def test_a_path_cannot_leave_the_folder(client, path):
    ws = _ws(client)
    resp = _upload(client, ws["id"], "x.md", "x", path)
    assert resp.status_code == 400
    assert not (Path(ws["working_dir"]).parent / "x.md").exists()


def test_the_extension_is_checked_on_the_path_not_the_upload_name(client):
    ws = _ws(client)
    assert _upload(client, ws["id"], "fine.md", "x", "docs/tool.exe").status_code == 400
    assert _upload(client, ws["id"], "fine.exe", "x", "docs/ok.txt").status_code == 201


def test_without_a_relative_path_nothing_changes(client):
    ws = _ws(client)
    doc = _upload(client, ws["id"], "plain.txt", "hello").json()
    assert doc["filename"] == "plain.txt"
    assert (Path(ws["working_dir"]) / "Inbox" / "plain.txt").is_file()


def test_a_folder_file_can_be_indexed_and_found_by_its_path(client):
    ws = _ws(client)
    doc = _upload(client, ws["id"], "budget.md", "The harbour budget is 250000 EUR.", "finance/2026/budget.md").json()
    assert client.post(f"/api/documents/{doc['id']}/index").json()["indexing_status"] == "indexed"
    hit = client.get("/api/search", params={"q": "harbour budget", "workspace_id": ws["id"]}).json()["results"][0]
    assert hit["document_filename"] == "finance/2026/budget.md"

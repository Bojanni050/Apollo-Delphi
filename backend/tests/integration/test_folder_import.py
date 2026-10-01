"""Importing a folder of this machine: scanned recursively by the backend, no browser upload involved."""
import hashlib
from pathlib import Path

import pytest

from app.core.config import get_settings


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "proj"
    for rel, text in {
        "README.md": "# Project\nThe harbour budget is 250000 EUR.",
        "docs/README.md": "# Docs",
        "docs/adr/001.md": "# ADR 1\nWe use PostgreSQL.",
        "node_modules/x/readme.md": "dependency",
        ".git/notes.txt": "git",
        "img/logo.png": "png",
        "empty.txt": "",
        "~$lock.docx": "lock",
        "docs/.hidden.md": "hidden",
    }.items():
        file = root / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    return root


def _scan(client, path):
    return client.post("/api/documents/folder/scan", json={"path": str(path)})


def _ws(client):
    return client.post("/api/workspaces", json={"name": "w"}).json()


def test_scan_lists_every_importable_file_recursively_with_its_hash(client, folder):
    body = _scan(client, folder).json()
    assert body["name"] == "proj" and body["truncated"] is False
    assert [f["path"] for f in body["files"]] == ["README.md", "docs/README.md", "docs/adr/001.md"]
    readme = body["files"][0]
    assert readme["content_hash"] == hashlib.sha256((folder / "README.md").read_bytes()).hexdigest()
    assert readme["size"] == len((folder / "README.md").read_bytes())


def test_scan_says_what_it_skips_and_why(client, folder):
    skipped = {s["path"]: s["reason"] for s in _scan(client, folder).json()["skipped"]}
    assert skipped["node_modules/"] == "genegeerde map" and skipped[".git/"] == "genegeerde map"
    assert skipped["img/logo.png"] == "niet ondersteund" and skipped["empty.txt"] == "leeg bestand"
    assert skipped["~$lock.docx"] == "tijdelijk of verborgen bestand" and skipped["docs/.hidden.md"] == "tijdelijk of verborgen bestand"
    assert not any(p.startswith("node_modules/x") for p in skipped), "a skipped folder is not entered"


def test_files_above_the_upload_limit_are_skipped(client, folder, monkeypatch):
    monkeypatch.setattr(type(get_settings()), "max_upload_size_bytes", property(lambda self: 20))
    body = _scan(client, folder).json()
    assert [f["path"] for f in body["files"]] == ["docs/README.md"]
    assert any(s["path"] == "README.md" and s["reason"].startswith("groter dan") for s in body["skipped"])


@pytest.mark.parametrize("path", ["relatief/pad", "", "   "])
def test_a_scan_needs_a_full_path(client, path):
    assert client.post("/api/documents/folder/scan", json={"path": path}).status_code == 400


def test_a_scan_of_a_file_or_a_missing_folder_is_refused(client, folder):
    assert _scan(client, folder / "README.md").status_code == 400
    assert _scan(client, folder / "bestaat-niet").status_code == 400


def test_a_file_is_imported_under_the_folder_name_and_kept_in_the_inbox(client, folder):
    ws = _ws(client)
    resp = client.post("/api/documents/folder/file", json={"root": str(folder), "path": "docs/adr/001.md", "workspace_id": ws["id"]})
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["filename"] == "proj/docs/adr/001.md" and doc["workspace_id"] == ws["id"] and doc["file_type"] == "md"
    assert (Path(ws["working_dir"]) / "Inbox" / "proj" / "docs" / "adr" / "001.md").read_text() == "# ADR 1\nWe use PostgreSQL."
    assert doc["content_hash"] == hashlib.sha256((folder / "docs" / "adr" / "001.md").read_bytes()).hexdigest()


def test_a_whole_scanned_folder_can_be_imported_indexed_and_found_by_its_path(client, folder):
    ws = _ws(client)
    for f in _scan(client, folder).json()["files"]:
        doc = client.post("/api/documents/folder/file", json={"root": str(folder), "path": f["path"], "workspace_id": ws["id"]}).json()
        assert client.post(f"/api/documents/{doc['id']}/index").json()["indexing_status"] == "indexed"
    hit = client.get("/api/search", params={"q": "harbour budget", "workspace_id": ws["id"]}).json()["results"][0]
    assert hit["document_filename"] == "proj/README.md"


@pytest.mark.parametrize("path", ["../outside.md", "docs/../../outside.md", "/etc/x.md", "C:\\x.md", "", "docs/"])
def test_a_file_path_cannot_leave_the_folder(client, folder, path):
    (folder.parent / "outside.md").write_text("secret")
    resp = client.post("/api/documents/folder/file", json={"root": str(folder), "path": path})
    assert resp.status_code == 400
    assert client.get("/api/documents").json() == []


def test_only_allowed_plain_files_are_read(client, folder):
    for path in ("img/logo.png", "empty.txt", "~$lock.docx", "docs/adr", "bestaat-niet.md"):
        resp = client.post("/api/documents/folder/file", json={"root": str(folder), "path": path})
        assert resp.status_code == 400, path


def test_a_symbolic_link_is_neither_scanned_nor_read(client, folder, tmp_path):
    secret = tmp_path / "secret.md"
    secret.write_text("not for the app")
    try:
        (folder / "link.md").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    body = _scan(client, folder).json()
    assert "link.md" not in [f["path"] for f in body["files"]]
    assert client.post("/api/documents/folder/file", json={"root": str(folder), "path": "link.md"}).status_code == 400


def test_it_can_be_switched_off(client, folder, monkeypatch):
    monkeypatch.setattr(get_settings(), "folder_browse_enabled", False)
    assert _scan(client, folder).status_code == 403
    assert client.post("/api/documents/folder/file", json={"root": str(folder), "path": "README.md"}).status_code == 403

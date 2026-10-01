"""The folder picker's endpoint: directory names only, safe fallbacks, switchable."""
from pathlib import Path

import pytest

from app.api import system
from app.core.config import get_settings


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "Beta").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "inner").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "$RECYCLE.BIN").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "notes.txt").write_text("secret contents")
    return tmp_path


def _browse(client, path=None):
    return client.get("/api/system/folders", params={"path": path} if path is not None else None)


def test_lists_only_visible_folders_sorted_without_files(client, tree):
    body = _browse(client, str(tree)).json()
    assert [f["name"] for f in body["folders"]] == ["alpha", "Beta"]
    assert all(Path(f["path"]).is_dir() for f in body["folders"])
    assert "secret" not in str(body) and "notes.txt" not in str(body)
    assert Path(body["current_path"]) == tree.resolve()
    assert Path(body["parent_path"]) == tree.resolve().parent


def test_navigating_into_a_folder_and_up(client, tree):
    down = _browse(client, str(tree / "alpha")).json()
    assert [f["name"] for f in down["folders"]] == ["inner"]
    assert Path(down["parent_path"]) == tree.resolve()


def test_a_missing_folder_falls_back_to_its_nearest_existing_parent(client, tree):
    body = _browse(client, str(tree / "alpha" / "bestaat-niet" / "ook-niet")).json()
    assert Path(body["current_path"]) == (tree / "alpha").resolve()


@pytest.mark.parametrize("path", [None, "", "   ", "relatief/pad"])
def test_no_or_relative_path_starts_in_the_home_folder(client, path):
    body = _browse(client, path).json()
    assert Path(body["current_path"]) == Path.home().resolve()


def test_a_file_path_shows_the_folder_it_is_in(client, tree):
    assert Path(_browse(client, str(tree / "notes.txt")).json()["current_path"]) == tree.resolve()


def test_root_has_no_parent_and_drives_and_shortcuts_are_offered(client):
    root = Path(Path.home().anchor)
    body = _browse(client, str(root)).json()
    assert body["parent_path"] is None
    assert body["drives"] and any(d for d in body["drives"])
    assert all(Path(q["path"]).is_dir() for q in body["quick_access"])


def test_a_huge_folder_is_cut_off_and_flagged(client, tmp_path, monkeypatch):
    monkeypatch.setattr(system, "MAX_FOLDERS", 3)
    for i in range(5):
        (tmp_path / f"d{i}").mkdir()
    body = _browse(client, str(tmp_path)).json()
    assert len(body["folders"]) == 3 and body["truncated"] is True


def test_can_be_switched_off(client, tree, monkeypatch):
    monkeypatch.setattr(get_settings(), "folder_browse_enabled", False)
    resp = _browse(client, str(tree))
    assert resp.status_code == 403 and "FOLDER_BROWSE_ENABLED" in resp.json()["detail"]

"""A werkmap is a repository: a folder on disk with git history.

Uploaded originals land in ``Inbox/`` and each one is recorded as its own
commit, so nothing a user puts in a werkmap can silently change or disappear.
Only an explicit list of paths is ever staged (never ``-A``) and nothing here
deletes, rewrites history or pushes; deleting a werkmap in the database leaves
its folder untouched.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

INBOX_DIR = "Inbox"
TIMEOUT_SECONDS = 20

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_IDENTITY = ["-c", "user.name=Apollo", "-c", "user.email=apollo@local", "-c", "commit.gpgsign=false"]


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    cmd = ["git", "-C", str(repo), *_IDENTITY, *args]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS, check=False
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError("git command timed out") from exc
    if proc.returncode != 0:
        raise GitError((proc.stderr or proc.stdout).strip() or "git command failed")
    return proc.stdout


def default_working_dir(workspace_id: int, name: str) -> Path:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")[:40] or "werkmap"
    root = Path(get_settings().workspaces_root)
    return (root / f"{workspace_id}-{slug}").resolve()


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def init_repo(path: Path) -> Path:
    """Make ``path`` a git repository with an ``Inbox/``. Safe on an existing folder/repo."""
    path.mkdir(parents=True, exist_ok=True)
    inbox = path / INBOX_DIR
    inbox.mkdir(exist_ok=True)
    if not is_git_repo(path):
        _git(path, "init", "-q")
        keep = inbox / ".gitkeep"
        if not any(inbox.iterdir()):
            keep.touch()
        _commit_paths(path, [f"{INBOX_DIR}/{keep.name}"] if keep.exists() else [], "Initialize werkmap")
    return path


def _commit_paths(repo: Path, rel_paths: list[str], message: str) -> bool:
    if not rel_paths:
        return False
    _git(repo, "add", "--", *rel_paths)
    if not _git(repo, "status", "--porcelain", "--", *rel_paths).strip():
        return False
    _git(repo, "commit", "-q", "-m", message, "--", *rel_paths)
    return True


MAX_PATH_DEPTH = 12
MAX_PATH_CHARS = 500


def clean_relative_path(path: str | None) -> str | None:
    """A path inside an uploaded folder as ``a/b/c.md``: forward slashes, safe names, no way out of the folder.

    None when there is no path. ValueError when it tries to leave the folder (``..``, an absolute path, a drive).
    """
    if not path or not path.strip():
        return None
    raw = path.replace("\\", "/")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise ValueError("A path must be relative to the uploaded folder")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if not parts:
        return None
    if any(p == ".." for p in parts):
        raise ValueError("A path must not contain '..'")
    cleaned = [_SAFE_NAME_RE.sub("_", p).strip(" .") or "_" for p in parts]
    if len(cleaned) > MAX_PATH_DEPTH or sum(len(p) + 1 for p in cleaned) > MAX_PATH_CHARS:
        raise ValueError("That path is too deep or too long")
    return "/".join(cleaned)


def _unique_name(directory: Path, filename: str) -> str:
    name = _SAFE_NAME_RE.sub("_", Path(filename).name).strip(" .") or "document"
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, n = name, 1
    while (directory / candidate).exists():
        n += 1
        candidate = f"{stem}-{n}{suffix}"
    return candidate


def store_in_inbox(repo: Path, filename: str, data: bytes) -> str:
    """Write the original into ``Inbox/`` (never overwriting) and commit it. Returns the repo-relative path.

    ``filename`` may be a path from an uploaded folder (``docs/adr/001.md``): the subfolders are kept under Inbox.
    """
    inbox = repo / INBOX_DIR
    *folders, base = clean_relative_path(filename).split("/") if clean_relative_path(filename) else ["document"]
    directory = inbox.joinpath(*folders)
    directory.mkdir(parents=True, exist_ok=True)
    if inbox.resolve() not in (directory.resolve(), *directory.resolve().parents):
        raise OSError("The path leaves the Inbox")
    name = _unique_name(directory, base)
    tmp = directory / f".{name}.part"
    tmp.write_bytes(data)
    tmp.replace(directory / name)
    rel = "/".join([INBOX_DIR, *folders, name])
    try:
        _commit_paths(repo, [rel], f"Add {rel}")
    except GitError as exc:
        log.warning("Stored %s but could not commit it: %s", rel, exc)
    return rel


def history(repo: Path, limit: int = 50) -> list[dict]:
    if not is_git_repo(repo):
        return []
    try:
        out = _git(repo, "log", f"-{limit}", "--format=%H%x1f%an%x1f%aI%x1f%s")
    except GitError:
        return []  # no commits yet
    rows = []
    for line in out.splitlines():
        sha, author, date, subject = line.split("\x1f", 3)
        rows.append({"sha": sha, "author": author, "date": date, "message": subject})
    return rows

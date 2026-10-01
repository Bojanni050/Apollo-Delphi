"""Read a folder of the machine the backend runs on, recursively, so its documents can be imported without the browser.

Choosing a folder in the browser (``<input webkitdirectory>``) makes the browser itself ask "upload N files to this site?",
in its own unstyled popup at its own place. In the desktop app the backend runs on the same computer, so the app picks the
folder with its own dialog and the backend reads it from disk: no popup of the browser, and no bytes through the page.

What is read is limited like an upload: only the allowed extensions, nothing above the upload size limit, no symbolic links
(they could point out of the folder). The same switch as the folder picker (FOLDER_BROWSE_ENABLED) can turn this off.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import get_settings

#: Folders with tooling, dependencies or build output, never documents. Hidden folders (".x") are skipped too.
SKIPPED_FOLDERS = {"node_modules", "__pycache__", "venv", "dist", "build", "target"}
MAX_FILES = 5000


class FolderImportError(Exception):
    pass


@dataclass
class ScannedFile:
    path: str  # relative to the folder, with "/"
    size: int
    content_hash: str


@dataclass
class ScanResult:
    root: Path
    files: list[ScannedFile] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (path, reason)
    truncated: bool = False


def resolve_root(path: str) -> Path:
    candidate = Path((path or "").strip()).expanduser()
    if not candidate.is_absolute():
        raise FolderImportError("Give the full path of a folder")
    try:
        root = candidate.resolve()
    except OSError as exc:
        raise FolderImportError(f"Cannot read that folder: {exc}") from exc
    if not root.is_dir():
        raise FolderImportError("That is not a folder")
    return root


def _skip_reason(name: str, size: int) -> str | None:
    if name.startswith(".") or name.startswith("~$"):
        return "tijdelijk of verborgen bestand"
    ext = os.path.splitext(name)[1].lower()
    if ext not in get_settings().allowed_extensions:
        return "niet ondersteund"
    if size == 0:
        return "leeg bestand"
    if size > get_settings().max_upload_size_bytes:
        return f"groter dan {get_settings().max_upload_size_mb} MB"
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_folder(root: Path) -> ScanResult:
    """Every file below ``root``: which ones would be imported (with their hash) and which are skipped, and why."""
    result = ScanResult(root=root)
    for current, folders, names in os.walk(root, followlinks=False):
        here = Path(current)
        kept = []
        for folder in sorted(folders):
            if folder.startswith(".") or folder in SKIPPED_FOLDERS or (here / folder).is_symlink():
                result.skipped.append(((here / folder).relative_to(root).as_posix() + "/", "genegeerde map"))
            else:
                kept.append(folder)
        folders[:] = kept  # os.walk only enters the folders left in this list
        for name in sorted(names):
            path = here / name
            rel = path.relative_to(root).as_posix()
            try:
                if path.is_symlink() or not path.is_file():
                    result.skipped.append((rel, "snelkoppeling of speciaal bestand"))
                    continue
                size = path.stat().st_size
                reason = _skip_reason(name, size)
                if reason:
                    result.skipped.append((rel, reason))
                elif len(result.files) >= MAX_FILES:
                    result.truncated = True
                else:
                    result.files.append(ScannedFile(rel, size, _sha256(path)))
            except OSError as exc:
                result.skipped.append((rel, f"niet te lezen ({exc.__class__.__name__})"))
    return result


def read_file(root: Path, relative: str) -> bytes:
    """The bytes of one file below ``root``; refuses anything that is not a plain file inside it."""
    parts = [p for p in relative.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        raise FolderImportError("Invalid path")
    target = root.joinpath(*parts)
    if target.is_symlink() or not target.is_file():
        raise FolderImportError("Not a plain file in the folder")
    resolved = target.resolve()
    if root not in resolved.parents:
        raise FolderImportError("The file lies outside the folder")
    reason = _skip_reason(resolved.name, resolved.stat().st_size)
    if reason:
        raise FolderImportError(f"Not importable: {reason}")
    return resolved.read_bytes()

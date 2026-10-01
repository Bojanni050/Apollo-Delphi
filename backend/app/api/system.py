"""Browse the folders of the machine the backend runs on, for the folder picker of the setup wizard.

Only directory *names* are returned: never files and never file contents. The API has no authentication, so
whoever can reach it can already use every other endpoint; this one adds a view of the folder structure.
``FOLDER_BROWSE_ENABLED=false`` switches it off for a shared deployment (the wizard then falls back to typing
a path). Inside Docker it shows the container's file system, not the host's.
"""
from __future__ import annotations

import os
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/system", tags=["system"])

#: A folder with more subfolders than this is cut off (and reported as ``truncated``).
MAX_FOLDERS = 500
_HIDDEN_NAMES = {"node_modules", "__pycache__", "System Volume Information"}


class FolderItem(BaseModel):
    name: str
    path: str


class QuickAccessItem(BaseModel):
    name: str
    path: str


class FolderBrowseOut(BaseModel):
    current_path: str
    #: None at the top (a drive root or "/").
    parent_path: str | None
    folders: list[FolderItem]
    truncated: bool = False
    #: Drive roots on Windows, "/" elsewhere.
    drives: list[str]
    quick_access: list[QuickAccessItem]


def _drives() -> list[str]:
    if os.name == "nt":
        return [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]
    return ["/"]


def _quick_access() -> list[QuickAccessItem]:
    home = Path.home()
    candidates = [("Home", home), ("Documenten", home / "Documents"), ("Bureaublad", home / "Desktop")]
    return [QuickAccessItem(name=name, path=str(p)) for name, p in candidates if p.is_dir()]


def _start(path: str | None) -> Path:
    """The folder to show: the requested one, else its nearest existing parent, else the home folder."""
    if path and path.strip():
        candidate = Path(path.strip()).expanduser()
        if candidate.is_absolute():
            for folder in (candidate, *candidate.parents):
                try:
                    if folder.is_dir():
                        return folder.resolve()
                except OSError:
                    continue
    return Path.home().resolve()


def _hidden(name: str) -> bool:
    return name.startswith((".", "$")) or name in _HIDDEN_NAMES


@router.get("/folders", response_model=FolderBrowseOut)
def browse_folders(path: str | None = Query(None, description="Absolute folder to list; empty = the home folder")):
    """Subfolders of ``path`` (hidden and system folders left out), with a way up and some shortcuts."""
    if not get_settings().folder_browse_enabled:
        raise HTTPException(status_code=403, detail="Browsing folders is switched off (FOLDER_BROWSE_ENABLED=false)")
    current = _start(path)
    folders: list[FolderItem] = []
    truncated = False
    try:
        for entry in sorted(current.iterdir(), key=lambda e: e.name.lower()):
            if _hidden(entry.name):
                continue
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            if len(folders) >= MAX_FOLDERS:
                truncated = True
                break
            folders.append(FolderItem(name=entry.name, path=str(entry)))
    except OSError:
        pass  # an unreadable folder is shown as empty rather than failing the whole picker
    return FolderBrowseOut(
        current_path=str(current),
        parent_path=str(current.parent) if current.parent != current else None,
        folders=folders,
        truncated=truncated,
        drives=_drives(),
        quick_access=_quick_access(),
    )

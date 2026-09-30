from __future__ import annotations

import re
import urllib.parse

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

GITHUB_API = "https://api.github.com"

TEXT_EXTENSIONS = {".md", ".txt", ".rst", ".markdown"}
CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".toml",
    ".cfg", ".ini", ".html", ".css", ".sql", ".sh", ".env.example",
}
MAX_FILES = 50
MAX_FILE_BYTES = 200_000


class GitHubIngestError(Exception):
    pass


def parse_repo_url(url: str) -> tuple[str, str]:
    """Accepts https://github.com/owner/repo, owner/repo, with optional .git suffix."""
    url = url.strip().removesuffix(".git")
    m = re.match(r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", url)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", url)
    if m:
        return m.group(1), m.group(2)
    raise GitHubIngestError(f"Ongeldige GitHub-repository URL: {url}")


class GitHubClient:
    def __init__(self, token: str | None = None):
        self.headers = {"Accept": "application/vnd.github+json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _get(self, url: str) -> dict:
        r = httpx.get(url, headers=self.headers, timeout=30, follow_redirects=True)
        if r.status_code == 404:
            raise GitHubIngestError("Repository of bestand niet gevonden (is het publiek?)")
        if r.status_code == 403:
            raise GitHubIngestError("GitHub API-toegang geweigerd (rate limit? Voeg een token toe in de settings)")
        if r.status_code != 200:
            raise GitHubIngestError(f"GitHub API-fout {r.status_code}")
        return r.json()

    def repo_info(self, owner: str, repo: str) -> dict:
        return self._get(f"https://api.github.com/repos/{owner}/{repo}")

    def default_branch_tree(self, owner: str, repo: str) -> dict:
        info = self.repo_info(owner, repo)
        branch = info.get("default_branch") or "main"
        return self._get(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")

    def fetch_file(self, owner: str, repo: str, path: str) -> bytes:
        r = httpx.get(
            f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{urllib.parse.quote(path)}",
            headers={"Accept": "application/octet-stream"},
            timeout=30,
            follow_redirects=True,
        )
        if r.status_code != 200:
            raise GitHubIngestError(f"Kon bestand {path} niet ophalen ({r.status_code})")
        return r.content


def select_text_files(tree: dict) -> list[str]:
    """Pick documentation and light config/code files, skipping noise like node_modules."""
    paths: list[str] = []
    for item in tree.get("tree", []):
        if item.get("type") != "blob":
            continue
        p = item.get("path", "")
        lower = p.lower()
        if any(skip in lower for skip in (
            "node_modules/", ".min.js", ".min.css", "/dist/", "/build/", "package-lock.json",
            "/.git/", "pnpm-lock", "yarn.lock", "/migrations/versions/", "/__pycache__/",
        )):
            continue
        if item.get("size", 0) > MAX_FILE_BYTES:
            continue
        ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
        stem = lower.rsplit(".", 1)[0]
        if ext in TEXT_EXTENSIONS or (stem.endswith("readme")) or lower == "license":
            paths.append(p)
        elif ext in {".py", ".ts", ".tsx", ".js", ".jsx", ".yml", ".yaml", ".toml", ".sql", ".json", ".sh", ".cfg", ".ini"}:
            paths.append(p)
        if len(paths) >= MAX_FILES:
            break
    return paths

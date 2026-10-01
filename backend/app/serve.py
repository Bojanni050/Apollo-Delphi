"""Entry point of the desktop build: the API and the built frontend on one port, with its own data folder.

    python -m app.serve                 # 127.0.0.1:5274, data in the per-user data folder
    python -m app.serve --port 0        # let the OS pick a free port (printed on the first line)

Why a separate entry point
--------------------------
* **Same origin.** The desktop window loads the frontend from this server, so the page and the API share one
  origin: no CORS configuration and nothing to open up.
* **Own data folder, no Docker, no PostgreSQL.** Everything lives in one per-user folder (database, uploads,
  werkmappen, downloaded models) and the database is SQLite. Vector search then runs in Python over the stored
  vectors and keyword search in memory, which is fine at the size of one person's documents.
* **Migrations at start.** A fresh database is built by Alembic, and an existing one is brought up to date, so a
  new version of the app can change the schema without the user doing anything.
* **Opt-in.** Mounting the frontend changes the process-wide ASGI app, so it must not happen merely because
  ``app.main`` was imported (tests, CLIs). Only this entry point does it.

Settings already present in the environment win over the defaults chosen here (for example ``UPLOAD_DIR``).
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

#: ``backend/`` and the built frontend next to it, so this works regardless of the current directory.
BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"

APP_FOLDER = "Apollo-Delphi"


def default_data_dir() -> Path:
    """The per-user folder for the app's data: %LOCALAPPDATA% on Windows, XDG/Library elsewhere."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_FOLDER


def configure_environment(data_dir: Path) -> dict[str, str]:
    """Point the app at ``data_dir`` by setting the environment variables it reads. Existing ones are kept.

    Must run before ``app`` is imported: the database engine is created at import time.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "APOLLO_DATABASE_URL": f"sqlite:///{(data_dir / 'apollo.db').as_posix()}",
        "UPLOAD_DIR": str(data_dir / "uploads"),
        "WORKSPACES_ROOT": str(data_dir / "workspaces"),
        "LLAMACPP_MODELS_DIR": str(data_dir / "models"),
    }
    applied = {}
    for key, value in defaults.items():
        if not os.environ.get(key):
            os.environ[key] = value
            applied[key] = value
    return applied


def migrate() -> None:
    """Bring the database up to date with Alembic (creates it when it is new)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")


def build_app(dist: Path | None = None):
    """The FastAPI app with the built frontend mounted at the root.

    Fails with a clear message when the bundle is missing: the 404s on every asset would otherwise be very hard
    to diagnose.
    """
    dist = dist or FRONTEND_DIST
    if not (dist / "index.html").is_file():
        raise SystemExit(f"No frontend build at {dist}.\nBuild it first:  npm --prefix frontend run build")

    from fastapi.staticfiles import StaticFiles

    # Imported here so that importing this module needs neither a database nor a valid configuration.
    from app.main import app

    # Mounted last so it cannot shadow the /api routes (Starlette matches in registration order); html=True
    # serves index.html for "/". Unknown paths are a 404: the frontend keeps its pages in state, not in URLs.
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    return app


def _free_port(host: str) -> int:
    with socket.socket() as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.serve", description="Serve the API and the built frontend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5274, help="0 = let the OS pick a free port")
    parser.add_argument("--data-dir", type=Path, default=None, help=f"default: {default_data_dir()}")
    parser.add_argument("--frontend-dist", type=Path, default=None, help=f"default: {FRONTEND_DIST}")
    args = parser.parse_args(argv)

    configure_environment(args.data_dir or default_data_dir())
    migrate()
    app = build_app(args.frontend_dist)

    import uvicorn

    port = args.port or _free_port(args.host)
    print(f"Apollo serving on http://{args.host}:{port}", flush=True)
    uvicorn.run(app, host=args.host, port=port, log_level="info")


if __name__ == "__main__":
    main()

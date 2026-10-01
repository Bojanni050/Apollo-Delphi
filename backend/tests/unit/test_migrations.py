"""The Alembic chain must be a single line that can go up, all the way down and up again.

Runs in a subprocess: env.py reconfigures logging, which must not leak into other tests.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "APOLLO_DATABASE_URL": db_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180
    )


def _tables(db_file: Path) -> set[str]:
    with sqlite3.connect(db_file) as conn:
        return {r[0] for r in conn.execute("select name from sqlite_master where type='table'")} - {"alembic_version"}


def test_single_head():
    out = _alembic("sqlite:///unused.db", "heads")
    assert out.returncode == 0, out.stderr
    assert out.stdout.count("(head)") == 1, f"branched migrations: {out.stdout}"


def test_upgrade_downgrade_to_base_and_upgrade_again(tmp_path):
    db_file = tmp_path / "chain.db"
    url = f"sqlite:///{db_file.as_posix()}"

    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-1500:]
    assert {"documents", "workspaces", "pulse_runs", "app_settings", "generated_documents"} <= _tables(db_file)

    down = _alembic(url, "downgrade", "base")
    assert down.returncode == 0, f"downgrade failed (the GitHub-source migration used to break here):\n{down.stderr[-1500:]}"
    assert _tables(db_file) == set(), "downgrade to base must remove every table"

    again = _alembic(url, "upgrade", "head")
    assert again.returncode == 0, again.stderr[-1500:]
    assert "documents" in _tables(db_file)

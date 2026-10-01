"""The desktop entry point: own data folder, migrations at start, frontend on the API's port.

The server runs in a subprocess: mounting the frontend changes the process-wide app, which must not leak into
the other tests.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app import serve

BACKEND = Path(__file__).resolve().parents[2]
_OWN = ("APOLLO_DATABASE_URL", "UPLOAD_DIR", "WORKSPACES_ROOT", "LLAMACPP_MODELS_DIR")


def test_default_data_dir_is_a_per_user_apollo_folder():
    assert serve.default_data_dir().name == "Apollo-Delphi"
    assert serve.default_data_dir().is_absolute()


def test_configure_environment_sets_defaults_and_keeps_what_is_already_set(tmp_path, monkeypatch):
    for key in _OWN:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("UPLOAD_DIR", "/elsewhere")
    applied = serve.configure_environment(tmp_path / "data")
    assert (tmp_path / "data").is_dir()
    assert os.environ["APOLLO_DATABASE_URL"] == f"sqlite:///{(tmp_path / 'data' / 'apollo.db').as_posix()}"
    assert os.environ["WORKSPACES_ROOT"] == str(tmp_path / "data" / "workspaces")
    assert os.environ["UPLOAD_DIR"] == "/elsewhere" and "UPLOAD_DIR" not in applied


def _child_env():
    env = {k: v for k, v in os.environ.items() if k not in _OWN}
    return {**env, "PYTHONUNBUFFERED": "1"}


class Server:
    def __init__(self, data_dir, dist):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "app.serve", "--port", "0", "--data-dir", str(data_dir), "--frontend-dist", str(dist)],
            cwd=BACKEND, env=_child_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        seen = []
        for line in self.proc.stdout:  # the migrations log first; then "Apollo serving on http://127.0.0.1:PORT"
            seen.append(line)
            if line.startswith("Apollo serving on "):
                break
        else:
            raise AssertionError("the server never announced its address:\n" + "".join(seen))
        self.url = line.split(" on ", 1)[1].strip()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                self.get("/api/health")
                return
            except OSError:
                time.sleep(0.2)
        self.stop()
        raise AssertionError("the server did not become healthy")

    def get(self, path):
        with urllib.request.urlopen(self.url + path, timeout=5) as resp:
            return resp.status, resp.read().decode()

    def post(self, path, body):
        req = urllib.request.Request(
            self.url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())

    def stop(self):
        if os.name == "nt":
            # A venv's python.exe is a launcher that starts the real interpreter as a child; terminate() would
            # only kill the launcher and leave the server running, so take the whole tree down.
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        else:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


@pytest.fixture
def dist(tmp_path):
    folder = tmp_path / "dist"
    folder.mkdir()
    (folder / "index.html").write_text("<!doctype html><title>Apollo test page</title>")
    return folder


def test_serves_frontend_and_api_on_one_port_and_keeps_data_between_runs(tmp_path, dist):
    data = tmp_path / "data"
    server = Server(data, dist)
    try:
        status, page = server.get("/")
        assert status == 200 and "Apollo test page" in page
        with pytest.raises(urllib.error.HTTPError) as unknown:  # the frontend has no client-side routes
            server.get("/some/other/path")
        assert unknown.value.code == 404
        assert json.loads(server.get("/api/health")[1])["status"] == "ok"
        assert json.loads(server.get("/api/workspaces")[1]) == []
        status, ws = server.post("/api/workspaces", {"name": "Haven"})
        assert status == 201
    finally:
        server.stop()
    assert (data / "apollo.db").is_file() and (data / "workspaces").is_dir()

    again = Server(data, dist)  # an existing database is migrated, not recreated
    try:
        assert [w["name"] for w in json.loads(again.get("/api/workspaces")[1])] == ["Haven"]
    finally:
        again.stop()


def test_a_missing_frontend_build_is_explained(tmp_path):
    out = subprocess.run(
        [sys.executable, "-m", "app.serve", "--port", "0", "--data-dir", str(tmp_path / "d"), "--frontend-dist", str(tmp_path / "none")],
        cwd=BACKEND, env=_child_env(), capture_output=True, text=True, timeout=60,
    )
    assert out.returncode != 0 and "npm --prefix frontend run build" in (out.stderr + out.stdout)

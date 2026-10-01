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
    applied = serve.configure_environment(tmp_path / "data", _Settings())
    assert (tmp_path / "data").is_dir()
    assert os.environ["APOLLO_DATABASE_URL"] == f"sqlite:///{(tmp_path / 'data' / 'apollo.db').as_posix()}"
    assert os.environ["WORKSPACES_ROOT"] == str(tmp_path / "data" / "workspaces")
    assert os.environ["UPLOAD_DIR"] == "/elsewhere" and "UPLOAD_DIR" not in applied


class _Settings:
    """Stands in for the settings object, so a developer's real backend/.env cannot change the result."""

    def __init__(self, database_url=None, apollo_database_url=""):
        self.apollo_database_url = apollo_database_url
        self.database_url = database_url or "sqlite:///./apollo.db"
        self.model_fields_set = {"database_url"} if database_url else set()


def test_a_chosen_database_wins_over_the_sqlite_default(tmp_path, monkeypatch):
    sqlite = f"sqlite:///{(tmp_path / 'apollo.db').as_posix()}"
    pg = "postgresql+psycopg2://u:p@localhost:5432/apollo_desktop"
    for key in _OWN:
        monkeypatch.delenv(key, raising=False)

    assert serve.configured_database_url(_Settings()) == ""
    serve.configure_environment(tmp_path, _Settings())
    assert os.environ["APOLLO_DATABASE_URL"] == sqlite

    monkeypatch.delenv("APOLLO_DATABASE_URL")
    serve.configure_environment(tmp_path, _Settings(database_url=pg))  # DATABASE_URL from backend/.env
    assert os.environ["APOLLO_DATABASE_URL"] == pg

    monkeypatch.delenv("APOLLO_DATABASE_URL")
    other = "postgresql+psycopg2://u:p@localhost:5432/other"
    assert serve.configured_database_url(_Settings(database_url=pg, apollo_database_url=other)) == other

    monkeypatch.setenv("APOLLO_DATABASE_URL", "sqlite:///x.db")  # the environment beats .env
    assert serve.configured_database_url(_Settings(database_url=pg, apollo_database_url=other)) == "sqlite:///x.db"


def _child_env():
    """The child runs from another folder, with the backend on its path: settings are read from ``.env`` in the
    working directory, and a developer's real backend/.env (their own database!) must never reach these tests."""
    env = {k: v for k, v in os.environ.items() if k not in (*_OWN, "DATABASE_URL")}
    return {**env, "PYTHONUNBUFFERED": "1", "PYTHONPATH": str(BACKEND)}


class Server:
    def __init__(self, data_dir, dist):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "app.serve", "--port", "0", "--data-dir", str(data_dir), "--frontend-dist", str(dist)],
            cwd=data_dir.parent, env=_child_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
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
        cwd=tmp_path, env=_child_env(), capture_output=True, text=True, timeout=60,
    )
    assert out.returncode != 0 and "npm --prefix frontend run build" in (out.stderr + out.stdout)


# -- the database is created when it is missing (PostgreSQL) ---------------------------------------------


class _PgServer:
    """A fake PostgreSQL server: which databases exist, who may create one, whether pgvector is installed."""

    def __init__(self, databases=("postgres", "template1"), can_create=True, vector=True, connect_error=None):
        self.databases, self.can_create, self.vector, self.connect_error = set(databases), can_create, vector, connect_error
        self.statements = []

    def create_engine(self, url, **kwargs):
        return _FakeEngine(self, url.database)


class _Preparer:
    @staticmethod
    def quote(name):
        return name if name.isidentifier() else '"' + name + '"'


class _FakeEngine:
    dialect = type("D", (), {"identifier_preparer": _Preparer})()

    def __init__(self, server, database):
        self.server, self.database = server, database

    def connect(self):
        from sqlalchemy.exc import OperationalError

        if self.server.connect_error:
            raise OperationalError("connect", {}, Exception(self.server.connect_error))
        if self.database not in self.server.databases:
            raise OperationalError("connect", {}, Exception(f'FATAL:  database "{self.database}" does not exist'))
        return _FakeConnection(self.server)

    def dispose(self):
        pass


class _FakeConnection:
    def __init__(self, server):
        self.server = server

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement):
        from sqlalchemy.exc import ProgrammingError

        sql = str(statement)
        self.server.statements.append(sql)
        if sql.startswith("CREATE DATABASE"):
            if not self.server.can_create:
                raise ProgrammingError(sql, {}, Exception("permission denied to create database"))
            self.server.databases.add(sql.split("CREATE DATABASE ", 1)[1].strip('"'))
            return None
        return type("R", (), {"first": lambda _self: (1,) if self.server.vector else None})()


URL = "postgresql+psycopg2://apollo:secret@localhost:5432/apollo_desktop"


def test_a_missing_database_is_created(capsys):
    server = _PgServer()
    assert serve.ensure_database(URL, server.create_engine) is True
    assert "apollo_desktop" in server.databases
    assert "CREATE DATABASE apollo_desktop" in server.statements
    assert "Created database 'apollo_desktop'" in capsys.readouterr().out


def test_an_existing_database_is_left_alone():
    server = _PgServer(databases=("postgres", "apollo_desktop"))
    assert serve.ensure_database(URL, server.create_engine) is False
    assert not any(s.startswith("CREATE DATABASE") for s in server.statements)


def test_a_name_that_needs_quoting_is_quoted():
    server = _PgServer()
    serve.ensure_database(URL.replace("apollo_desktop", "mijn-apollo"), server.create_engine)
    assert 'CREATE DATABASE "mijn-apollo"' in server.statements and "mijn-apollo" in server.databases


def test_other_databases_are_not_touched():
    assert serve.ensure_database("sqlite:///x.db", lambda *a, **k: pytest.fail("no engine expected")) is False


def test_not_allowed_to_create_says_what_to_do():
    with pytest.raises(serve.DatabaseError) as err:
        serve.ensure_database(URL, _PgServer(can_create=False).create_engine)
    assert "CREATE DATABASE apollo_desktop" in str(err.value.code) and "'apollo'" in str(err.value.code)


def test_a_refused_password_and_an_unreachable_server_are_explained():
    with pytest.raises(serve.DatabaseError) as err:
        serve.ensure_database(URL, _PgServer(connect_error='FATAL:  password authentication failed for user "apollo"').create_engine)
    assert "refused the password for user 'apollo'" in str(err.value.code) and "backend/.env" in str(err.value.code)
    with pytest.raises(serve.DatabaseError) as err:
        serve.ensure_database(URL, _PgServer(connect_error="connection refused").create_engine)
    assert "Could not connect to PostgreSQL on localhost:5432" in str(err.value.code)


def test_missing_pgvector_points_at_the_installer():
    with pytest.raises(serve.DatabaseError) as err:
        serve.ensure_database(URL, _PgServer(databases=("apollo_desktop",), vector=False).create_engine)
    assert "pgvector" in str(err.value.code) and "install-pgvector-windows.ps1" in str(err.value.code)


@pytest.mark.skipif(not os.environ.get("APOLLO_TEST_PG_URL"), reason="set APOLLO_TEST_PG_URL to a PostgreSQL URL with pgvector")
def test_against_a_real_postgresql():
    """Creates a throw-away database next to the one in the URL, then drops it."""
    import uuid

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    base = make_url(os.environ["APOLLO_TEST_PG_URL"])
    name = f"apollo_test_{uuid.uuid4().hex[:8]}"
    url = base.set(database=name).render_as_string(hide_password=False)
    try:
        assert serve.ensure_database(url) is True
        assert serve.ensure_database(url) is False
    finally:
        admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()

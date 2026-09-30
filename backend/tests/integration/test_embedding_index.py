"""Switching embedding model: vectors of different models must never be compared."""
import io

import pytest

from app.core import embeddings as emb
from app.core.config import get_settings
from app.models import DocumentChunk
from app.services import llm_settings

_KEYS = [*llm_settings.FIELDS, "embedding_dimensions", "openai_api_key"]
TEXT = "The harbour renovation budget covers quay repairs and dredging work."


@pytest.fixture(autouse=True)
def restore_settings():
    s = get_settings()
    saved = {k: getattr(s, k) for k in _KEYS}
    emb.set_embedding_provider(None)
    yield
    for k, v in saved.items():
        setattr(s, k, v)
    emb.set_embedding_provider(None)


def _upload(client, ws_id, name="doc.txt", text=TEXT):
    d = client.post(
        "/api/documents", params={"workspace_id": ws_id}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}
    ).json()
    assert client.post(f"/api/documents/{d['id']}/index").json()["indexing_status"] == "indexed"
    return d["id"]


def _use_mock(client, model, dims=None):
    body = {"provider": "mock", "model": model}
    assert client.put("/api/embeddings/settings", json=body).status_code == 200
    if dims:
        get_settings().embedding_dimensions = dims
        emb.set_embedding_provider(None)


def test_chunks_record_the_model_and_dimension(client, db):
    ws = client.post("/api/workspaces", json={"name": "w"}).json()["id"]
    _upload(client, ws)
    chunk = db.query(DocumentChunk).first()
    assert (chunk.embedding_model, chunk.embedding_dim) == ("mock-embedder", 64)


def test_status_reports_nothing_stale_for_the_active_model(client):
    ws = client.post("/api/workspaces", json={"name": "w"}).json()["id"]
    _upload(client, ws)
    st = client.get("/api/embeddings/status").json()
    assert (st["model"], st["dimensions"], st["provider"]) == ("mock-embedder", 64, "mock")
    assert st["chunks_total"] == st["chunks_current"] == 1 and st["documents_stale"] == 0


def test_switching_model_hides_old_vectors_from_search_until_reindexed(client, db):
    ws = client.post("/api/workspaces", json={"name": "w"}).json()["id"]
    _upload(client, ws)
    assert client.get("/api/search", params={"q": "harbour budget", "workspace_id": ws}).json()["results"]

    _use_mock(client, "other-model", dims=32)  # a different model with another dimension
    st = client.get("/api/embeddings/status").json()
    assert st["model"] == "other-model" and st["dimensions"] == 32
    assert st["documents_stale"] == 1 and st["chunks_current"] == 0 and st["by_model"] == {"mock-embedder": 1}
    assert client.get("/api/search", params={"q": "harbour budget", "workspace_id": ws}).json()["results"] == [], "never compare across models"

    result = client.post("/api/embeddings/reindex").json()
    assert result["model"] == "other-model" and result["requested"] == 1 and result["reindexed"] == 1 and not result["failed"]
    db.expire_all()
    chunk = db.query(DocumentChunk).one()
    assert (chunk.embedding_model, chunk.embedding_dim, len(chunk.embedding)) == ("other-model", 32, 32)
    assert client.get("/api/search", params={"q": "harbour budget", "workspace_id": ws}).json()["results"]
    assert client.get("/api/embeddings/status").json()["documents_stale"] == 0
    # nothing left to do: a second reindex requests nothing
    assert client.post("/api/embeddings/reindex").json()["requested"] == 0
    assert client.post("/api/embeddings/reindex", params={"everything": True}).json()["requested"] == 1


def test_reindex_can_be_limited_to_one_werkmap(client):
    a = client.post("/api/workspaces", json={"name": "a"}).json()["id"]
    b = client.post("/api/workspaces", json={"name": "b"}).json()["id"]
    _upload(client, a, "a.txt")
    _upload(client, b, "b.txt")
    _use_mock(client, "other-model", dims=16)
    assert client.get("/api/embeddings/status", params={"workspace_id": a}).json()["documents_stale"] == 1
    assert client.post("/api/embeddings/reindex", params={"workspace_id": a}).json()["reindexed"] == 1
    assert client.get("/api/embeddings/status", params={"workspace_id": b}).json()["documents_stale"] == 1


def test_settings_roundtrip_hide_keys_and_validate(client, db):
    body = client.put(
        "/api/embeddings/settings",
        json={"provider": "openai", "model": "BAAI/bge-m3", "base_url": "http://localhost:11434/v1", "api_key": "secret", "batch_size": 16},
    ).json()
    assert (body["provider"], body["model"], body["base_url"], body["batch_size"], body["api_key_set"]) == (
        "openai", "BAAI/bge-m3", "http://localhost:11434/v1", 16, True,
    )
    assert "secret" not in str(body)
    # survives a restart
    s = get_settings()
    s.embedding_provider, s.embedding_model, s.embedding_api_key = "mock", "x", ""
    llm_settings.load_overrides(db)
    assert (s.embedding_provider, s.embedding_model, s.embedding_api_key) == ("openai", "BAAI/bge-m3", "secret")
    assert client.put("/api/embeddings/settings", json={"api_key": ""}).json()["api_key_set"] is False
    for bad in ({"provider": "x"}, {"runtime": "x"}, {"base_url": "ftp://x"}, {"batch_size": 0}):
        assert client.put("/api/embeddings/settings", json=bad).status_code == 400


def test_test_endpoint_reports_dimension_and_errors(client):
    ok = client.post("/api/embeddings/test").json()
    assert ok["ok"] and ok["dimensions"] == 64 and ok["model"] == "mock-embedder"
    client.put("/api/embeddings/settings", json={"provider": "openai", "base_url": "", "api_key": ""})
    get_settings().openai_api_key = ""
    emb.set_embedding_provider(None)
    bad = client.post("/api/embeddings/test").json()
    assert bad["ok"] is False and "API key" in bad["error"]
    assert client.get("/api/embeddings/status").json()["error"]

"""Indexing in the background: files are stored at once, the queue indexes them one after the other."""
import io
import time

from app.models import Document
from app.services.documents.index_queue import recover_interrupted_indexing


def _ws(client):
    return client.post("/api/workspaces", json={"name": "w"}).json()["id"]


def _upload(client, ws, name, text="The harbour budget is 250000 EUR."):
    resp = client.post("/api/documents", params={"workspace_id": ws}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _wait(client, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get("/api/documents/index-queue").json()
        if not status["active"]:
            return status
        time.sleep(0.1)
    raise AssertionError("the queue did not finish")


def test_an_idle_queue_reports_nothing(client):
    status = client.get("/api/documents/index-queue").json()
    assert (status["active"], status["total"], status["done"], status["failed"], status["current"]) == (False, 0, 0, 0, None)


def test_pending_documents_of_a_werkmap_are_indexed_in_the_background(client):
    ws = _ws(client)
    for i in range(3):
        _upload(client, ws, f"d{i}.txt", f"Document {i} about the harbour quay repairs.")
    assert {d["indexing_status"] for d in client.get("/api/documents", params={"workspace_id": ws}).json()} == {"pending"}

    started = client.post("/api/documents/index-queue", json={"workspace_id": ws}).json()
    assert started["added"] == 3 and started["total"] == 3, "the request returns at once; the work runs on"

    status = _wait(client)
    assert (status["total"], status["parsed"], status["done"], status["failed"]) == (3, 3, 3, 0)
    assert status["seconds_per_document"] is not None
    assert {d["indexing_status"] for d in client.get("/api/documents", params={"workspace_id": ws}).json()} == {"indexed"}
    assert client.get("/api/search", params={"q": "harbour quay", "workspace_id": ws}).json()["results"]


def test_only_pending_documents_of_that_werkmap_are_queued(client):
    a, b = _ws(client), _ws(client)
    _upload(client, a, "a.txt")
    _upload(client, b, "b.txt")
    assert client.post("/api/documents/index-queue", json={"workspace_id": a}).json()["added"] == 1
    _wait(client)
    again = client.post("/api/documents/index-queue", json={"workspace_id": a}).json()
    assert again["added"] == 0, "already indexed: nothing pending any more"
    statuses = {d["filename"]: d["indexing_status"] for d in client.get("/api/documents").json()}
    assert statuses == {"a.txt": "indexed", "b.txt": "pending"}


def test_a_document_is_queued_once(client):
    ws = _ws(client)
    doc = _upload(client, ws, "once.txt")
    first = client.post("/api/documents/index-queue", json={"document_ids": [doc["id"]]}).json()
    second = client.post("/api/documents/index-queue", json={"document_ids": [doc["id"]]}).json()
    assert first["added"] == 1 and (second["added"] == 0 or second["total"] == 1)
    assert _wait(client)["done"] == 1


def test_one_failing_document_does_not_stop_the_queue(client):
    ws = _ws(client)
    broken = client.post(
        "/api/documents", params={"workspace_id": ws}, files={"file": ("broken.pdf", io.BytesIO(b"%PDF-1.4 not really"), "application/pdf")}
    ).json()
    good = _upload(client, ws, "good.txt")
    client.post("/api/documents/index-queue", json={"document_ids": [broken["id"], good["id"]]})
    status = _wait(client)
    assert (status["total"], status["done"], status["failed"]) == (2, 1, 1)
    assert [e["filename"] for e in status["errors"]] == ["broken.pdf"] and status["errors"][0]["error"]
    by_name = {d["filename"]: d["indexing_status"] for d in client.get("/api/documents").json()}
    assert by_name == {"broken.pdf": "failed", "good.txt": "indexed"}


def test_documents_left_processing_by_a_stopped_app_become_pending_again(client, db):
    ws = _ws(client)
    doc = _upload(client, ws, "stuck.txt")
    db.query(Document).filter(Document.id == doc["id"]).update({"indexing_status": "processing"})
    db.commit()
    assert recover_interrupted_indexing() == 1
    assert client.get(f"/api/documents/{doc['id']}").json()["indexing_status"] == "pending"


class _DownProvider:
    name, model, dimensions = "down", "down-model", 4

    async def embed_documents(self, texts):
        raise RuntimeError("embedding server unreachable")

    async def embed_query(self, text):
        raise RuntimeError("embedding server unreachable")


def test_when_the_embedding_model_is_down_the_documents_are_still_read_and_found_by_words(client):
    from app.core import embeddings as emb

    emb.set_embedding_provider(_DownProvider())
    try:
        ws = _ws(client)
        for i in range(3):
            _upload(client, ws, f"d{i}.txt", f"Document {i} about the harbour quay repairs.")
        client.post("/api/documents/index-queue", json={"workspace_id": ws})
        status = _wait(client)
        assert (status["total"], status["parsed"], status["done"], status["failed"]) == (3, 3, 0, 3)
        assert all("Embedden mislukt" in (e["error"] or "") for e in status["errors"])
        docs = client.get("/api/documents", params={"workspace_id": ws}).json()
        assert {d["indexing_status"] for d in docs} == {"parsed"}
        hits = client.get("/api/search", params={"q": "harbour quay", "workspace_id": ws, "mode": "keyword"}).json()["results"]
        assert len(hits) == 3, "readable, and searchable by words, although nothing could be embedded"
        assert client.get(f"/api/documents/{docs[0]['id']}/text").json()["chunks"], "and the reading pane has its fragments"
    finally:
        emb.set_embedding_provider(None)

    # the model is back: the same button finishes what is left
    added = client.post("/api/documents/index-queue", json={"workspace_id": ws}).json()["added"]
    assert added == 3, "parsed documents wait for their vectors, they are queued again"
    status = _wait(client)
    assert (status["done"], status["failed"]) == (3, 0)
    assert {d["indexing_status"] for d in client.get("/api/documents", params={"workspace_id": ws}).json()} == {"indexed"}

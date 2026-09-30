import io


def _create_workspace(client, name):
    return client.post("/api/workspaces", json={"name": name}).json()


def _upload(client, workspace_id, name, content):
    resp = client.post(
        "/api/documents",
        params={"workspace_id": workspace_id},
        files={"file": (name, io.BytesIO(content.encode()), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    r = client.post(f"/api/documents/{doc['id']}/index")
    assert r.json()["indexing_status"] == "indexed"
    return doc


def test_workspace_crud(client):
    ws = _create_workspace(client, "Test Werkmap")
    assert ws["id"] > 0 and ws["name"] == "Test Werkmap"

    listed = client.get("/api/workspaces").json()
    assert any(w["id"] == ws["id"] for w in listed)

    detail = client.get(f"/api/workspaces/{ws['id']}").json()
    assert detail["name"] == "Test Werkmap"
    assert detail["document_count"] == 0

    assert client.delete(f"/api/workspaces/{ws['id']}").status_code == 204
    assert client.get(f"/api/workspaces/{ws['id']}").status_code == 404


def test_workspace_name_validation(client):
    assert client.post("/api/workspaces", json={"name": ""}).status_code == 422


def test_documents_scoped_to_workspace(client):
    ws_a = _create_workspace(client, "Alpha")
    ws_b = _create_workspace(client, "Beta")
    _upload(client, ws_a["id"], "a.txt", "The total approved budget is 25000 EUR.")
    _upload(client, ws_b["id"], "b.txt", "The total approved budget is 30000 EUR.")

    docs_a = client.get("/api/documents", params={"workspace_id": ws_a["id"]}).json()
    docs_b = client.get("/api/documents", params={"workspace_id": ws_b["id"]}).json()
    assert len(docs_a) == 1 and docs_a[0]["workspace_id"] == ws_a["id"]
    assert len(docs_b) == 1 and docs_b[0]["workspace_id"] == ws_b["id"]
    assert docs_a[0]["filename"] == "a.txt"
    assert docs_b[0]["filename"] == "b.txt"


def test_analysis_scoped_to_workspace(client):
    ws_a = _create_workspace(client, "Alpha")
    ws_b = _create_workspace(client, "Beta")
    _upload(client, ws_a["id"], "a.txt", "The total approved budget is 25000 EUR.")
    _upload(client, ws_b["id"], "b.txt", "The total approved budget is 30000 EUR. The team size is 5 people.")

    run_a = client.post("/api/analysis", params={"workspace_id": ws_a["id"]}).json()
    run_b = client.post("/api/analysis", params={"workspace_id": ws_b["id"]}).json()
    assert run_a["stats"]["documents_analyzed"] == 1
    assert run_b["stats"]["documents_analyzed"] == 1
    assert run_b["stats"]["claims"] >= 2

    # a contradiction between the two workspaces must NOT appear, because
    # each analysis only sees its own workspace's documents
    assert run_a["stats"]["contradictions"] == 0
    assert run_b["stats"]["contradictions"] == 0

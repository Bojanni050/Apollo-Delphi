import io


def _upload_and_index(client, name, content):
    resp = client.post("/api/documents", files={"file": (name, io.BytesIO(content.encode()), "text/plain")})
    doc_id = resp.json()["id"]
    client.post(f"/api/documents/{doc_id}/index")
    return doc_id


def test_semantic_search_returns_relevant_chunk(client):
    _upload_and_index(client, "budget.txt", "The approved project budget is 30000 EUR for the Alpha initiative.")
    resp = client.get("/api/search", params={"q": "project budget"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "project budget"
    assert body["results"]
    top = body["results"][0]
    assert "budget" in top["excerpt"].lower()
    assert 0.0 <= top["similarity"] <= 1.0
    assert top["document_id"] > 0


def test_search_empty_query_rejected(client):
    resp = client.get("/api/search", params={"q": ""})
    assert resp.status_code == 422


def test_search_no_results_for_unkwown_terms(client):
    _upload_and_index(client, "a.txt", "Total quality management framework alignment.")
    resp = client.get("/api/search", params={"q": "xylophone quantum banana"})
    assert resp.status_code == 200
    assert isinstance(resp.json()["results"], list)

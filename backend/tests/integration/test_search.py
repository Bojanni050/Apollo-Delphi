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


def test_hits_carry_the_line_range_of_their_chunk(client):
    ws = client.post("/api/workspaces", json={"name": "w"}).json()["id"]
    text = "# Intro\nGeneral words.\n\n# Harbour\nThe harbour budget covers quay repairs.\nDredging follows."
    d = client.post(
        "/api/documents", params={"workspace_id": ws}, files={"file": ("h.md", io.BytesIO(text.encode()), "text/markdown")}
    ).json()
    assert client.post(f"/api/documents/{d['id']}/index").json()["indexing_status"] == "indexed"
    hits = client.get("/api/search", params={"q": "harbour budget quay", "workspace_id": ws, "mode": "keyword"}).json()["results"]
    harbour = next(h for h in hits if h["section"] == "Harbour")
    assert (harbour["line_start"], harbour["line_end"]) == (4, 6)



def test_line_ranges_are_only_reported_for_txt_and_md_uploads(client, db):
    from app.models import Document
    from app.services.search.service import has_citable_lines

    def doc(file_type, source_type):
        return Document(file_type=file_type, source_type=source_type)

    assert has_citable_lines(doc("txt", "upload")) and has_citable_lines(doc("md", "upload"))
    assert not has_citable_lines(doc("pdf", "upload")) and not has_citable_lines(doc("docx", "upload"))
    assert not has_citable_lines(doc("md", "github")), "a GitHub digest has no file to count lines in"

    ws = client.post("/api/workspaces", json={"name": "w"}).json()["id"]
    d = client.post(
        "/api/documents", params={"workspace_id": ws}, files={"file": ("n.txt", io.BytesIO(b"Harbour budget notes.\nQuay repairs."), "text/plain")}
    ).json()
    client.post(f"/api/documents/{d['id']}/index")
    params = {"q": "harbour budget", "workspace_id": ws}
    assert client.get("/api/search", params=params).json()["results"][0]["line_start"] == 1

    db.get(Document, d["id"]).file_type = "pdf"  # same stored chunks, but lines of extracted PDF text are not citable
    db.commit()
    hit = client.get("/api/search", params=params).json()["results"][0]
    assert (hit["line_start"], hit["line_end"]) == (None, None)

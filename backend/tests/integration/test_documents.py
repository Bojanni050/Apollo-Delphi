from app.services.documents.service import DocumentValidationError, document_service, validate_upload


def test_upload_requires_allowed_extension(client):
    import io

    resp = client.post(
        "/api/documents",
        files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


def test_upload_rejects_empty_file(client):
    import io

    resp = client.post("/api/documents", files={"file": ("a.txt", io.BytesIO(b""), "text/plain")})
    assert resp.status_code == 400


def test_upload_rejects_path_traversal_filename(client):
    import io

    resp = client.post("/api/documents", files={"file": ("../../etc/passwd.txt", io.BytesIO(b"x"), "text/plain")})
    assert resp.status_code == 400


def test_upload_and_get_document(client):
    import io

    resp = client.post(
        "/api/documents",
        files={"file": ("notes.txt", io.BytesIO(b"The budget is 30000 EUR."), "text/plain")},
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["indexing_status"] == "pending"
    assert doc["file_type"] == "txt"

    got = client.get(f"/api/documents/{doc['id']}")
    assert got.status_code == 200
    assert got.json()["filename"] == "notes.txt"


def test_list_and_delete_documents(client):
    import io

    for i in range(2):
        client.post("/api/documents", files={"file": (f"d{i}.txt", io.BytesIO(b"content " * 50), "text/plain")})
    listed = client.get("/api/documents")
    assert len(listed.json()) >= 2
    doc_id = listed.json()[0]["id"]
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_indexing_pipeline_produces_chunks(client):
    import io

    resp = client.post(
        "/api/documents",
        files={"file": ("doc.md", io.BytesIO(b"# Budget\n\nThe budget is 30000 EUR."), "text/markdown")},
    )
    doc_id = resp.json()["id"]
    indexed = client.post(f"/api/documents/{doc_id}/index")
    assert indexed.status_code == 200
    body = indexed.json()
    assert body["indexing_status"] == "indexed"
    assert body["error_message"] is None


def test_failed_indexing_persists_error(client, db):
    import io

    resp = client.post(
        "/api/documents",
        files={"file": ("broken.docx", io.BytesIO(b"not really a docx"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    doc_id = resp.json()["id"]
    indexed = client.post(f"/api/documents/{doc_id}/index")
    assert indexed.status_code == 200
    body = indexed.json()
    assert body["indexing_status"] == "failed"
    assert body["error_message"]

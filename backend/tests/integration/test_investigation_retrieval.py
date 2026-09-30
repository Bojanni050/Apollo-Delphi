"""Regression: semantic retrieval during investigation must actually run.

The investigate endpoint runs inside an event loop; retrieval used to spin up a
second loop, fail silently and fall back to zero hits.
"""

import json

from app.models import DocumentChunk, Investigation
from app.services.search.service import SearchHit, SearchService
from tests.integration.test_e2e import DOC_A, DOC_B, DOC_C, _upload


def test_investigation_uses_semantic_hits(client, db, monkeypatch):
    _upload(client, "doc_a.txt", DOC_A)
    _upload(client, "doc_b.txt", DOC_B)
    memo = _upload(client, "doc_c.txt", DOC_C)
    client.post("/api/analysis")
    contra = next(i for i in client.get("/api/issues").json() if i["issue_type"] == "contradiction")

    chunk = db.query(DocumentChunk).filter(DocumentChunk.document_id == memo["id"]).first()
    calls = []

    async def fake_search(self, db_, query, top_k=None, document_ids=None):
        calls.append(query)
        return [
            SearchHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_filename="doc_c.txt",
                excerpt=chunk.content,
                page_number=None,
                section=None,
                similarity=0.9,
            )
        ]

    monkeypatch.setattr(SearchService, "search", fake_search)

    resp = client.post(f"/api/issues/{contra['id']}/investigate")
    assert resp.status_code == 200, resp.text
    assert calls, "semantic search was never executed"

    db.expire_all()
    investigation = db.query(Investigation).filter(Investigation.issue_id == contra["id"]).one()
    summary = json.loads(investigation.evidence_summary)
    assert any(e["document_id"] == memo["id"] for e in summary), "semantic hit missing from investigation evidence"

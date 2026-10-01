"""Hybrid search: exact tokens are found even when embeddings would not find them."""
import io

import pytest

from app.core import embeddings as emb
from app.core.embeddings import EmbeddingError


def _ws(client, name="w"):
    return client.post("/api/workspaces", json={"name": name}).json()["id"]


def _doc(client, ws_id, name, text):
    d = client.post(
        "/api/documents", params={"workspace_id": ws_id}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}
    ).json()
    assert client.post(f"/api/documents/{d['id']}/index").json()["indexing_status"] == "indexed"
    return d["id"]


def _search(client, ws, q, **params):
    return client.get("/api/search", params={"q": q, "workspace_id": ws, "top_k": 10, **params}).json()


def _corpus(client):
    ws = _ws(client)
    _doc(client, ws, "budget.txt", "The harbour renovation budget is 250000 EUR. Quay repairs and dredging are included.")
    _doc(client, ws, "sponsor.txt", "The project sponsor is Maria Chen. She reports to the city council every quarter.")
    _doc(client, ws, "decision.txt", "Decision record ADR-0042: we use PostgreSQL with pgvector for all vector storage.")
    _doc(client, ws, "party.txt", "The office summer party is on 20 June at the lakeside pavilion with fruit tarts.")
    return ws


@pytest.mark.parametrize(
    "query, expected",
    [("250000", "budget.txt"), ("Maria Chen", "sponsor.txt"), ("ADR-0042", "decision.txt")],
)
def test_exact_tokens_are_found_and_ranked_first(client, query, expected):
    ws = _corpus(client)
    result = _search(client, ws, query)
    assert result["mode"] == "hybrid"
    assert result["results"][0]["document_filename"] == expected
    assert result["results"][0]["match"] in ("keyword", "both")


def test_keyword_mode_finds_only_documents_that_contain_the_words(client):
    ws = _corpus(client)
    names = {r["document_filename"] for r in _search(client, ws, "pgvector storage", mode="keyword")["results"]}
    assert names == {"decision.txt"}
    assert {r["match"] for r in _search(client, ws, "pgvector storage", mode="keyword")["results"]} == {"keyword"}


def test_semantic_mode_returns_vector_hits_only(client):
    ws = _corpus(client)
    results = _search(client, ws, "harbour renovation budget", mode="semantic")["results"]
    assert results and {r["match"] for r in results} == {"semantic"}
    assert all(r["similarity"] >= 0 for r in results)


def test_hybrid_marks_which_leg_found_each_hit_and_scores_descend(client):
    ws = _corpus(client)
    results = _search(client, ws, "harbour renovation budget 250000")["results"]
    assert results[0]["document_filename"] == "budget.txt" and results[0]["match"] == "both"
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True) and scores[0] > 0
    # a document found by both legs scores above anything found by one leg alone
    assert results[0]["score"] > 1 / 61


def test_common_words_alone_do_not_match_everything(client):
    ws = _corpus(client)
    assert _search(client, ws, "what is the", mode="keyword")["results"] == []


def test_stale_embeddings_do_not_hide_keyword_hits(client):
    ws = _corpus(client)
    client.put("/api/embeddings/settings", json={"provider": "mock", "model": "another-model"})
    result = _search(client, ws, "ADR-0042")
    assert [r["document_filename"] for r in result["results"]][:1] == ["decision.txt"]
    assert result["results"][0]["match"] == "keyword"
    client.put("/api/embeddings/settings", json={"provider": "mock", "model": "mock-embedder"})


def test_hybrid_degrades_to_keyword_when_the_embedding_endpoint_fails(client, monkeypatch):
    ws = _corpus(client)

    async def broken(self, text):
        raise EmbeddingError("endpoint down")

    monkeypatch.setattr(emb.MockEmbeddingProvider, "embed_query", broken)
    degraded = _search(client, ws, "Maria Chen")
    assert degraded["mode"] == "keyword" and degraded["results"][0]["document_filename"] == "sponsor.txt"
    assert client.get("/api/search", params={"q": "x", "workspace_id": ws, "mode": "semantic"}).status_code == 503


def test_invalid_mode_is_rejected_and_scope_is_still_respected(client):
    ws = _corpus(client)
    other = _ws(client, "other")
    _doc(client, other, "elsewhere.txt", "Maria Chen also appears in another werkmap.")
    assert client.get("/api/search", params={"q": "x", "workspace_id": ws, "mode": "nope"}).status_code == 422
    names = {r["document_filename"] for r in _search(client, ws, "Maria Chen")["results"]}
    assert "elsewhere.txt" not in names and "sponsor.txt" in names

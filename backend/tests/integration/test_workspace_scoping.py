"""Search, issues, knowledge, analysis and generated documents are scoped per werkmap.

Rule everywhere: `workspace_id` selects a werkmap; omitting it selects only what belongs to no werkmap.
"""
import io

BUDGET_A = "Harbour Initial Budget\n\nThe total approved budget is 25000 EUR for the harbour.\n"
BUDGET_A2 = "Harbour Revised Budget\n\nThis revised proposal supersedes the initial budget proposal.\nThe total approved budget is 30000 EUR for the harbour.\n"
BUDGET_B = "Library Initial Budget\n\nThe total approved budget is 7000 EUR for the library.\n"
BUDGET_B2 = "Library Revised Budget\n\nThis revised proposal supersedes the initial budget proposal.\nThe total approved budget is 9000 EUR for the library.\n"
LOOSE = "Loose note\n\nThe team size is 4 people.\n"
LOOSE2 = "Loose memo\n\nThe team size is 6 people.\n"


def _ws(client, name):
    return client.post("/api/workspaces", json={"name": name}).json()["id"]


def _doc(client, ws_id, name, text):
    params = {"workspace_id": ws_id} if ws_id else {}
    d = client.post("/api/documents", params=params, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}).json()
    assert client.post(f"/api/documents/{d['id']}/index").json()["indexing_status"] == "indexed"
    return d["id"]


def _two_werkmappen(client):
    a, b = _ws(client, "harbour"), _ws(client, "library")
    _doc(client, a, "a1.txt", BUDGET_A)
    _doc(client, a, "a2.txt", BUDGET_A2)
    _doc(client, b, "b1.txt", BUDGET_B)
    _doc(client, b, "b2.txt", BUDGET_B2)
    run_a = client.post("/api/analysis", params={"workspace_id": a}).json()
    run_b = client.post("/api/analysis", params={"workspace_id": b}).json()
    return a, b, run_a, run_b


def _names(results):
    return {r["document_filename"] for r in results}


def test_search_only_sees_the_selected_werkmap(client):
    a, b, _, _ = _two_werkmappen(client)
    q = {"q": "total approved budget", "top_k": 20}
    assert _names(client.get("/api/search", params={**q, "workspace_id": a}).json()["results"]) == {"a1.txt", "a2.txt"}
    assert _names(client.get("/api/search", params={**q, "workspace_id": b}).json()["results"]) == {"b1.txt", "b2.txt"}
    assert client.get("/api/search", params=q).json()["results"] == [], "no werkmap = only unassigned documents"
    assert client.get("/api/search", params={**q, "workspace_id": 9999}).json()["results"] == []


def test_unassigned_documents_are_searched_only_without_a_werkmap(client):
    a, _, _, _ = _two_werkmappen(client)
    _doc(client, None, "loose.txt", LOOSE)
    q = {"q": "team size", "top_k": 20}
    assert _names(client.get("/api/search", params=q).json()["results"]) == {"loose.txt"}
    assert "loose.txt" not in _names(client.get("/api/search", params={**q, "workspace_id": a}).json()["results"])


def test_issues_are_listed_per_werkmap(client):
    a, b, run_a, run_b = _two_werkmappen(client)
    issues_a = client.get("/api/issues", params={"workspace_id": a}).json()
    issues_b = client.get("/api/issues", params={"workspace_id": b}).json()
    assert issues_a and issues_b
    assert {i["analysis_run_id"] for i in issues_a} == {run_a["id"]}
    assert {i["analysis_run_id"] for i in issues_b} == {run_b["id"]}
    assert client.get("/api/issues").json() == [], "no werkmap = only analyses that belong to no werkmap"
    assert client.get("/api/issues", params={"workspace_id": a, "status": "open"}).json()


def test_analysis_without_a_werkmap_only_reads_unassigned_documents(client):
    _two_werkmappen(client)
    _doc(client, None, "loose.txt", LOOSE)
    _doc(client, None, "loose2.txt", LOOSE2)
    run = client.post("/api/analysis").json()
    assert run["status"] == "completed" and run["stats"]["documents_analyzed"] == 2
    issues = client.get("/api/issues").json()
    assert issues and {i["analysis_run_id"] for i in issues} == {run["id"]}


def test_knowledge_is_the_latest_state_of_the_selected_werkmap(client):
    a, b, run_a, run_b = _two_werkmappen(client)
    client.post("/api/knowledge/build", params={"analysis_run_id": run_a["id"]})
    client.post("/api/knowledge/build", params={"analysis_run_id": run_b["id"]})

    ka = client.get("/api/knowledge", params={"workspace_id": a}).json()
    kb = client.get("/api/knowledge", params={"workspace_id": b}).json()
    assert ka and kb
    assert {k["analysis_run_id"] for k in ka} == {run_a["id"]}
    assert {k["analysis_run_id"] for k in kb} == {run_b["id"]}
    assert any("30000" in (k["statement"] or "") for k in ka) and not any("9000" in (k["statement"] or "") for k in ka)
    assert client.get("/api/knowledge").json() == [], "no werkmap = nothing unassigned was analysed"


def test_generated_documents_belong_to_their_werkmap(client):
    a, b, run_a, run_b = _two_werkmappen(client)
    client.post("/api/knowledge/build", params={"analysis_run_id": run_a["id"]})
    client.post("/api/knowledge/build", params={"analysis_run_id": run_b["id"]})

    doc_a = client.post("/api/documents/generate", params={"title": "Harbour report", "workspace_id": a}).json()
    doc_b = client.post("/api/documents/generate", params={"title": "Library report", "workspace_id": b}).json()
    assert doc_a["workspace_id"] == a and doc_b["workspace_id"] == b
    assert "30000" in doc_a["content"] and "9000" not in doc_a["content"], "a report only uses its own werkmap's knowledge"
    assert "9000" in doc_b["content"] and "30000" not in doc_b["content"]

    assert [d["id"] for d in client.get("/api/documents/generated/list", params={"workspace_id": a}).json()] == [doc_a["id"]]
    assert [d["id"] for d in client.get("/api/documents/generated/list", params={"workspace_id": b}).json()] == [doc_b["id"]]
    assert client.get("/api/documents/generated/list").json() == []
    # generating for a werkmap that was never analysed is an error, not someone else's knowledge
    c = _ws(client, "empty")
    assert client.post("/api/documents/generate", params={"workspace_id": c}).status_code == 400

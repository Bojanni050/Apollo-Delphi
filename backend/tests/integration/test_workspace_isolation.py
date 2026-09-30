"""A werkmap must not see another werkmap's documents while investigating."""
import io
import json

from app.models import Document, Investigation

# Werkmap A: budget 25000 -> 30000 (revised supersedes initial).
A_INITIAL = "Project Alpha Initial Budget\n\nThe total approved budget is 25000 EUR for Project Alpha.\n"
A_REVISED = "Project Alpha Revised Budget\n\nThis revised proposal supersedes the initial budget proposal.\nThe total approved budget is 30000 EUR for Project Alpha.\n"
# Werkmap B: similar wording, different numbers, and its own "supersedes" statement.
B_INITIAL = "Project Alpha Initial Budget\n\nThe total approved budget is 99000 EUR for Project Alpha.\n"
B_REVISED = "Project Alpha Revised Budget\n\nThis revised proposal supersedes the initial budget proposal.\nThe total approved budget is 11000 EUR for Project Alpha.\n"


def _ws(client, name):
    return client.post("/api/workspaces", json={"name": name}).json()["id"]


def _doc(client, ws_id, name, text):
    d = client.post(
        "/api/documents", params={"workspace_id": ws_id}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}
    ).json()
    assert client.post(f"/api/documents/{d['id']}/index").json()["indexing_status"] == "indexed"
    return d["id"]


def test_investigation_only_uses_evidence_from_its_own_werkmap(client, db):
    a, b = _ws(client, "A"), _ws(client, "B")
    _doc(client, a, "initial.txt", A_INITIAL)
    _doc(client, a, "revised.txt", A_REVISED)
    _doc(client, b, "initial.txt", B_INITIAL)
    _doc(client, b, "revised.txt", B_REVISED)

    run_a = client.post("/api/analysis", params={"workspace_id": a}).json()
    client.post("/api/analysis", params={"workspace_id": b})
    issue = next(
        i
        for i in client.get("/api/issues", params={"workspace_id": a}).json()
        if i["issue_type"] == "contradiction" and i["analysis_run_id"] == run_a["id"]
    )

    detail = client.post(f"/api/issues/{issue['id']}/investigate").json()
    assert "30000" in detail["resolution"]["conclusion"], detail["resolution"]

    db.expire_all()
    investigation = db.query(Investigation).filter(Investigation.issue_id == issue["id"]).one()
    used = {e["document_id"] for e in json.loads(investigation.evidence_summary)}
    foreign = {d.id for d in db.query(Document).filter(Document.workspace_id == b)}
    assert used, "the investigation should have evidence"
    assert not (used & foreign), "evidence from another werkmap leaked into the investigation"

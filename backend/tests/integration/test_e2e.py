"""End-to-end scenario: the core Apollo loop.

Upload A/B/C → index → analyze → claims → open questions → contradictions →
investigate → resolve → knowledge state → generate document → verify.
"""

import io
import json

DOC_A = """\
Project Alpha Initial Budget Proposal

The total approved budget is 25000 EUR for Project Alpha.
The team size is 4 people.
The final delivery date is TBD.
"""

DOC_B = """\
Project Alpha Revised Budget

This revised proposal supersedes the initial budget proposal for Project Alpha.
The total approved budget is 30000 EUR for Project Alpha.
The team size is 6 people.
"""

DOC_C = """\
Project Alpha Status Memo

The project sponsor is Maria Chen.
The final delivery date is 15 March 2025.
"""


def _upload(client, name, content):
    resp = client.post("/api/documents", files={"file": (name, io.BytesIO(content.encode()), "text/plain")})
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    r = client.post(f"/api/documents/{doc['id']}/index")
    assert r.status_code == 200, r.text
    assert r.json()["indexing_status"] == "indexed", r.json()
    return doc


def test_full_apollo_loop(client, db):
    # Phase 1: upload and index three documents
    _upload(client, "doc_a_initial.txt", DOC_A)
    _upload(client, "doc_b_revised.txt", DOC_B)
    _upload(client, "doc_c_memo.txt", DOC_C)
    docs = client.get("/api/documents").json()
    assert len(docs) == 3
    assert all(d["indexing_status"] == "indexed" for d in docs)

    # Phase 2: analyze the collection
    analysis = client.post("/api/analysis").json()
    assert analysis["status"] == "completed", analysis
    run_id = analysis["id"]
    assert analysis["stats"]["claims"] > 0
    assert analysis["stats"]["open_questions"] >= 1
    assert analysis["stats"]["contradictions"] >= 1

    # Phase 3: inspect claims
    claims = client.get(f"/api/analysis/{run_id}/claims").json()
    assert claims
    budget_claims = [c for c in claims if c["subject"] and "budget" in c["subject"].lower()]
    assert {c["value"] for c in budget_claims} >= {"25000", "30000"}

    # Phase 4: inspect issues — contradiction + open question
    issues = client.get("/api/issues").json()
    contradictions = [i for i in issues if i["issue_type"] == "contradiction"]
    open_questions = [i for i in issues if i["issue_type"] == "open_question"]
    assert contradictions, "expected at least one contradiction"
    assert open_questions, "expected at least one open question"

    contra = contradictions[0]
    detail = client.get(f"/api/issues/{contra['id']}").json()
    assert len(detail["claims"]) == 2
    assert detail["evidence"]
    assert {c["value"] for c in detail["claims"]} == {"25000", "30000"}
    # every piece of evidence points at the lines of its own file that hold the quoted text
    by_name = {"doc_a_initial.txt": DOC_A, "doc_b_revised.txt": DOC_B, "doc_c_memo.txt": DOC_C}
    texts = {d["id"]: by_name[d["filename"]] for d in client.get("/api/documents").json()}
    for e in detail["evidence"]:
        assert e["line_start"] is not None, e
        covered = "\n".join(texts[e["document_id"]].splitlines()[e["line_start"] - 1 : e["line_end"]])
        assert e["original_text"].strip() in covered, (e, covered)
    assert {(e["line_start"], e["line_end"]) for e in detail["evidence"]} == {(3, 3), (4, 4)}, "the quote's line, not the whole chunk"

    # Phase 5: investigate and resolve the contradiction
    resolved_detail = client.post(f"/api/issues/{contra['id']}/investigate").json()
    resolution = resolved_detail["resolution"]
    assert resolution is not None
    assert resolution["status"] == "resolved"
    assert "30000" in resolution["conclusion"]
    assert resolution["explanation_type"] in ("supersedes", "changed_over_time")
    assert resolution["reasoning"]

    # The open question must stay unresolved (evidence insufficient)
    oq_detail = client.get(f"/api/issues/{open_questions[0]['id']}").json()
    assert oq_detail["status"] in ("open", "unresolved")

    # Phase 6: human review — accept the resolution, then check persistence
    accept = client.post(
        f"/api/issues/{contra['id']}/resolve", json={"decision": "accept", "note": "reviewed"}
    ).json()
    assert accept["status"] == "resolved"

    # Phase 7: build knowledge state
    knowledge = client.post("/api/knowledge/build", params={"analysis_run_id": run_id}).json()
    types = {k["item_type"] for k in knowledge}
    assert "fact" in types
    assert "resolved_contradiction" in types
    facts = [k for k in knowledge if k["item_type"] == "fact"]
    assert any("budget" in k["statement"].lower() and "30000" in k["statement"] for k in facts + [k for k in knowledge if k["item_type"] == "resolved_contradiction"])

    # Phase 8: generate a document from the knowledge state
    generated = client.post(
        "/api/documents/generate", params={"title": "Project Alpha Report", "analysis_run_id": run_id}
    ).json()
    assert generated["status"] == "drafted"
    assert "30000" in generated["content"]
    assert generated["verification_status"] in ("passed", "passed_with_warnings", "failed")

    # Phase 9: verify the generated document
    findings = client.get(f"/api/documents/generated/{generated['id']}/verification").json()
    for f in findings:
        assert f["severity"] in ("info", "warning", "error")
        assert f["finding_type"]

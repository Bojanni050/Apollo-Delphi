"""Een rapport na een analyse: de vindingen op een rij als markdown, bewaard en als PDF te downloaden."""
import io

BUDGET_250 = "The harbour renovation budget is 250000 EUR. The quay repairs are included."
BUDGET_300 = "The harbour renovation budget is 300000 EUR. The quay repairs are included."


def _run_with_issues(client):
    ws = client.post("/api/workspaces", json={"name": "Rapport"}).json()["id"]
    for name, text in [("plan.md", BUDGET_250), ("besluit.md", BUDGET_300)]:
        doc = client.post(
            "/api/documents", params={"workspace_id": ws}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}
        ).json()
        client.post(f"/api/documents/{doc['id']}/index")
    run = client.post("/api/analysis", params={"workspace_id": ws}).json()
    return ws, run


def test_a_report_is_built_saved_and_downloadable_as_pdf(client, db):
    ws, run = _run_with_issues(client)
    assert run["stats"]["contradictions"] >= 1

    resp = client.post(f"/api/analysis/{run['id']}/report")
    assert resp.status_code == 201, resp.text
    report = resp.json()
    assert report["doc_kind"] == "report" and report["workspace_id"] == ws
    assert "Tegenstrijdigheden" in report["content"]
    assert "Samenvatting" in report["content"]

    # Het staat in de Generate-geschiedenis.
    listing = client.get("/api/documents/generated/list", params={"workspace_id": ws}).json()
    assert any(d["id"] == report["id"] for d in listing)

    pdf = client.get(f"/api/documents/generated/{report['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 500


def test_a_report_for_an_unknown_run_is_a_404(client):
    assert client.post("/api/analysis/99999/report").status_code == 404


def test_a_pdf_for_an_unknown_document_is_a_404(client):
    assert client.get("/api/documents/generated/99999/pdf").status_code == 404

"""Analysing one group of documents (or two, or all): the run only looks at those, so only they can contradict each other."""
import io

from app.models import Document

BUDGET_250 = "The harbour renovation budget is 250000 EUR. The quay repairs are included."
BUDGET_300 = "The harbour renovation budget is 300000 EUR. The quay repairs are included."
OTHER = "The project sponsor is Maria Chen. The steering group meets monthly."


def _setup(client, db):
    ws = client.post("/api/workspaces", json={"name": "Groepen"}).json()["id"]
    ids = {}
    for name, text, group in [
        ("plan.md", BUDGET_250, "architectuur"),
        ("besluit.md", BUDGET_300, "besluiten"),
        ("sponsor.md", OTHER, None),
    ]:
        doc = client.post(
            "/api/documents", params={"workspace_id": ws}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}
        ).json()
        client.post(f"/api/documents/{doc['id']}/index")
        db.query(Document).filter(Document.id == doc["id"]).update({"group_name": group})
        db.commit()  # right away: an open write transaction would lock the database for the next upload
        ids[name] = doc["id"]
    return ws, ids


def _run(client, ws, groups=()):
    params = [("workspace_id", ws), *[("groups", g) for g in groups]]
    resp = client.post("/api/analysis", params=params)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_without_groups_every_document_is_analysed_and_the_contradiction_is_found(client, db):
    ws, _ = _setup(client, db)
    run = _run(client, ws)
    assert run["stats"]["documents_analyzed"] == 3 and run["stats"]["contradictions"] >= 1
    assert run["stats"]["groups"] is None


def test_one_group_only_looks_at_its_own_documents(client, db):
    ws, _ = _setup(client, db)
    run = _run(client, ws, ["architectuur"])
    assert run["stats"]["documents_analyzed"] == 1 and run["stats"]["groups"] == ["architectuur"]
    assert run["stats"]["contradictions"] == 0, "the conflicting budget is in another group"


def test_two_groups_together_can_contradict_each_other(client, db):
    ws, _ = _setup(client, db)
    run = _run(client, ws, ["architectuur", "besluiten"])
    assert run["stats"]["documents_analyzed"] == 2 and run["stats"]["contradictions"] >= 1
    assert run["stats"]["groups"] == ["architectuur", "besluiten"]


def test_the_documents_without_a_group_can_be_chosen_too(client, db):
    ws, _ = _setup(client, db)
    assert _run(client, ws, ["__none__"])["stats"]["documents_analyzed"] == 1
    assert _run(client, ws, ["__none__", "besluiten"])["stats"]["documents_analyzed"] == 2


def test_an_unknown_group_analyses_nothing_and_does_not_fall_back_to_everything(client, db):
    ws, _ = _setup(client, db)
    assert _run(client, ws, ["bestaat-niet"])["stats"]["documents_analyzed"] == 0


def test_groups_of_another_werkmap_are_not_touched(client, db):
    ws, _ = _setup(client, db)
    other = client.post("/api/workspaces", json={"name": "Andere"}).json()["id"]
    doc = client.post(
        "/api/documents", params={"workspace_id": other}, files={"file": ("x.md", io.BytesIO(BUDGET_250.encode()), "text/plain")}
    ).json()
    client.post(f"/api/documents/{doc['id']}/index")
    db.query(Document).filter(Document.id == doc["id"]).update({"group_name": "architectuur"})
    db.commit()
    assert _run(client, ws, ["architectuur"])["stats"]["documents_analyzed"] == 1

"""The group filter of the issues list: only the issues whose documents belong to one group."""

import io

DOC_A = (
    "Project Alpha Initial Budget\n\nThe total approved budget is 25000 EUR for Project Alpha.\n"
    "The final delivery date is TBD."
)
DOC_B = "Project Alpha Revised Budget\n\nThe total approved budget is 30000 EUR for Project Alpha."
DOC_RECIPE = "Kitchen notes\n\nThe baking time of the sourdough is unclear."


def _ws(client):
    return client.post("/api/workspaces", json={"name": "Groepen"}).json()["id"]


def _doc(client, ws, name, text):
    doc = client.post(
        "/api/documents",
        params={"workspace_id": ws},
        files={"file": (name, io.BytesIO(text.encode()), "text/plain")},
        data={"relative_path": name},
    ).json()
    client.post(f"/api/documents/{doc['id']}/index")
    return doc


def _set_group(client, doc_id, group):
    """Give a document a group the way Delphi Pulse does when its suggestion is accepted."""
    from app.db.session import SessionLocal

    session = SessionLocal()
    from app.models import Document

    d = session.get(Document, doc_id)
    d.group_name = group
    session.commit()
    session.close()


def _setup(client):
    ws = _ws(client)
    a = _doc(client, ws, "alpha/initial.txt", DOC_A)
    b = _doc(client, ws, "alpha/revised.txt", DOC_B)
    c = _doc(client, ws, "keuken/notities.txt", DOC_RECIPE)
    _set_group(client, a["id"], "architectuur")
    _set_group(client, b["id"], "architectuur")
    _set_group(client, c["id"], "keuken")
    client.post(f"/api/analysis?workspace_id={ws}")
    return ws, a, b, c


def test_without_a_group_filter_every_issue_is_returned(client):
    ws, a, b, c = _setup(client)
    issues = client.get(f"/api/issues?workspace_id={ws}").json()
    assert issues, "the analysis found issues"


def test_a_group_filter_returns_only_that_groups_issues(client):
    ws, a, b, c = _setup(client)
    keuken = client.get(f"/api/issues?workspace_id={ws}&group=keuken").json()
    assert keuken, "the kitchen document has an open question"
    assert all(i["issue_type"] == "open_question" for i in keuken)
    architectuur = client.get(f"/api/issues?workspace_id={ws}&group=architectuur").json()
    assert architectuur, "the two budget documents contradict each other"
    assert any(i["issue_type"] == "contradiction" for i in architectuur)


def test_a_group_without_issues_gives_an_empty_list(client):
    ws, a, b, c = _setup(client)
    assert client.get(f"/api/issues?workspace_id={ws}&group=bestaatniet").json() == []


def test_the_none_group_holds_the_issues_of_ungrouped_documents(client):
    ws, a, b, c = _setup(client)
    from app.db.session import SessionLocal

    from app.models import Document

    session = SessionLocal()
    session.get(Document, a["id"]).group_name = None
    session.commit()
    session.close()
    zonder = client.get(f"/api/issues?workspace_id={ws}&group=__none__").json()
    assert zonder, "doc a (TBD) has an open question and is now without a group"
    # the contradiction still belongs to architectuur: doc b and its claims are still in that group
    met = client.get(f"/api/issues?workspace_id={ws}&group=architectuur").json()
    assert any(i["issue_type"] == "contradiction" for i in met)

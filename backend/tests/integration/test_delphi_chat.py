"""Delphi, the chat agent of a werkmap: her focus is the werkmap's documents and Apollo itself."""

import io

BUDGET_A = (
    "Budget planning for the harbour renovation project. The harbour renovation budget covers "
    "quay repairs and dredging. The harbour renovation budget is due in March."
)
BUDGET_B = (
    "Revised harbour renovation budget. Quay repairs and dredging costs increased, "
    "so the harbour budget changed and the due date moved to June."
)
RECIPE = "Recipe collection: sourdough bread, butter, flour and patience. Bake the sourdough slowly."


def _ws(client, name="Delphi"):
    return client.post("/api/workspaces", json={"name": name}).json()["id"]


def _doc(client, ws, name, text):
    doc = client.post(
        "/api/documents",
        params={"workspace_id": ws},
        files={"file": (name, io.BytesIO(text.encode()), "text/plain")},
        data={"relative_path": name},
    ).json()
    client.post(f"/api/documents/{doc['id']}/index")
    return doc


def _chat(client, ws, message, follow_up_of=None):
    return client.post(
        "/api/delphi/chat",
        json={"message": message, "workspace_id": ws, "follow_up_of": follow_up_of},
    )


def test_a_werkmap_without_documents_gets_a_polite_hint(client):
    ws = _ws(client)
    res = _chat(client, ws, "Wat staat er in de documenten?")
    assert res.status_code == 201
    body = res.json()
    assert body["user_message"]["role"] == "user" and body["user_message"]["parent_id"] is None
    assert body["reply"]["role"] == "delphi"
    assert body["reply"]["parent_id"] == body["user_message"]["id"]
    assert body["reply"]["refusal"] == "no_documents"
    assert "geen documenten" in body["reply"]["content"].lower()


def test_a_question_about_the_documents_is_answered(client):
    ws = _ws(client)
    _doc(client, ws, "architectuur/rapport-a.md", BUDGET_A)
    _doc(client, ws, "besluiten/rapport-b.md", BUDGET_B)
    res = _chat(client, ws, "Wanneer loopt het budget van de harbour renovation af?")
    assert res.status_code == 201
    answer = res.json()["reply"]["content"]
    assert res.json()["reply"]["refusal"] is None
    assert "harbour" in answer.lower() or "budget" in answer.lower()


def test_a_question_about_apollo_itself_is_answered_even_without_documents(client):
    ws = _ws(client)
    res = _chat(client, ws, "Wat is Apollo eigenlijk?")
    assert res.status_code == 201
    assert res.json()["reply"]["refusal"] is None
    assert "apollo" in res.json()["reply"]["content"].lower()


def test_follow_ups_stay_in_their_werkmap_and_conversation(client):
    ws = _ws(client)
    _doc(client, ws, "architectuur/rapport-a.md", BUDGET_A)
    first = _chat(client, ws, "Wat zegt het document over het budget?").json()
    res = _chat(client, ws, "En wanneer is het due?", follow_up_of=first["reply"]["id"])
    assert res.status_code == 201
    assert res.json()["user_message"]["parent_id"] == first["reply"]["id"]
    other = _ws(client, "Andere")
    res = _chat(client, other, "Vervolg", follow_up_of=first["reply"]["id"])
    assert res.status_code == 400


def test_history_returns_the_conversation_oldest_first(client):
    ws = _ws(client)
    _doc(client, ws, "architectuur/rapport-a.md", BUDGET_A)
    _chat(client, ws, "Eerste vraag over het budget")
    _chat(client, ws, "Tweede vraag over dredging")
    history = client.get(f"/api/delphi/history?workspace_id={ws}").json()
    assert [m["role"] for m in history] == ["user", "delphi", "user", "delphi"]
    assert history[0]["content"] == "Eerste vraag over het budget"
    assert history[-1]["role"] == "delphi"


def test_messages_of_another_werkmap_are_not_in_the_history(client):
    a = _ws(client, "A")
    b = _ws(client, "B")
    _doc(client, a, "architectuur/rapport-a.md", BUDGET_A)
    _chat(client, a, "Vraag over het budget van de haven")
    assert client.get(f"/api/delphi/history?workspace_id={b}").json() == []


def test_a_werkmap_that_does_not_exist_is_a_404(client):
    assert _chat(client, 99999, "Hallo").status_code == 404

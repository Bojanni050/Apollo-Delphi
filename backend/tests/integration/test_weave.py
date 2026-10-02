"""Delphi Weave: the groups, documents and connections as accepted in Delphi Pulse."""
import io

BUDGET_A = "Budget planning for the harbour renovation project. The harbour renovation budget covers quay repairs and dredging."
BUDGET_B = "Revised harbour renovation budget. Quay repairs and dredging costs increased, so the harbour budget changed."
UNRELATED = "Recipe collection: sourdough bread, butter, flour and patience. Bake the sourdough slowly."


def _ws(client, name="Weave"):
    return client.post("/api/workspaces", json={"name": name}).json()["id"]


def _doc(client, ws, name, text):
    doc = client.post(
        "/api/documents", params={"workspace_id": ws}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}, data={"relative_path": name}
    ).json()
    client.post(f"/api/documents/{doc['id']}/index")
    return doc


def _setup(client):
    ws = _ws(client)
    a = _doc(client, ws, "architectuur/rapport-a.md", BUDGET_A)
    b = _doc(client, ws, "besluiten/rapport-b.md", BUDGET_B)
    c = _doc(client, ws, "keuken/recepten.md", UNRELATED)
    client.post(f"/api/workspaces/{ws}/pulse")
    return ws, a, b, c


def test_an_empty_werkmap_has_an_empty_weave(client):
    ws = _ws(client)
    assert client.get(f"/api/workspaces/{ws}/weave").json() == {"documents": [], "connections": []}


def test_a_werkmap_that_does_not_exist_is_a_404(client):
    assert client.get("/api/workspaces/99999/weave").status_code == 404


def test_suggestions_that_are_still_open_are_not_part_of_the_weave(client):
    ws, a, b, c = _setup(client)
    weave = client.get(f"/api/workspaces/{ws}/weave").json()
    assert len(weave["documents"]) == 3, "every readable document is there"
    assert weave["connections"] == [] and all(d["group"] is None and d["tags"] == [] for d in weave["documents"])


def test_accepted_groups_folders_tags_and_connections_show_up(client):
    ws, a, b, c = _setup(client)
    assert client.post(f"/api/workspaces/{ws}/pulse/decision", json={"decision": "accepted"}).json()["decided"] == 3
    weave = client.get(f"/api/workspaces/{ws}/weave").json()
    docs = {d["id"]: d for d in weave["documents"]}
    assert (docs[a["id"]]["group"], docs[b["id"]]["group"], docs[c["id"]]["group"]) == ("architectuur", "besluiten", "keuken")
    assert docs[a["id"]]["folder"] == "Reports" and "harbour" in docs[a["id"]]["tags"]
    assert len(weave["connections"]) == 1, "a and b point at each other: one line, not two"
    link = weave["connections"][0]
    assert {link["source"], link["target"]} == {a["id"], b["id"]} and link["relation"] == "relates-to" and link["why"]


def test_dismissed_suggestions_leave_no_trace_in_the_weave(client):
    ws, a, b, c = _setup(client)
    client.post(f"/api/workspaces/{ws}/pulse/decision", json={"decision": "dismissed"})
    weave = client.get(f"/api/workspaces/{ws}/weave").json()
    assert weave["connections"] == [] and all(d["group"] is None for d in weave["documents"])


def test_the_weave_stays_inside_its_werkmap(client):
    ws, a, b, c = _setup(client)
    client.post(f"/api/workspaces/{ws}/pulse/decision", json={"decision": "accepted"})
    other = _ws(client, "Andere")
    assert client.get(f"/api/workspaces/{other}/weave").json() == {"documents": [], "connections": []}

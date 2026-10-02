import io
import json

import pytest

from app.core import llm
from app.core.llm import LLMProvider
from app.models import Document

BUDGET_A = "Budget planning for the harbour renovation project. The harbour renovation budget covers quay repairs and dredging."
BUDGET_B = "Revised harbour renovation budget. Quay repairs and dredging costs increased, so the harbour budget changed."
UNRELATED = "Recipe collection: sourdough bread, butter, flour and patience. Bake the sourdough slowly."


def _ws(client, name="Pulse"):
    return client.post("/api/workspaces", json={"name": name}).json()


def _doc(client, ws_id, name, text):
    r = client.post(
        "/api/documents",
        params={"workspace_id": ws_id},
        files={"file": (name, io.BytesIO(text.encode()), "text/plain")},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert client.post(f"/api/documents/{doc['id']}/index").json()["indexing_status"] == "indexed"
    return doc


def test_pulse_suggests_tags_and_connections_and_only_applies_on_accept(client, db):
    ws = _ws(client)
    a = _doc(client, ws["id"], "budget_a.txt", BUDGET_A)
    b = _doc(client, ws["id"], "budget_b.txt", BUDGET_B)
    c = _doc(client, ws["id"], "recipes.txt", UNRELATED)

    result = client.post(f"/api/workspaces/{ws['id']}/pulse").json()
    assert result["run"]["status"] == "completed"
    assert result["run"]["stats"]["analysed"] == 3
    items = {i["document_id"]: i for i in result["items"]}
    assert "harbour" in items[a["id"]]["tags"]
    assert [x["document_id"] for x in items[a["id"]]["connections"]] == [b["id"]]
    assert items[a["id"]]["connections"][0]["filename"] == "budget_b.txt"
    assert items[c["id"]]["connections"] == [], "unrelated document must not be connected"

    # nothing applied yet
    def meta():
        db.expire_all()
        return json.loads(db.get(Document, a["id"]).doc_metadata or "{}")

    assert "tags" not in meta()

    accepted = client.post(f"/api/pulse/items/{items[a['id']]['id']}/decision", json={"decision": "accepted"}).json()
    assert accepted["decision"] == "accepted"
    assert "harbour" in meta()["tags"] and meta()["connections"][0]["document_id"] == b["id"]
    pending = client.get(f"/api/workspaces/{ws['id']}/pulse").json()["items"]
    assert items[a["id"]]["id"] not in {i["id"] for i in pending}


def test_pulse_is_incremental_and_force_reanalyses(client):
    ws = _ws(client)
    _doc(client, ws["id"], "a.txt", BUDGET_A)
    first = client.post(f"/api/workspaces/{ws['id']}/pulse").json()
    assert first["run"]["stats"]["analysed"] == 1
    second = client.post(f"/api/workspaces/{ws['id']}/pulse").json()
    assert second["run"]["stats"]["analysed"] == 0 and second["run"]["stats"]["skipped"] == 1
    forced = client.post(f"/api/workspaces/{ws['id']}/pulse", params={"force": True}).json()
    assert forced["run"]["stats"]["analysed"] == 1


def test_pulse_is_scoped_to_its_werkmap(client):
    ws1, ws2 = _ws(client, "een"), _ws(client, "twee")
    _doc(client, ws1["id"], "budget_a.txt", BUDGET_A)
    _doc(client, ws2["id"], "budget_b.txt", BUDGET_B)
    r1 = client.post(f"/api/workspaces/{ws1['id']}/pulse").json()
    assert len(r1["items"]) == 1 and r1["items"][0]["connections"] == []


def test_dismiss_and_unknown_decision(client):
    ws = _ws(client)
    _doc(client, ws["id"], "a.txt", BUDGET_A)
    item = client.post(f"/api/workspaces/{ws['id']}/pulse").json()["items"][0]
    assert client.post(f"/api/pulse/items/{item['id']}/decision", json={"decision": "dismissed"}).json()["decision"] == "dismissed"
    assert client.post(f"/api/pulse/items/{item['id']}/decision", json={"decision": "nonsense"}).status_code == 400
    assert client.post("/api/pulse/items/9999/decision", json={"decision": "accepted"}).status_code == 404


class _ScriptedLLM(LLMProvider):
    """Stands in for a real model: replies with fixed JSON containing junk the boundary must drop."""

    name = "scripted"

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    async def complete(self, system, user, response_schema=None):
        self.calls += 1
        return self.reply(user) if callable(self.reply) else self.reply


@pytest.fixture
def scripted():
    def install(reply):
        provider = _ScriptedLLM(reply)
        llm.set_llm_provider(provider)
        return provider

    yield install
    llm.set_llm_provider(None)


def test_real_model_path_validates_ids_relations_and_tags(client, scripted):
    ws = _ws(client)
    a = _doc(client, ws["id"], "a.txt", BUDGET_A)
    b = _doc(client, ws["id"], "b.txt", BUDGET_B)

    def reply(_user):
        return json.dumps(
            {
                "documents": [
                    {
                        "id": str(a["id"]),
                        "summary": "Harbour budget.",
                        "tags": ["Budget", "budget", "  ", "harbour"],
                        "connections": [
                            {"id": str(b["id"]), "relation": "supports", "why": "Same project."},
                            {"id": "9999", "relation": "supports", "why": "hallucinated id"},
                            {"id": str(a["id"]), "relation": "supports", "why": "self"},
                            {"id": str(b["id"]), "relation": "loves", "why": "bad relation"},
                        ],
                        "confidence": 7,
                    },
                    {"id": "31337", "summary": "hallucinated document", "tags": ["x"]},
                ]
            }
        )

    provider = scripted(reply)
    result = client.post(f"/api/workspaces/{ws['id']}/pulse").json()
    assert provider.calls == 1, "both documents fit in one batch"
    assert result["run"]["provider"] == "scripted"
    assert len(result["items"]) == 1, "only real documents are reported"
    item = result["items"][0]
    assert item["tags"] == ["budget", "harbour"]
    assert [(c["document_id"], c["relation"]) for c in item["connections"]] == [(b["id"], "supports")]
    assert item["confidence"] == 1.0


def test_model_failure_marks_run_failed_without_items(client, scripted):
    ws = _ws(client)
    _doc(client, ws["id"], "a.txt", BUDGET_A)
    scripted("this is not json at all")
    result = client.post(f"/api/workspaces/{ws['id']}/pulse").json()
    assert result["run"]["status"] == "failed" and result["items"] == []
    assert "invalid JSON" in result["run"]["error_message"]


def test_accept_all_applies_every_open_suggestion_of_the_werkmap_only(client, db):
    ws1, ws2 = _ws(client, "een"), _ws(client, "twee")
    a = _doc(client, ws1["id"], "budget_a.txt", BUDGET_A)
    b = _doc(client, ws1["id"], "budget_b.txt", BUDGET_B)
    other = _doc(client, ws2["id"], "recipes.txt", UNRELATED)
    client.post(f"/api/workspaces/{ws1['id']}/pulse")
    client.post(f"/api/workspaces/{ws2['id']}/pulse")

    done = client.post(f"/api/workspaces/{ws1['id']}/pulse/decision", json={"decision": "accepted"}).json()
    assert done == {"decision": "accepted", "decided": 2}
    assert client.get(f"/api/workspaces/{ws1['id']}/pulse").json()["items"] == []
    assert len(client.get(f"/api/workspaces/{ws2['id']}/pulse").json()["items"]) == 1, "another werkmap is left alone"
    db.expire_all()
    assert "tags" in json.loads(db.get(Document, a["id"]).doc_metadata or "{}")
    assert "tags" in json.loads(db.get(Document, b["id"]).doc_metadata or "{}")
    assert "tags" not in json.loads(db.get(Document, other["id"]).doc_metadata or "{}")
    again = client.post(f"/api/workspaces/{ws1['id']}/pulse/decision", json={"decision": "accepted"}).json()
    assert again["decided"] == 0, "nothing left to decide"


def test_reject_all_changes_no_metadata_and_clears_the_list(client, db):
    ws = _ws(client)
    a = _doc(client, ws["id"], "budget_a.txt", BUDGET_A)
    _doc(client, ws["id"], "budget_b.txt", BUDGET_B)
    client.post(f"/api/workspaces/{ws['id']}/pulse")
    assert client.post(f"/api/workspaces/{ws['id']}/pulse/decision", json={"decision": "dismissed"}).json()["decided"] == 2
    assert client.get(f"/api/workspaces/{ws['id']}/pulse").json()["items"] == []
    db.expire_all()
    assert "tags" not in json.loads(db.get(Document, a["id"]).doc_metadata or "{}")


def test_deciding_all_validates_the_decision_and_the_werkmap(client):
    ws = _ws(client)
    assert client.post(f"/api/workspaces/{ws['id']}/pulse/decision", json={"decision": "maybe"}).status_code == 400
    assert client.post("/api/workspaces/99999/pulse/decision", json={"decision": "accepted"}).status_code == 404

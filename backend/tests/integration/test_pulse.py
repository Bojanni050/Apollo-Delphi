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


def _decisions(ws):
    from pathlib import Path

    path = Path(ws["working_dir"]) / "Decisions" / "decisions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def _messages(client, ws):
    return [c["message"] for c in client.get(f"/api/workspaces/{ws['id']}/history").json()]


def test_a_decision_is_committed_in_the_werkmap_repository(client):
    ws = _ws(client)
    a = _doc(client, ws["id"], "budget_a.txt", BUDGET_A)
    b = _doc(client, ws["id"], "budget_b.txt", BUDGET_B)
    items = {i["document_id"]: i for i in client.post(f"/api/workspaces/{ws['id']}/pulse").json()["items"]}

    client.post(f"/api/pulse/items/{items[a['id']]['id']}/decision", json={"decision": "accepted"})
    assert _messages(client, ws)[0] == "Pulse: accepted Other/budget_a.txt"
    [entry] = _decisions(ws)
    assert (entry["kind"], entry["decision"], entry["document"]) == ("pulse", "accepted", "Other/budget_a.txt")
    assert "harbour" in entry["tags"] and entry["connections"][0]["document"] == "Inbox/budget_b.txt", "names, not database ids"

    client.post(f"/api/pulse/items/{items[b['id']]['id']}/decision", json={"decision": "dismissed"})
    assert _messages(client, ws)[0] == "Pulse: dismissed Inbox/budget_b.txt"
    assert [e["decision"] for e in _decisions(ws)] == ["accepted", "dismissed"], "appended, never rewritten"


def test_deciding_all_is_one_commit_with_a_line_per_suggestion(client):
    ws = _ws(client)
    _doc(client, ws["id"], "budget_a.txt", BUDGET_A)
    _doc(client, ws["id"], "budget_b.txt", BUDGET_B)
    _doc(client, ws["id"], "recipes.txt", UNRELATED)
    client.post(f"/api/workspaces/{ws['id']}/pulse")
    before = len(_messages(client, ws))
    client.post(f"/api/workspaces/{ws['id']}/pulse/decision", json={"decision": "dismissed"})
    messages = _messages(client, ws)
    assert len(messages) == before + 1 and messages[0] == "Pulse: dismissed 3 suggestions"
    assert len(_decisions(ws)) == 3 and {e["decision"] for e in _decisions(ws)} == {"dismissed"}


def test_failing_to_log_does_not_undo_the_decision(client, db, monkeypatch):
    from app.services import workspace_repo

    def broken(*args, **kwargs):
        raise workspace_repo.GitError("git is not available")

    monkeypatch.setattr(workspace_repo, "record_decisions", broken)
    ws = _ws(client)
    a = _doc(client, ws["id"], "budget_a.txt", BUDGET_A)
    item = next(i for i in client.post(f"/api/workspaces/{ws['id']}/pulse").json()["items"] if i["document_id"] == a["id"])
    assert client.post(f"/api/pulse/items/{item['id']}/decision", json={"decision": "accepted"}).json()["decision"] == "accepted"
    db.expire_all()
    assert "tags" in json.loads(db.get(Document, a["id"]).doc_metadata or "{}")


# --- type folders (on disk) and groups (virtual folders) -----------------------------------------------------------------


def _upload_named(client, ws_id, name, text):
    r = client.post(
        "/api/documents", params={"workspace_id": ws_id}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}, data={"relative_path": name}
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    client.post(f"/api/documents/{doc['id']}/index")
    return doc


def _tree(ws):
    from pathlib import Path

    root = Path(ws["working_dir"])
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts and p.name != ".gitkeep")


def test_pulse_suggests_a_type_folder_and_a_group_and_applies_nothing_yet(client):
    ws = _ws(client)
    report = _upload_named(client, ws["id"], "Gaia/architectuur/rapport-haven.md", BUDGET_A)
    draft = _upload_named(client, ws["id"], "Gaia/foundation/draft-visie.md", UNRELATED)
    items = {i["document_id"]: i for i in client.post(f"/api/workspaces/{ws['id']}/pulse").json()["items"]}
    assert (items[report["id"]]["folder"], items[report["id"]]["group"]) == ("Reports", "architectuur")
    assert (items[draft["id"]]["folder"], items[draft["id"]]["group"]) == ("Drafts", "foundation")
    assert items[report["id"]]["folder_is_new"] is False
    assert _tree(ws) == ["Inbox/Gaia/architectuur/rapport-haven.md", "Inbox/Gaia/foundation/draft-visie.md"], "nothing moved yet"
    doc = client.get(f"/api/documents/{report['id']}").json()
    assert doc["group_name"] is None and doc["inbox_path"].startswith("Inbox/")


def test_accepting_moves_the_file_into_its_type_folder_and_sets_the_group(client):
    ws = _ws(client)
    report = _upload_named(client, ws["id"], "Gaia/architectuur/rapport-haven.md", BUDGET_A)
    items = client.post(f"/api/workspaces/{ws['id']}/pulse").json()["items"]
    client.post(f"/api/pulse/items/{items[0]['id']}/decision", json={"decision": "accepted"})

    assert _tree(ws) == ["Decisions/decisions.jsonl", "Reports/Gaia/architectuur/rapport-haven.md"], "moved, subfolders kept, Inbox emptied"
    doc = client.get(f"/api/documents/{report['id']}").json()
    assert doc["inbox_path"] == "Reports/Gaia/architectuur/rapport-haven.md" and doc["group_name"] == "architectuur"
    messages = _messages(client, ws)
    assert messages[1] == "Move Inbox/Gaia/architectuur/rapport-haven.md to Reports/", "the move is its own commit, before the decision"
    assert messages[0] == "Pulse: accepted Reports/Gaia/architectuur/rapport-haven.md"
    [entry] = _decisions(ws)
    assert (entry["folder"], entry["group"], entry["moved_to"]) == ("Reports", "architectuur", "Reports/Gaia/architectuur/rapport-haven.md")
    # the document itself is untouched: still readable and searchable
    assert client.get(f"/api/documents/{report['id']}/text").json()["text"].startswith("Budget planning")


def test_dismissing_moves_nothing_and_sets_no_group(client):
    ws = _ws(client)
    doc = _upload_named(client, ws["id"], "Gaia/architectuur/rapport-haven.md", BUDGET_A)
    item = client.post(f"/api/workspaces/{ws['id']}/pulse").json()["items"][0]
    client.post(f"/api/pulse/items/{item['id']}/decision", json={"decision": "dismissed"})
    assert "Inbox/Gaia/architectuur/rapport-haven.md" in _tree(ws)
    assert client.get(f"/api/documents/{doc['id']}").json()["group_name"] is None


def test_accept_all_moves_every_file_in_one_commit(client):
    ws = _ws(client)
    _upload_named(client, ws["id"], "a/rapport-een.md", BUDGET_A)
    _upload_named(client, ws["id"], "b/draft-twee.md", BUDGET_B)
    _upload_named(client, ws["id"], "c/hoofdstuk-drie.md", UNRELATED)
    client.post(f"/api/workspaces/{ws['id']}/pulse")
    before = len(_messages(client, ws))
    assert client.post(f"/api/workspaces/{ws['id']}/pulse/decision", json={"decision": "accepted"}).json()["decided"] == 3
    messages = _messages(client, ws)
    assert len(messages) == before + 2, "one commit for all the moves, one for the decisions"
    assert messages[1].startswith("Move 3 documents into type folders") and messages[0] == "Pulse: accepted 3 suggestions"
    assert [p for p in _tree(ws) if not p.startswith("Decisions")] == [
        "Chapters/c/hoofdstuk-drie.md", "Drafts/b/draft-twee.md", "Reports/a/rapport-een.md",
    ]


def test_a_taken_name_gets_a_number_and_nothing_is_overwritten(client):
    ws = _ws(client)
    first = _upload_named(client, ws["id"], "rapport.md", BUDGET_A)
    client.post(f"/api/workspaces/{ws['id']}/pulse")
    client.post(f"/api/workspaces/{ws['id']}/pulse/decision", json={"decision": "accepted"})
    second = _upload_named(client, ws["id"], "rapport.md", BUDGET_B)
    client.post(f"/api/workspaces/{ws['id']}/pulse")
    client.post(f"/api/workspaces/{ws['id']}/pulse/decision", json={"decision": "accepted"})
    assert [p for p in _tree(ws) if p.startswith("Reports/")] == ["Reports/rapport-2.md", "Reports/rapport.md"]
    assert client.get(f"/api/documents/{first['id']}").json()["inbox_path"] == "Reports/rapport.md"
    assert client.get(f"/api/documents/{second['id']}").json()["inbox_path"] == "Reports/rapport-2.md"


def test_a_missing_file_does_not_stop_the_decision(client):
    from pathlib import Path

    ws = _ws(client)
    doc = _upload_named(client, ws["id"], "Gaia/architectuur/rapport-haven.md", BUDGET_A)
    item = client.post(f"/api/workspaces/{ws['id']}/pulse").json()["items"][0]
    (Path(ws["working_dir"]) / "Inbox/Gaia/architectuur/rapport-haven.md").unlink()
    assert client.post(f"/api/pulse/items/{item['id']}/decision", json={"decision": "accepted"}).json()["decision"] == "accepted"
    out = client.get(f"/api/documents/{doc['id']}").json()
    assert out["group_name"] == "architectuur" and out["inbox_path"] == "Inbox/Gaia/architectuur/rapport-haven.md", "group set, path unchanged"


def test_folder_and_group_names_from_the_model_are_cleaned():
    from app.services import workspace_repo
    from app.services.pulse.service import _clean_group

    clean = workspace_repo.clean_folder_name
    assert [clean(x) for x in ["reports", "Report", "chapter", "Inbox", "../etc", "", None, "novella"]] == [
        "Reports", "Reports", "Chapters", None, "Etc", None, None, "Novella",
    ]
    assert _clean_group("  Foundation! ") == "foundation" and _clean_group("Architectuur / Basis") == "architectuur basis" and _clean_group("???") is None


def test_a_new_folder_is_marked_as_new_and_created_on_accepting(client, monkeypatch):
    from app.services.pulse import service as pulse

    original = pulse._mock_analyse

    def with_new_folder(texts, names, targets):
        out = original(texts, names, targets)
        for r in out.values():
            r["folder"] = "Novella"
        return out

    monkeypatch.setattr(pulse, "_mock_analyse", with_new_folder)
    ws = _ws(client)
    _upload_named(client, ws["id"], "boek/tekst.md", BUDGET_A)
    item = client.post(f"/api/workspaces/{ws['id']}/pulse").json()["items"][0]
    assert item["folder"] == "Novella" and item["folder_is_new"] is True
    client.post(f"/api/pulse/items/{item['id']}/decision", json={"decision": "accepted"})
    assert "Novella/boek/tekst.md" in _tree(ws)


def test_search_can_be_limited_to_a_group(client):
    ws = _ws(client)
    _upload_named(client, ws["id"], "Gaia/architectuur/rapport-haven.md", BUDGET_A)
    _upload_named(client, ws["id"], "Gaia/foundation/rapport-kade.md", BUDGET_B)
    items = client.post(f"/api/workspaces/{ws['id']}/pulse").json()["items"]
    first = next(i for i in items if i["group"] == "architectuur")
    client.post(f"/api/pulse/items/{first['id']}/decision", json={"decision": "accepted"})  # only this one gets its group

    def hits(**extra):
        return [h["document_filename"] for h in client.get("/api/search", params={"q": "harbour budget", "workspace_id": ws["id"], "mode": "keyword", **extra}).json()["results"]]

    assert len(set(hits())) == 2
    assert set(hits(group="architectuur")) == {"Gaia/architectuur/rapport-haven.md"}
    assert set(hits(group="__none__")) == {"Gaia/foundation/rapport-kade.md"}
    assert hits(group="bestaat-niet") == []

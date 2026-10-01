"""Question answering with citations: retrieval inside one werkmap, a checked answer, a stored history."""
import io

import pytest

from app.core import llm
from app.core.llm import LLMError, LLMProvider


def _ws(client, name="w"):
    return client.post("/api/workspaces", json={"name": name}).json()["id"]


def _doc(client, ws_id, name, text):
    d = client.post(
        "/api/documents", params={"workspace_id": ws_id}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}
    ).json()
    assert client.post(f"/api/documents/{d['id']}/index").json()["indexing_status"] == "indexed"
    return d["id"]


def _corpus(client):
    ws = _ws(client)
    _doc(client, ws, "budget.txt", "The harbour renovation budget is 250000 EUR. Quay repairs and dredging are included.")
    _doc(client, ws, "sponsor.txt", "The project sponsor is Maria Chen. She reports to the city council every quarter.")
    return ws


class Scripted(LLMProvider):
    """Stands in for a language model: returns a fixed answer and records what it was asked."""

    name = "scripted"

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete(self, system, user, response_schema=None):
        self.calls.append((system, user))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply(user) if callable(self.reply) else self.reply


@pytest.fixture
def model():
    def install(reply):
        provider = Scripted(reply)
        llm.set_llm_provider(provider)
        return provider

    yield install
    llm.set_llm_provider(None)


def _ask(client, ws, question):
    r = client.post("/api/ask", json={"question": question, "workspace_id": ws})
    assert r.status_code == 201, r.text
    return r.json()


def test_offline_answer_is_extractive_and_cited(client):
    ws = _corpus(client)
    a = _ask(client, ws, "What is the harbour renovation budget?")
    assert a["answered"] and a["grounded"] and a["model_provider"] == "mock"
    assert "250000 EUR" in a["answer"] and "[" in a["answer"]
    assert [c["document_filename"] for c in a["citations"]] == ["budget.txt"]
    assert "250000 EUR" in a["citations"][0]["excerpt"] and a["citations"][0]["n"] == 1


def test_offline_answer_admits_when_nothing_matches(client):
    ws = _corpus(client)
    a = _ask(client, ws, "How tall are giraffes?")
    assert a["answered"] is False and a["citations"] == [] and "niets over" in a["answer"]


def test_the_model_is_given_numbered_sources_from_the_werkmap_only(client, model):
    ws = _corpus(client)
    other = _ws(client, "other")
    _doc(client, other, "elsewhere.txt", "The budget in another werkmap is 111 EUR.")
    provider = model("The budget is 250000 EUR [1].")
    a = _ask(client, ws, "What is the budget?")
    system, user = provider.calls[0]
    assert "NO_ANSWER" in system and "ONLY" in system
    assert "[1] (file:" in user and "Question: What is the budget?" in user
    assert "elsewhere.txt" not in user and "111 EUR" not in user
    assert a["sources_considered"] == 2 and a["model_provider"] == "scripted"


def test_valid_citations_are_resolved_to_their_fragments(client, model):
    ws = _corpus(client)

    def reply(user):
        # cite whichever numbered source mentions the budget
        for line in user.split("\n\n"):
            if "250000 EUR" in line:
                return f"The budget is 250000 EUR {line.split(' ')[0]}."
        return "NO_ANSWER"

    model(reply)
    a = _ask(client, ws, "What is the budget?")
    assert a["grounded"] and a["warnings"] == []
    assert len(a["citations"]) == 1 and a["citations"][0]["document_filename"] == "budget.txt"
    assert f"[{a['citations'][0]['n']}]" in a["answer"]


def test_a_citation_to_an_unknown_source_is_removed_and_reported(client, model):
    ws = _corpus(client)
    model("The budget is 250000 EUR [1]. The sponsor is lovely [9].")
    a = _ask(client, ws, "Budget and sponsor?")
    assert "[9]" not in a["answer"] and "[1]" in a["answer"]
    assert any("[9]" in w and "niet bestaat" in w for w in a["warnings"])
    assert [c["n"] for c in a["citations"]] == [1]


def test_an_answer_without_any_citation_is_not_grounded(client, model):
    ws = _corpus(client)
    model("The budget is 250000 EUR.")
    a = _ask(client, ws, "What is the budget?")
    assert a["grounded"] is False and a["citations"] == []
    assert any("geen geldige bronvermelding" in w for w in a["warnings"])


def test_a_number_that_is_not_in_the_sources_is_flagged(client, model):
    ws = _corpus(client)
    model("The budget is 999999 EUR [1].")
    a = _ask(client, ws, "What is the budget?")
    assert a["grounded"] is False
    assert any("999999" in w for w in a["warnings"])


def test_no_answer_is_passed_on_honestly(client, model):
    ws = _corpus(client)
    model("NO_ANSWER")
    a = _ask(client, ws, "What is the airspeed of a swallow?")
    assert a["answered"] is False and a["citations"] == [] and a["answer"].startswith("In de documenten")


def test_an_empty_werkmap_does_not_call_the_model(client, model):
    provider = model("should never be used")
    empty = _ws(client, "empty")
    a = _ask(client, empty, "Anything?")
    assert a["answered"] is False and provider.calls == []


def test_history_is_per_werkmap_newest_first(client):
    ws = _corpus(client)
    other = _ws(client, "other")
    _doc(client, other, "x.txt", "Other werkmap text about libraries.")
    first = _ask(client, ws, "What is the harbour renovation budget?")
    second = _ask(client, ws, "Who is the project sponsor?")
    _ask(client, other, "What about libraries?")
    rows = client.get("/api/ask/history", params={"workspace_id": ws}).json()
    assert [r["id"] for r in rows] == [second["id"], first["id"]]
    assert rows[0]["citations"] and rows[0]["question"] == "Who is the project sponsor?"
    assert client.get("/api/ask/history").json() == [], "no werkmap = only unassigned"


def test_validation_and_failures(client, model):
    ws = _corpus(client)
    assert client.post("/api/ask", json={"question": "", "workspace_id": ws}).status_code == 422
    assert client.post("/api/ask", json={"question": "x", "workspace_id": 9999}).status_code == 404
    model(LLMError("model endpoint is down"))
    r = client.post("/api/ask", json={"question": "What is the budget?", "workspace_id": ws})
    assert r.status_code == 503 and "model endpoint is down" in r.json()["detail"]
    assert client.get("/api/ask/history", params={"workspace_id": ws}).json() == [], "a failed answer is not stored"


# -- follow-up questions -------------------------------------------------------------------------------


def _follow(client, ws, question, parent):
    r = client.post("/api/ask", json={"question": question, "workspace_id": ws, "follow_up_of": parent})
    assert r.status_code == 201, r.text
    return r.json()


def test_a_follow_up_is_retrieved_with_its_topic_and_linked_to_its_parent(client):
    ws = _corpus(client)
    first = _ask(client, ws, "What is the harbour renovation budget?")
    assert first["parent_id"] is None and first["standalone_question"] is None
    # on its own "And what does it include?" matches nothing; with the topic of the first question it does
    assert _ask(client, ws, "And what does it include?")["answered"] is False
    second = _follow(client, ws, "And what does it include?", first["id"])
    assert second["parent_id"] == first["id"]
    assert second["question"] == "And what does it include?"
    assert second["standalone_question"].startswith("What is the harbour renovation budget?")
    assert second["answered"] and [c["document_filename"] for c in second["citations"]] == ["budget.txt"]


def test_a_follow_up_to_a_follow_up_keeps_the_original_topic(client):
    ws = _corpus(client)
    first = _ask(client, ws, "What is the harbour renovation budget?")
    second = _follow(client, ws, "And what does it include?", first["id"])
    third = _follow(client, ws, "Are quay repairs part of it?", second["id"])
    assert third["standalone_question"].startswith("What is the harbour renovation budget?")
    assert third["parent_id"] == second["id"]


def test_the_model_rewrites_the_follow_up_and_sees_the_conversation_as_context(client, model):
    ws = _corpus(client)

    def reply(user):
        if user.startswith("Conversation:"):  # the rewrite call
            return "When is the harbour renovation budget due?"
        return "It is due in May [1]."

    provider = model(reply)
    first = _ask(client, ws, "What is the harbour renovation budget?")
    provider.calls.clear()
    second = _follow(client, ws, "And when is it due?", first["id"])

    rewrite, answer = provider.calls
    assert "Last question: And when is it due?" in rewrite[1] and "What is the harbour renovation budget?" in rewrite[1]
    assert second["standalone_question"] == "When is the harbour renovation budget due?"
    assert "NOT a source" in answer[1] and "Q: What is the harbour renovation budget?" in answer[1]
    assert "Question: And when is it due?" in answer[1]
    assert second["question"] == "And when is it due?"


def test_a_failing_rewrite_falls_back_to_the_previous_topic(client, model):
    ws = _corpus(client)

    def reply(user):
        if user.startswith("Conversation:"):
            raise LLMError("rewrite failed")
        return "The budget is 250000 EUR [1]."

    model(reply)
    first = _ask(client, ws, "What is the harbour renovation budget?")
    second = _follow(client, ws, "And what does it include?", first["id"])
    assert second["standalone_question"].startswith("What is the harbour renovation budget?")
    assert second["answered"]


def test_a_follow_up_still_has_to_be_backed_by_sources_of_its_own(client, model):
    """The earlier answer is context, not evidence: a number that only the conversation knows is flagged."""
    ws = _corpus(client)
    model(lambda user: "The deadline is 99999 days away [1]." if not user.startswith("Conversation:") else "Budget deadline?")
    first = _ask(client, ws, "What is the harbour renovation budget?")
    second = _follow(client, ws, "And the deadline?", first["id"])
    assert second["grounded"] is False and any("99999" in w for w in second["warnings"])


def test_only_the_most_recent_turns_are_given_as_context(client, model):
    from app.core.config import get_settings

    settings = get_settings()
    saved, settings.ask_history_turns = settings.ask_history_turns, 2
    try:
        ws = _corpus(client)
        provider = model(lambda user: "Budget topic" if user.startswith("Conversation:") else "250000 EUR [1]")
        a = _ask(client, ws, "What is the harbour renovation budget?")
        b = _follow(client, ws, "Second question about the budget?", a["id"])
        c = _follow(client, ws, "Third question about the budget?", b["id"])
        provider.calls.clear()
        _follow(client, ws, "Fourth question about the budget?", c["id"])
        rewrite_prompt = provider.calls[0][1]
        assert "Third question" in rewrite_prompt and "Second question" in rewrite_prompt
        assert "What is the harbour renovation budget?" not in rewrite_prompt
    finally:
        settings.ask_history_turns = saved


def test_follow_up_validation(client):
    ws = _corpus(client)
    other = _ws(client, "other")
    first = _ask(client, ws, "What is the harbour renovation budget?")
    missing = client.post("/api/ask", json={"question": "And?", "workspace_id": ws, "follow_up_of": 99999})
    assert missing.status_code == 404
    cross = client.post("/api/ask", json={"question": "And?", "workspace_id": other, "follow_up_of": first["id"]})
    assert cross.status_code == 400
    history = client.get("/api/ask/history", params={"workspace_id": ws}).json()
    assert history[0]["parent_id"] is None

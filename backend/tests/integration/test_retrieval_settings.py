"""Retrieval and question-answering knobs set in the UI: stored, applied at once, validated."""
import pytest

from app.core.config import get_settings
from app.models import AppSetting
from app.services import llm_settings

_KEYS = list(llm_settings.RETRIEVAL_RANGES)


@pytest.fixture(autouse=True)
def restore_settings():
    s = get_settings()
    saved = {k: getattr(s, k) for k in _KEYS}
    yield
    for k, v in saved.items():
        setattr(s, k, v)


def test_defaults_come_from_the_environment_settings(client):
    body = client.get("/api/retrieval/settings").json()
    assert body == {
        "search_top_k": 8, "search_rrf_k": 60, "search_candidate_multiplier": 5, "ask_top_k": 8, "ask_history_turns": 3,
    }


def test_partial_update_is_applied_stored_and_reloaded(client, db):
    body = client.put("/api/retrieval/settings", json={"ask_top_k": 12, "ask_history_turns": 5}).json()
    assert (body["ask_top_k"], body["ask_history_turns"], body["search_rrf_k"]) == (12, 5, 60)
    assert get_settings().ask_top_k == 12, "applied without a restart"
    assert db.get(AppSetting, "ask_top_k").value == "12"
    # survives a restart: the stored value wins over the environment default again
    get_settings().ask_top_k = 8
    llm_settings.load_overrides(db)
    assert get_settings().ask_top_k == 12 and get_settings().search_rrf_k == 60


def test_the_new_value_is_what_ask_uses(client):
    client.put("/api/retrieval/settings", json={"ask_top_k": 1})
    ws = client.post("/api/workspaces", json={"name": "w"}).json()["id"]
    import io

    for name, text in (("a.txt", "The harbour budget is 250000 EUR."), ("b.txt", "The harbour quay needs repairs.")):
        d = client.post(
            "/api/documents", params={"workspace_id": ws}, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}
        ).json()
        client.post(f"/api/documents/{d['id']}/index")
    answer = client.post("/api/ask", json={"question": "harbour", "workspace_id": ws}).json()
    assert answer["sources_considered"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"ask_top_k": 0}, {"ask_top_k": 31}, {"ask_history_turns": 0}, {"ask_history_turns": 11},
        {"search_top_k": 51}, {"search_rrf_k": 0}, {"search_candidate_multiplier": 51},
    ],
)
def test_out_of_range_values_are_rejected_and_not_applied(client, payload):
    before = client.get("/api/retrieval/settings").json()
    assert client.put("/api/retrieval/settings", json=payload).status_code == 400
    assert client.get("/api/retrieval/settings").json() == before

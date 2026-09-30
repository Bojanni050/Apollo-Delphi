import httpx
import pytest

from app.core import llm
from app.core.config import get_settings
from app.models import AppSetting
from app.services import llm_settings

_KEYS = list(llm_settings.FIELDS)


@pytest.fixture(autouse=True)
def restore_settings():
    s = get_settings()
    saved = {k: getattr(s, k) for k in _KEYS}
    llm.set_llm_provider(None)
    yield
    for k, v in saved.items():
        setattr(s, k, v)
    llm.set_llm_provider(None)


def test_defaults_come_from_environment_and_no_keys_leak(client):
    body = client.get("/api/llm/settings").json()
    assert body["provider"] == "mock"
    assert body["openai_key_set"] is False and body["anthropic_key_set"] is False
    assert "api_key" not in " ".join(body)


def test_changes_apply_immediately_and_persist(client, db):
    resp = client.put(
        "/api/llm/settings",
        json={"provider": "anthropic", "model": "claude-x", "background_model": "claude-small", "anthropic_api_key": "sk-secret"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "anthropic" and body["model"] == "claude-x" and body["anthropic_key_set"] is True
    assert "sk-secret" not in resp.text

    status = client.get("/api/llm/status").json()
    assert [(t["tier"], t["model"], t["configured"]) for t in status["tiers"]] == [
        ("main", "claude-x", True),
        ("background", "claude-small", True),
    ]
    assert isinstance(llm.get_llm_provider("background"), llm.AnthropicLLMProvider)
    assert db.get(AppSetting, "llm_model").value == "claude-x"

    # simulate a restart: wipe the in-memory values, then load from the database
    s = get_settings()
    s.llm_provider, s.llm_model, s.anthropic_api_key = "mock", "mock-model", ""
    llm_settings.load_overrides(db)
    assert (s.llm_provider, s.llm_model, s.anthropic_api_key) == ("anthropic", "claude-x", "sk-secret")


def test_partial_update_leaves_other_fields_and_empty_string_clears_key(client):
    client.put("/api/llm/settings", json={"provider": "openai", "model": "m1", "openai_api_key": "k1", "base_url": "http://localhost:11434/v1"})
    client.put("/api/llm/settings", json={"model": "m2"})
    body = client.get("/api/llm/settings").json()
    assert (body["provider"], body["model"], body["base_url"], body["openai_key_set"]) == ("openai", "m2", "http://localhost:11434/v1", True)
    client.put("/api/llm/settings", json={"openai_api_key": ""})
    assert client.get("/api/llm/settings").json()["openai_key_set"] is False


@pytest.mark.parametrize(
    "payload",
    [{"provider": "skynet"}, {"base_url": "ftp://x"}, {"timeout_seconds": 0}, {"timeout_seconds": 99999}],
)
def test_invalid_settings_are_rejected_and_not_applied(client, payload):
    assert client.put("/api/llm/settings", json=payload).status_code == 400
    assert client.get("/api/llm/settings").json()["provider"] == "mock"


def test_real_provider_without_model_or_key_is_reported_not_configured(client):
    client.put("/api/llm/settings", json={"provider": "anthropic", "model": ""})
    tiers = client.get("/api/llm/status").json()["tiers"]
    assert not any(t["configured"] for t in tiers) and "No model selected" in tiers[0]["error"]
    test = client.post("/api/llm/test").json()
    assert test["ok"] is False


@pytest.fixture
def fake_http(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "anthropic" in str(request.url):
            return httpx.Response(200, json={"data": [{"id": "claude-b"}, {"id": "claude-a"}]})
        return httpx.Response(200, json={"data": [{"id": "llama3"}, {"id": "mistral"}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


def test_model_picker_lists_local_runtime_without_key(client, fake_http):
    body = client.get("/api/llm/models", params={"provider": "openai", "base_url": "http://localhost:11434/v1"}).json()
    assert body == {"models": ["llama3", "mistral"], "error": None}
    assert "authorization" not in fake_http[0].headers


def test_model_picker_uses_saved_key_and_reports_problems(client, fake_http):
    missing = client.get("/api/llm/models", params={"provider": "anthropic"}).json()
    assert missing["models"] == [] and "API key" in missing["error"]
    client.put("/api/llm/settings", json={"anthropic_api_key": "sk-x"})
    body = client.get("/api/llm/models", params={"provider": "anthropic"}).json()
    assert body["models"] == ["claude-a", "claude-b"]
    assert fake_http[-1].headers["x-api-key"] == "sk-x"

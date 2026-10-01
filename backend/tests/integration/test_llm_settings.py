import httpx
import pytest

from app.core import llm
from app.core.config import get_settings
from app.models import AppSetting
from app.services import llm_settings

_KEYS = list(llm_settings.FIELDS)
EDEN = "https://api.edenai.run/v3"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"


@pytest.fixture(autouse=True)
def restore_settings():
    s = get_settings()
    saved = {k: getattr(s, k) for k in _KEYS}
    llm.set_llm_provider(None)
    yield
    for k, v in saved.items():
        setattr(s, k, v)
    llm.set_llm_provider(None)


def _put(client, **body):
    resp = client.put("/api/llm/settings", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _two_vendors(client):
    return _put(
        client,
        main={"provider": "openai", "base_url": EDEN, "api_key": "key-main", "model": "deepseek-x"},
        background={"provider": "openai", "base_url": GEMINI, "api_key": "key-bg", "model": "gemini-x"},
    )


def test_defaults_come_from_environment_and_no_keys_leak(client):
    body = client.get("/api/llm/settings").json()
    assert body["main"]["provider"] == "mock" and body["main"]["api_key_set"] is False
    assert body["background"] == {"provider": "", "model": "", "base_url": "", "api_key_set": False}
    assert "key-" not in str(body)


def test_two_tiers_use_their_own_endpoint_key_and_model(client, db):
    body = _two_vendors(client)
    assert body["main"]["api_key_set"] and body["background"]["api_key_set"]
    assert "key-main" not in str(body) and "key-bg" not in str(body)

    main, bg = llm.get_llm_provider("main"), llm.get_llm_provider("background")
    assert (main.base_url, main.api_key, main.model) == (EDEN, "key-main", "deepseek-x")
    assert (bg.base_url, bg.api_key, bg.model) == (GEMINI.rstrip("/"), "key-bg", "gemini-x")

    status = {t["tier"]: t for t in client.get("/api/llm/status").json()["tiers"]}
    assert status["main"]["model"] == "deepseek-x" and status["background"]["model"] == "gemini-x"
    assert status["main"]["configured"] and status["background"]["configured"]
    assert db.get(AppSetting, "background_llm_model").value == "gemini-x"

    # survives a restart
    s = get_settings()
    for k in ("llm_model", "background_llm_model", "llm_api_key", "background_llm_api_key"):
        setattr(s, k, "")
    llm_settings.load_overrides(db)
    assert llm.get_llm_provider("background").api_key == "key-bg"


def test_background_follows_main_when_left_empty(client):
    _put(client, main={"provider": "openai", "base_url": EDEN, "api_key": "key-main", "model": "deepseek-x"})
    cfg = llm.tier_config("background")
    assert (cfg.provider, cfg.base_url, cfg.model, cfg.api_key, cfg.inherits) == ("openai", EDEN, "deepseek-x", "key-main", True)
    _put(client, background={"model": "cheaper"})  # own model, same endpoint and key
    cfg = llm.tier_config("background")
    assert (cfg.model, cfg.api_key, cfg.base_url, cfg.inherits) == ("cheaper", "key-main", EDEN, False)


def test_main_key_is_never_sent_to_a_different_background_endpoint(client):
    _put(
        client,
        main={"provider": "openai", "base_url": EDEN, "api_key": "key-main", "model": "m"},
        background={"base_url": GEMINI, "model": "g"},  # no key of its own
    )
    cfg = llm.tier_config("background")
    assert cfg.base_url == GEMINI and cfg.api_key == ""
    assert llm.get_llm_provider("background").api_key == "", "sent without a key rather than with main's"


def test_background_can_be_another_provider_and_model_is_not_borrowed(client):
    _put(
        client,
        main={"provider": "openai", "base_url": EDEN, "api_key": "key-main", "model": "deepseek-x"},
        background={"provider": "anthropic", "api_key": "sk-ant"},
    )
    cfg = llm.tier_config("background")
    assert (cfg.provider, cfg.api_key, cfg.model) == ("anthropic", "sk-ant", ""), "main's model must not be borrowed across endpoints"
    status = {t["tier"]: t for t in client.get("/api/llm/status").json()["tiers"]}
    assert status["background"]["configured"] is False
    assert "no model selected" in status["background"]["error"].lower()
    _put(client, background={"model": "claude-small"})
    assert isinstance(llm.get_llm_provider("background"), llm.AnthropicLLMProvider)
    assert isinstance(llm.get_llm_provider("main"), llm.OpenAICompatibleLLMProvider)


def test_partial_update_and_empty_string_clears_key(client):
    _put(client, main={"provider": "openai", "model": "m1", "api_key": "k1", "base_url": "http://localhost:11434/v1"})
    _put(client, main={"model": "m2"})
    main = client.get("/api/llm/settings").json()["main"]
    assert (main["provider"], main["model"], main["base_url"], main["api_key_set"]) == ("openai", "m2", "http://localhost:11434/v1", True)
    _put(client, main={"api_key": ""})
    assert client.get("/api/llm/settings").json()["main"]["api_key_set"] is False


def test_legacy_provider_keys_still_work_for_main(client):
    s = get_settings()
    s.llm_provider, s.llm_model, s.openai_api_key = "openai", "m", "env-key"
    llm.set_llm_provider(None)
    assert llm.get_llm_provider("main").api_key == "env-key"
    assert llm.tier_config("background").api_key == "env-key"  # follows main's endpoint


@pytest.mark.parametrize(
    "payload",
    [
        {"main": {"provider": "skynet"}},
        {"background": {"provider": "skynet"}},
        {"main": {"base_url": "ftp://x"}},
        {"background": {"base_url": "gemini.google.com"}},
        {"timeout_seconds": 0},
        {"timeout_seconds": 99999},
    ],
)
def test_invalid_settings_are_rejected_and_not_applied(client, payload):
    assert client.put("/api/llm/settings", json=payload).status_code == 400
    assert client.get("/api/llm/settings").json()["main"]["provider"] == "mock"


def test_real_provider_without_model_is_reported_not_configured(client):
    _put(client, main={"provider": "anthropic", "model": "", "api_key": "k"})
    tiers = client.get("/api/llm/status").json()["tiers"]
    assert tiers[0]["configured"] is False and "no model selected" in tiers[0]["error"].lower()
    assert client.post("/api/llm/test").json()["ok"] is False


@pytest.fixture
def fake_http(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "anthropic" in str(request.url):
            return httpx.Response(200, json={"data": [{"id": "claude-b"}, {"id": "claude-a"}]})
        return httpx.Response(200, json={"data": [{"id": "llama3"}, {"id": "mistral"}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "verify"}))
    return seen


def test_model_picker_lists_local_runtime_without_key(client, fake_http):
    body = client.get("/api/llm/models", params={"provider": "openai", "base_url": "http://localhost:11434/v1"}).json()
    assert body == {"models": ["llama3", "mistral"], "error": None}
    assert "authorization" not in fake_http[0].headers


def test_model_picker_asks_the_tiers_own_endpoint_with_its_own_key(client, fake_http):
    _two_vendors(client)
    client.get("/api/llm/models", params={"tier": "main"})
    client.get("/api/llm/models", params={"tier": "background"})
    main_req, bg_req = fake_http
    assert str(main_req.url).startswith(EDEN) and main_req.headers["authorization"] == "Bearer key-main"
    assert str(bg_req.url).startswith(GEMINI.rstrip("/")) and bg_req.headers["authorization"] == "Bearer key-bg"


def test_model_picker_reports_problems(client, fake_http):
    missing = client.get("/api/llm/models", params={"provider": "anthropic"}).json()
    assert missing["models"] == [] and "API key" in missing["error"]


def _post_models(client, **body):
    return client.post("/api/llm/models", json=body).json()


def test_models_can_be_listed_with_a_key_that_is_not_saved_yet(client, fake_http):
    body = _post_models(client, tier="main", provider="openai", base_url=EDEN, api_key="typed-not-saved")
    assert body == {"models": ["llama3", "mistral"], "error": None}
    assert str(fake_http[0].url).startswith(EDEN) and fake_http[0].headers["authorization"] == "Bearer typed-not-saved"
    assert client.get("/api/llm/settings").json()["main"]["api_key_set"] is False, "nothing was saved"


def test_a_saved_key_is_used_while_the_endpoint_is_unchanged_but_never_for_another_one(client, fake_http):
    _put(client, main={"provider": "openai", "base_url": EDEN, "model": "m", "api_key": "saved-key"})
    _post_models(client, tier="main")  # untouched form: the saved endpoint and key
    _post_models(client, tier="main", provider="openai", base_url=GEMINI)  # someone trying another address
    same, other = fake_http
    assert same.headers["authorization"] == "Bearer saved-key"
    assert "authorization" not in other.headers, "the stored key must not follow a typed-in address"


def test_posted_models_report_problems_and_keep_the_key_out_of_the_error(client, fake_http):
    missing = _post_models(client, provider="anthropic")
    assert missing["models"] == [] and "API key" in missing["error"]
    ok = _post_models(client, provider="anthropic", api_key="sk-secret")
    assert ok["models"] == ["claude-a", "claude-b"] and "sk-secret" not in str(ok)

import json

import httpx
import pytest
from pydantic import BaseModel

from app.core import llm
from app.core.config import get_settings


class Answer(BaseModel):
    value: int


@pytest.fixture
def fake_http(monkeypatch):
    """Route every httpx.AsyncClient through a MockTransport; returns the list of seen requests."""
    class Seen(list):
        responses: list = []

    seen = Seen()
    responses = seen.responses = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses.pop(0)

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(llm.asyncio, "sleep", lambda *_: _noop())
    return seen


async def _noop():
    return None


async def test_openai_compatible_local_runtime_without_key(fake_http):
    fake_http.responses.append(httpx.Response(200, json={"choices": [{"message": {"content": '{"value": 7}'}}]}))
    p = llm.OpenAICompatibleLLMProvider("llama3", base_url="http://localhost:11434/v1/")
    out = await p.complete_json("sys", "user", Answer)
    assert out.value == 7
    req = fake_http[0]
    assert str(req.url) == "http://localhost:11434/v1/chat/completions"
    assert "authorization" not in req.headers
    assert json.loads(req.content)["response_format"] == {"type": "json_object"}


async def test_anthropic_request_shape_and_schema_instruction(fake_http):
    fake_http.responses.append(httpx.Response(200, json={"content": [{"type": "text", "text": '```json\n{"value": 3}\n```'}]}))
    p = llm.AnthropicLLMProvider("claude-x", "sk-test")
    out = await p.complete_json("be precise", "question", Answer)
    assert out.value == 3
    req = fake_http[0]
    body = json.loads(req.content)
    assert str(req.url) == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "sk-test" and req.headers["anthropic-version"]
    assert body["messages"] == [{"role": "user", "content": "question"}]
    assert body["system"].startswith("be precise") and '"value"' in body["system"]


async def test_retries_once_on_5xx_then_succeeds(fake_http):
    fake_http.responses += [httpx.Response(503, text="busy"), httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})]
    assert await llm.OpenAICompatibleLLMProvider("m", "k").complete("s", "u") == "ok"
    assert len(fake_http) == 2


async def test_client_error_is_not_retried_and_surfaces(fake_http):
    fake_http.responses.append(httpx.Response(401, text="bad key"))
    with pytest.raises(llm.LLMError, match="401"):
        await llm.AnthropicLLMProvider("m", "wrong").complete("s", "u")
    assert len(fake_http) == 1


def test_provider_selection_and_tiers(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "anthropic")
    monkeypatch.setattr(s, "anthropic_api_key", "k")
    monkeypatch.setattr(s, "llm_model", "big")
    monkeypatch.setattr(s, "background_llm_model", "small")
    llm.set_llm_provider(None)
    try:
        assert isinstance(llm.get_llm_provider("main"), llm.AnthropicLLMProvider)
        assert llm.get_llm_provider("main").model == "big"
        assert llm.get_llm_provider("background").model == "small"
        monkeypatch.setattr(s, "anthropic_api_key", "")
        llm.set_llm_provider(None)
        with pytest.raises(llm.LLMError, match="Anthropic API key"):
            llm.get_llm_provider()
    finally:
        monkeypatch.undo()
        llm.set_llm_provider(None)


def test_status_endpoint_never_leaks_keys(client):
    body = client.get("/api/llm/status").json()
    assert all(t["provider"] == "mock" and t["configured"] for t in body["tiers"])
    assert client.post("/api/llm/test").json()["ok"] is True


async def test_complete_json_tolerates_dotted_keys(fake_http):
    """Regression: a model returning {".value": ...} must validate, not raise."""
    fake_http.responses.append(httpx.Response(200, json={"choices": [{"message": {"content": '{".value": 3}'}}]}))
    p = llm.OpenAICompatibleLLMProvider("llama3", base_url="http://localhost:11434/v1/")
    out = await p.complete_json("sys", "user", Answer)
    assert out.value == 3

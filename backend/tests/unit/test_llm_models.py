"""What a /models answer says about each model: name, provider, description, context and price per 1M tokens."""
import pytest

from app.core.llm_models import MAX_DESCRIPTION, ModelInfo, model_info

# the shapes the real endpoints answer with (trimmed)
OPENROUTER = {
    "id": "openai/gpt-6.1-sol-pro",
    "name": "OpenAI: GPT-6.1 Sol Pro",
    "description": "A strong model.",
    "context_length": 1050000,
    "pricing": {"prompt": "0.000002", "completion": "0.00001", "web_search": "0.01"},
    "top_provider": {"context_length": 1050000},
}
EDENAI = {
    "id": "deepinfra/anthropic/claude-sonnet-5-5",
    "owned_by": "deepinfra",
    "model_name": "anthropic/claude-sonnet-5-5",
    "context_length": 1000000,
    "description": "",
    "pricing": {"input_cost_per_token": 2e-6, "output_cost_per_token": 0.00001},
}


def test_openrouter_entry():
    assert model_info(OPENROUTER) == ModelInfo(
        id="openai/gpt-6.1-sol-pro", name="OpenAI: GPT-6.1 Sol Pro", provider="openai", description="A strong model.",
        context_length=1050000, input_per_million=2.0, output_per_million=10.0,
    )


def test_edenai_entry():
    info = model_info(EDENAI)
    assert (info.provider, info.name, info.description) == ("deepinfra", "anthropic/claude-sonnet-5-5", None)
    assert (info.context_length, info.input_per_million, info.output_per_million) == (1000000, 2.0, 10.0)


def test_free_models_are_zero_not_missing():
    info = model_info({"id": "x/free", "pricing": {"prompt": "0", "completion": "0"}})
    assert (info.input_per_million, info.output_per_million) == (0.0, 0.0)


@pytest.mark.parametrize("pricing", [{}, {"prompt": "-1", "completion": "-1"}, {"prompt": "n/a"}, None])
def test_unknown_or_variable_prices_are_none(pricing):
    info = model_info({"id": "openrouter/auto", "pricing": pricing})
    assert info.input_per_million is None and info.output_per_million is None


def test_a_plain_openai_entry_has_only_an_id():
    info = model_info({"id": "gpt-4o", "object": "model", "owned_by": "system"})
    assert info == ModelInfo(id="gpt-4o")


def test_anthropic_entry_uses_its_display_name():
    info = model_info({"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5"})
    assert (info.id, info.name) == ("claude-opus-5-5", "Claude Opus 5.5")


def test_long_descriptions_are_cut_and_entries_without_an_id_are_skipped():
    info = model_info({"id": "m", "description": "word " * 1000})
    assert len(info.description) <= MAX_DESCRIPTION + 1 and info.description.endswith("…")
    assert model_info({"description": "no id"}) is None


def test_openrouter_capabilities_limits_and_cache_prices():
    info = model_info({
        "id": "openai/gpt-6.1-sol-pro", "created": 1790702886, "context_length": 1050000,
        "architecture": {"input_modalities": ["file", "image", "text"], "output_modalities": ["text"]},
        "pricing": {"prompt": "0.000002", "completion": "0.00001", "input_cache_read": "0.0000001", "input_cache_write": "0.0000025"},
        "top_provider": {"context_length": 1050000, "max_completion_tokens": 128000},
        "supported_parameters": ["include_reasoning", "max_tokens", "reasoning", "response_format", "tool_choice", "tools"],
    })
    assert info.input_modalities == ["file", "image", "text"] and info.output_modalities == ["text"]
    assert info.features == ["reasoning", "structured_output", "tools"], "several parameters of one capability count once"
    assert (info.max_output_tokens, info.cache_read_per_million, info.cache_write_per_million) == (128000, 0.1, 2.5)
    assert info.created == 1790702886


def test_edenai_capabilities_regions_and_cache_prices():
    info = model_info({
        "id": "deepinfra/anthropic/claude-sonnet-5-5", "owned_by": "deepinfra",
        "capabilities": {
            "input_modalities": ["text", "image"], "output_modalities": ["text"],
            "supports_reasoning": True, "supports_web_search": False, "supports_function_calling": True,
            "supports_prompt_caching": True, "supports_native_streaming": True,
        },
        "pricing": {"input_cost_per_token": 3e-6, "output_cost_per_token": 1.5e-5, "cache_read_input_token_cost": 3e-7, "cache_creation_input_token_cost": 3.75e-6},
        "regions": [{"code": "us", "name": "United States"}],
    })
    assert info.input_modalities == ["text", "image"]
    assert info.features == ["prompt_caching", "reasoning", "tools"], "only what is True, and only the capabilities worth naming"
    assert (info.cache_read_per_million, info.cache_write_per_million, info.regions) == (0.3, 3.75, ["United States"])

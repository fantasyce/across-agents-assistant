import pytest

from across_agents_assistant.credentials.store import KNOWN_PROVIDER_IDS
from across_agents_assistant.llm_gateway import config as gateway_config
from across_agents_assistant.llm_gateway.config import ModelInfo
from across_agents_assistant.llm_gateway.provider_registry import (
    get_default_provider_ids,
    get_provider_definition,
)
from across_agents_assistant.llm_gateway.openai_compatible_adapter import (
    parse_openai_models_payload,
)


def test_default_provider_registry_includes_major_openai_compatible_clouds():
    provider_ids = set(get_default_provider_ids())

    assert {
        "openai",
        "anthropic",
        "deepseek",
        "minimax",
        "bailian",
        "moonshot",
        "zhipu",
        "volcengine",
        "google",
        "xai",
        "mistral",
        "groq",
        "cohere",
        "openrouter",
        "together",
        "fireworks",
    }.issubset(provider_ids)
    assert set(KNOWN_PROVIDER_IDS) == provider_ids


def test_provider_registry_records_protocol_and_model_discovery_shape():
    anthropic = get_provider_definition("anthropic")
    deepseek = get_provider_definition("deepseek")
    google = get_provider_definition("google")
    openrouter = get_provider_definition("openrouter")

    assert anthropic is not None
    assert anthropic.provider_type == "anthropic"
    assert anthropic.models_endpoint.endswith("/v1/models")
    assert deepseek is not None
    assert deepseek.provider_type == "openai_compatible"
    assert deepseek.models_endpoint.endswith("/models")
    assert google is not None
    assert google.provider_type == "openai_compatible"
    assert "/openai" in google.endpoint
    assert openrouter is not None
    assert openrouter.provider_type == "openai_compatible"
    assert openrouter.models_endpoint.endswith("/models")


def test_default_provider_registry_uses_current_curated_fallback_models():
    assert get_provider_definition("openai").default_models[0].model_id == "gpt-5.5"
    assert get_provider_definition("deepseek").default_models[0].model_id == "deepseek-v4-pro"
    assert get_provider_definition("minimax").default_models[0].model_id == "MiniMax-M3"
    assert get_provider_definition("zhipu").default_models[0].model_id == "glm-5.1"
    assert get_provider_definition("google").default_models[0].model_id == "gemini-3.1-pro"
    assert get_provider_definition("openrouter").default_models[0].model_id == "openrouter/auto"


def test_parse_openai_models_payload_keeps_available_model_ids():
    parsed = parse_openai_models_payload(
        {
            "data": [
                {"id": "deepseek-chat", "owned_by": "deepseek"},
                {"id": "MiniMax-M2.7", "object": "model"},
                {"id": "", "object": "model"},
                {"object": "not-a-model"},
            ]
        }
    )

    assert parsed == [
        ModelInfo(model_id="deepseek-chat", name="deepseek-chat"),
        ModelInfo(model_id="MiniMax-M2.7", name="MiniMax-M2.7"),
    ]


def test_parse_openai_models_payload_accepts_google_style_prefixed_models():
    parsed = parse_openai_models_payload({"data": [{"id": "models/gemini-2.5-pro"}]})

    assert parsed == [ModelInfo(model_id="gemini-2.5-pro", name="gemini-2.5-pro")]


def test_load_llm_config_merges_registry_updates_into_persisted_builtin_providers(tmp_path, monkeypatch):
    config_path = tmp_path / "llm_config.json"
    legacy_path = tmp_path / "legacy_llm_config.json"
    monkeypatch.setattr(gateway_config, "CONFIG_FILE", config_path)
    monkeypatch.setattr(gateway_config, "LEGACY_CONFIG_FILE", legacy_path)

    config_path.write_text(
        """
        {
          "providers": [
            {
              "provider_id": "deepseek",
              "name": "DeepSeek",
              "api_key_env": "DEEPSEEK_API_KEY",
              "endpoint": "https://api.deepseek.com/v1",
              "provider_type": "openai_compatible",
              "models_endpoint": "https://api.deepseek.com/v1/models",
              "models": [
                {
                  "model_id": "deepseek-chat",
                  "name": "DeepSeek Chat",
                  "supports_vision": false,
                  "supports_function_calling": true,
                  "max_tokens": 8192
                }
              ],
              "enabled": true
            }
          ],
          "primary_provider": "deepseek",
          "fallback_providers": []
        }
        """,
        encoding="utf-8",
    )

    loaded = gateway_config.load_llm_config()
    deepseek = next(provider for provider in loaded.providers if provider.provider_id == "deepseek")
    model_ids = [model.model_id for model in deepseek.models]

    assert model_ids[:2] == ["deepseek-v4-pro", "deepseek-v4-flash"]
    assert "deepseek-chat" in model_ids
    assert "openai" in {provider.provider_id for provider in loaded.providers}

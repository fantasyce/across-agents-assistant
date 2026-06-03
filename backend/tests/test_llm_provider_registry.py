import pytest

from across_agents_assistant.credentials.store import KNOWN_PROVIDER_IDS
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
    }.issubset(provider_ids)
    assert set(KNOWN_PROVIDER_IDS) == provider_ids


def test_provider_registry_records_protocol_and_model_discovery_shape():
    anthropic = get_provider_definition("anthropic")
    deepseek = get_provider_definition("deepseek")
    google = get_provider_definition("google")

    assert anthropic is not None
    assert anthropic.provider_type == "anthropic"
    assert anthropic.models_endpoint.endswith("/v1/models")
    assert deepseek is not None
    assert deepseek.provider_type == "openai_compatible"
    assert deepseek.models_endpoint.endswith("/models")
    assert google is not None
    assert google.provider_type == "openai_compatible"
    assert "/openai" in google.endpoint


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

import pytest

from across_agents_assistant.agent_manager import _is_minimax_io_endpoint
from across_agents_assistant.llm_client import OrchestratorClient
from across_agents_assistant.persistence.service import _normalize_local_path


def test_minimax_host_detection_uses_hostname_boundaries():
    assert OrchestratorClient._is_minimax_endpoint("https://api.minimaxi.com/v1")
    assert OrchestratorClient._is_minimax_endpoint("https://gateway.minimax.io/v1")
    assert not OrchestratorClient._is_minimax_endpoint("https://api.minimax.io.evil.example/v1")
    assert not OrchestratorClient._is_minimax_endpoint("https://evil-minimaxi.com/v1")


def test_legacy_minimax_io_detection_uses_hostname_boundaries():
    assert _is_minimax_io_endpoint("https://api.minimax.io/anthropic")
    assert not _is_minimax_io_endpoint("https://api.minimax.io.evil.example/anthropic")


def test_normalize_local_path_rejects_control_characters():
    with pytest.raises(ValueError, match="Invalid local path"):
        _normalize_local_path("/tmp/project\nother")
    with pytest.raises(ValueError, match="Invalid local path"):
        _normalize_local_path("/tmp/project\x00other")


def test_orchestrator_client_uses_provider_registry_api_key_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test-key")

    assert OrchestratorClient._registry_api_key("agnes") == "agnes-test-key"
    assert OrchestratorClient._registry_api_key("unknown") == ""


@pytest.mark.asyncio
async def test_orchestrator_client_preserves_existing_system_context(monkeypatch):
    class FakeManager:
        def get_agent_config(self, agent_id):
            return {
                "type": "openai_compatible",
                "model": "demo-model",
                "api_key": "test-key",
                "base_url": "https://example.test/v1",
            }

    captured = {}

    async def fake_chat_openai(self, config, model, messages, tools):
        captured["messages"] = messages
        return type("Response", (), {"text": "ok", "tool_calls": []})()

    monkeypatch.setattr(OrchestratorClient, "_chat_openai", fake_chat_openai)

    client = OrchestratorClient(FakeManager())
    await client.chat(
        "deepseek",
        [
            {
                "role": "system",
                "content": "Current project directory: /tmp/across-ui-project",
            },
            {"role": "user", "content": "remember project context"},
        ],
        [],
    )

    system_message = captured["messages"][0]["content"]
    assert "You are a helpful AI assistant running in a macOS desktop environment" in system_message
    assert "Current project directory: /tmp/across-ui-project" in system_message

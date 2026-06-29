from fastapi.testclient import TestClient

from across_agents_assistant import local_agent_protocols
from across_agents_assistant.api_server import app


def test_local_agent_protocol_contract_exposes_optional_native_bridges(monkeypatch):
    def fake_resolve(agent_id):
        return {
            "kimi": "/opt/across-test/bin/kimi",
            "claude": "/opt/across-test/bin/claude",
        }.get(agent_id)

    monkeypatch.setattr(local_agent_protocols, "resolve_local_agent_executable", fake_resolve)
    monkeypatch.setattr(local_agent_protocols.shutil, "which", lambda name: "/opt/across-test/bin/qwen" if name == "qwen" else None)
    monkeypatch.setattr(local_agent_protocols, "_is_executable", lambda path: path.startswith("/opt/across-test/bin/"))

    payload = local_agent_protocols.render_local_agent_protocol_contract()

    assert payload["schema_version"] == "across-local-agent-protocols/1.0"
    assert payload["status"] == "passed"
    assert payload["kimi_code"]["acp"] == "optional"
    assert payload["kimi_code"]["command"]["executable"] == "/opt/across-test/bin/kimi"
    assert payload["kimi_code"]["command"]["args"] == ["acp"]
    assert payload["qwen_code"]["daemon"] == "optional"
    assert payload["qwen_code"]["command"]["executable"] == "/opt/across-test/bin/qwen"
    assert payload["qwen_code"]["status_command"]["args"] == ["daemon", "status"]
    assert payload["claude_code"]["checkpoint_bridge"] == "optional"
    assert payload["claude_code"]["rewind"]["approval_required"] is True
    assert payload["claude_code"]["replay"]["raw_transcripts_included"] is False
    assert payload["boundaries"]["product_paths_required"] == "~/.across"
    assert payload["boundaries"]["host_owns_credentials"] is True
    assert payload["boundaries"]["raw_secrets_included"] is False
    assert payload["boundaries"]["implementation_imports"] is False


def test_local_agent_protocol_api_returns_non_secret_contract(monkeypatch):
    monkeypatch.setattr(local_agent_protocols, "resolve_local_agent_executable", lambda agent_id: None)
    monkeypatch.setattr(local_agent_protocols.shutil, "which", lambda name: None)
    monkeypatch.setattr(local_agent_protocols, "_is_executable", lambda path: False)

    response = TestClient(app).get("/api/agents/protocols")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "across-local-agent-protocols/1.0"
    assert payload["kimi_code"]["command"]["requires_user_configuration"] is True
    assert payload["qwen_code"]["command"]["requires_user_configuration"] is True
    assert payload["claude_code"]["rewind"]["mode"] == "host_approved"
    assert payload["boundaries"]["raw_transcripts_included"] is False

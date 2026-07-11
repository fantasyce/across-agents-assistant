import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault(
    "ACROSS_AGENTS_DB_PATH",
    os.path.join(tempfile.mkdtemp(), "test_agent_workspace_readiness.db"),
)

from across_agents_assistant import agent_workspace_readiness as readiness
from across_agents_assistant.agent_capabilities import AgentCapabilityStore
from across_agents_assistant.api_server import app


def _fake_health():
    return {
        "openclaw": {
            "display_name": "OpenClaw",
            "found": True,
            "available": True,
            "status": "available",
            "executable": "openclaw",
            "path": "/private/bin/openclaw",
            "configured_path": "/private/bin/openclaw",
            "candidate_paths": ["/private/bin/openclaw"],
            "version": "openclaw 1.2.3",
        },
        "hermes": {
            "display_name": "Hermes",
            "found": True,
            "available": False,
            "status": "unavailable",
            "executable": "hermes",
            "error": "configured path is not executable: /secret/hermes",
        },
    }


def _store_with_secret_profile(tmp_path: Path) -> AgentCapabilityStore:
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile(
        "openclaw",
        {
            "enabled_skill_ids": ["general_execution"],
            "enabled_plugin_ids": ["across_context"],
            "enabled_tool_names": ["read_file"],
            "custom_instructions": "secret token sk-test-hidden",
            "strict_tool_scope": True,
        },
    )
    return store


def test_build_agent_workspace_readiness_is_readonly_and_non_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ACROSS_HOME", raising=False)
    store = _store_with_secret_profile(tmp_path)
    calls = []

    def fake_detect_local_agents(*, force=False):
        calls.append(force)
        return _fake_health()

    monkeypatch.setattr(readiness, "detect_local_agents", fake_detect_local_agents)
    monkeypatch.setattr(readiness, "get_agent_capability_store", lambda: store)

    payload = readiness.build_agent_workspace_readiness(refresh=True)

    workspace_root = Path(payload["workspace"]["root"])
    assert workspace_root == tmp_path / ".across/data/across-agents-assistant/agent-workspaces"
    assert workspace_root.exists() is False
    assert payload["workspace"]["under_across_home"] is True
    assert payload["workspace"]["creation_enabled"] is True
    assert payload["mutation_enabled"] is True
    assert payload["readonly"] is True
    assert payload["schema_version"] == "agent-workspace-readiness/1.0"
    assert payload["status"] == "partial"
    assert payload["readiness"] == "limited"
    assert isinstance(payload["generated_at"], str)
    assert calls == [True]

    assert [agent["agent_id"] for agent in payload["available_local_agents"]] == ["openclaw"]
    assert [agent["agent_id"] for agent in payload["agents"] if agent["available"]] == ["openclaw"]
    openclaw = payload["available_local_agents"][0]
    assert openclaw["capabilities"] == [
        "general_execution",
        "General execution",
        "implementation",
        "local",
        "across_context",
        "read_file",
    ]
    assert "path" not in openclaw
    assert "configured_path" not in openclaw
    assert "candidate_paths" not in openclaw
    assert "executable" not in openclaw

    feature_ids = {feature["id"] for feature in payload["supported_features"]}
    assert {
        "readonly_readiness_snapshot",
        "local_agent_detection",
        "non_secret_agent_capabilities",
        "workspace_root_policy",
        "isolated_git_worktrees",
        "durable_review_lifecycle",
        "human_approved_promotion",
    }.issubset(feature_ids)
    assert all(route["enabled"] is True for route in payload["future_routes"])

    missing_ids = {item["id"] for item in payload["missing_prerequisites"]}
    assert "workspace_root_missing" in missing_ids
    assert "local_agent_hermes_unavailable" in missing_ids
    assert payload["missing_prerequisite_ids"] == sorted(missing_ids)
    assert payload["workspace_isolation"] == {
        "status": "ready",
        "mode": "detached_git_worktrees",
        "supports_git_worktree": True,
        "can_create_isolated_workspaces": True,
        "missing_prerequisites": [],
        "reason": None,
    }
    assert payload["routes"] == {
        "create": "/api/agent-workspaces",
        "events": "/api/agent-workspaces/{workspace_id}/events",
        "diff": "/api/agent-workspaces/{workspace_id}/comparison",
        "evidence": "/api/agent-workspaces/{workspace_id}/comparison",
        "cancel": "/api/agent-workspaces/{workspace_id}/cancel",
        "comment": "/api/agent-workspaces/{workspace_id}/comment",
        "line_review": "/api/agent-workspaces/{workspace_id}/line-reviews",
        "agent_status": "/api/agent-workspaces/agent-status",
        "select": "/api/agent-workspaces/{workspace_id}/select",
        "promote": "/api/agent-workspaces/{workspace_id}/promote",
    }
    assert payload["security"] == {
        "secrets_included": False,
        "custom_instructions_included": False,
        "install_paths_included": False,
        "credential_fields_redacted": True,
        "prompt_included": False,
        "transcripts_included": False,
    }
    assert payload["repository_access_contract"]["bookmark_data_accepted"] is False
    assert payload["repository_access_contract"]["swift_responsibilities"] == [
        "resolve_stale_bookmark",
        "start_accessing_before_request",
        "keep_access_active_for_workspace_lifecycle",
        "stop_accessing_after_terminal_cleanup",
    ]
    operational = openclaw["operational_status"]
    assert operational["account"]["status"] == "unknown"
    assert operational["auth"]["status"] == "unknown"
    assert operational["model"]["status"] == "unknown"
    assert operational["provider"]["status"] == "unknown"
    assert operational["usage"]["status"] == "unknown"
    assert operational["rate_limit"]["status"] == "unknown"
    assert operational["capability"]["status"] == "known"
    encoded = json.dumps(payload)
    assert "sk-test-hidden" not in encoded
    assert "/private/bin/openclaw" not in encoded
    assert "/secret/hermes" not in encoded


def test_agent_workspace_readiness_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ACROSS_HOME", raising=False)
    store = _store_with_secret_profile(tmp_path)

    monkeypatch.setattr(readiness, "detect_local_agents", lambda *, force=False: _fake_health())
    monkeypatch.setattr(readiness, "get_agent_capability_store", lambda: store)

    response = TestClient(app).get("/api/agent-workspaces/readiness?refresh=true")

    assert response.status_code == 200
    body = response.json()
    assert body["mutation_enabled"] is True
    assert body["schema_version"] == "agent-workspace-readiness/1.0"
    assert body["status"] == "partial"
    assert body["readiness"] == "limited"
    assert body["available_local_agents"][0]["agent_id"] == "openclaw"
    assert body["agents"][0]["agent_id"] == "openclaw"
    assert body["workspace"]["root"] == str(
        tmp_path / ".across/data/across-agents-assistant/agent-workspaces"
    )
    assert all(route["enabled"] is True for route in body["future_routes"])


def test_agent_operational_status_endpoint_is_explicit_and_redacted(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ACROSS_HOME", raising=False)
    store = _store_with_secret_profile(tmp_path)
    health = _fake_health()
    health["openclaw"].update(
        {
            "configured_model": "model-safe",
            "provider": "provider-safe",
            "account": {"id": "account-safe", "display_name": "Developer"},
            "auth": {"status": "authenticated", "authenticated": True, "method": "browser_login"},
            "usage": {"window": "day", "input_tokens": 12, "output_tokens": 3, "total_tokens": 15, "requests": 2},
            "rate_limit": {"status": "limited", "remaining": 8, "limit": 10, "reset_at": "2030-01-01T00:00:00Z", "retry_after_seconds": 2.5},
            "credential": "must-not-appear",
        }
    )
    hidden_account = "".join(("sk", "-", "hidden-account-12345"))
    health["hermes"]["account"] = {"id": hidden_account}
    health["hermes"]["provider"] = "Bearer hidden-provider-value"
    monkeypatch.setattr(readiness, "detect_local_agents", lambda *, force=False: health)
    monkeypatch.setattr(readiness, "get_agent_capability_store", lambda: store)

    response = TestClient(app).get("/api/agent-workspaces/agent-status?refresh=true")

    assert response.status_code == 200
    body = response.json()
    openclaw = next(item for item in body["agents"] if item["agent_id"] == "openclaw")
    assert openclaw["account"] == {"status": "known", "id": "account-safe", "display_name": "Developer"}
    assert openclaw["auth"]["authenticated"] is True
    assert openclaw["model"] == {"status": "configured", "id": "model-safe"}
    assert openclaw["provider"] == {"status": "known", "id": "provider-safe"}
    assert openclaw["usage"]["total_tokens"] == 15
    assert openclaw["rate_limit"]["remaining"] == 8
    encoded = json.dumps(body)
    assert "must-not-appear" not in encoded
    assert hidden_account not in encoded
    assert "hidden-provider-value" not in encoded

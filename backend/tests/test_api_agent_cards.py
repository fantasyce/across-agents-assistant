import json
import os
import tempfile

os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from fastapi.testclient import TestClient

from across_agents_assistant.agent_capabilities import AgentCapabilityStore
from across_agents_assistant.api_server import app


def test_agent_cards_endpoint_exports_a2a_like_public_cards(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile(
        "openclaw",
        {
            "enabled_skill_ids": ["general_execution", "macos_automation"],
            "enabled_tool_names": ["filesystem__write_file"],
            "custom_instructions": "secret token sk-test-hidden",
            "strict_tool_scope": True,
        },
    )

    class FakeNativeSkillManager:
        def list_all_agent_skills(self):
            return {
                "openclaw": {
                    "agent_id": "openclaw",
                    "skills": [
                        {
                            "id": "window-capture",
                            "name": "Window Capture",
                            "description": "Capture a selected macOS window.",
                            "status": "enabled",
                            "availability": "available",
                        }
                    ],
                }
            }

    monkeypatch.setattr(api_server, "get_agent_capability_store", lambda: store)
    monkeypatch.setattr(api_server, "get_native_skill_manager", lambda: FakeNativeSkillManager())
    monkeypatch.setattr(
        api_server,
        "_runtime_tool_schemas",
        lambda: [
            {
                "name": "filesystem__write_file",
                "description": "Write local files.",
                "risk_level": "high",
            }
        ],
    )

    response = TestClient(app).get("/api/agent-cards")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["protocol"] == "a2a-like"
    assert body["security"]["secrets_included"] is False
    openclaw = next(card for card in body["cards"] if card["agent_id"] == "openclaw")
    assert openclaw["name"] == "OpenClaw"
    assert openclaw["kind"] == "local"
    assert openclaw["capabilities"]["configured_skills"] == [
        "General execution",
        "macOS automation",
    ]
    assert openclaw["skills"][0]["id"] == "window-capture"
    assert openclaw["tools"]["risk_summary"]["high"] == 1
    assert openclaw["routing"]["strict_tool_scope"] is True
    encoded = json.dumps(body)
    assert "sk-test-hidden" not in encoded

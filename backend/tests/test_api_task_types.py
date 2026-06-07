import os

os.environ["ACROSS_AGENTS_DB_PATH"] = os.path.join(os.environ.get("TMPDIR", "/tmp"), "test_api_task_types.db")
os.makedirs(os.path.dirname(os.environ["ACROSS_AGENTS_DB_PATH"]), exist_ok=True)

from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app


def test_auto_task_requires_task_types(monkeypatch):
    monkeypatch.setattr("across_agents_assistant.api_server._check_llm_provider_readiness", lambda: [])
    client = TestClient(app)

    response = client.post("/api/tasks/auto", json={"description": "Build a todo tool"})

    assert response.status_code == 422


def test_auto_task_accepts_functional_and_artifact_types(monkeypatch):
    captured = {}

    class FakePlugin:
        def implementation_status(self, probe=True):
            return {
                "mode": "external",
                "implementation": "external",
                "available": True,
                "transport": "cli",
                "connection_note": "fake external runtime",
            }

        def submit_task(self, *, goal, project_dir, deliverables=None, agent=None):
            captured["goal"] = goal
            captured["project_dir"] = project_dir
            captured["deliverables"] = deliverables
            captured["agent"] = agent
            return {"task_id": "task-unit123", "status": "pending"}

    monkeypatch.setattr("across_agents_assistant.api_server._check_llm_provider_readiness", lambda: [])
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())

    client = TestClient(app)
    response = client.post(
        "/api/tasks/auto",
        json={
            "description": "Build a todo tool",
            "task_types": ["functional", "artifact"],
            "owner_agent": "claude",
        },
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == "task-unit123"
    assert captured["goal"] == "Build a todo tool"
    assert captured["deliverables"] == ["README.md"]
    assert captured["agent"] == "claude"

import os

os.environ["ACROSS_AGENTS_DB_PATH"] = os.path.join(os.environ.get("TMPDIR", "/tmp"), "test_api_task_types.db")
os.makedirs(os.path.dirname(os.environ["ACROSS_AGENTS_DB_PATH"]), exist_ok=True)

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app


def test_auto_task_requires_task_types(monkeypatch):
    monkeypatch.setattr("across_agents_assistant.api_server._check_llm_provider_readiness", lambda: [])
    client = TestClient(app)

    response = client.post("/api/tasks/auto", json={"description": "Build a todo tool"})

    assert response.status_code == 422


def test_auto_task_accepts_functional_and_artifact_types(monkeypatch):
    captured = {}

    class FakeOrchestrator:
        def submit_task(self, description, context):
            captured["description"] = description
            captured["context"] = context
            return "task-unit123"

    monkeypatch.setattr("across_agents_assistant.api_server._check_llm_provider_readiness", lambda: [])
    monkeypatch.setattr("across_agents_assistant.api_server.get_task_orchestrator", lambda: FakeOrchestrator())

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
    assert captured["context"]["task_types"] == ["functional", "artifact"]
    assert captured["context"]["delivery_mode"] == "composite"

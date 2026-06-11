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

        def submit_task(self, *, goal, project_dir, deliverables=None, agent=None, subtasks=None, strict_dependency=False, task_types=None):
            captured["goal"] = goal
            captured["project_dir"] = project_dir
            captured["deliverables"] = deliverables
            captured["agent"] = agent
            captured["subtasks"] = subtasks
            captured["strict_dependency"] = strict_dependency
            captured["task_types"] = task_types
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
    assert captured["subtasks"] == []
    assert captured["strict_dependency"] is True
    assert captured["task_types"] == ["functional", "artifact"]


def test_auto_task_external_extracts_serial_wave_plan(monkeypatch, tmp_path):
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

        def submit_task(self, *, goal, project_dir, deliverables=None, agent=None, subtasks=None, strict_dependency=False, task_types=None):
            captured["deliverables"] = deliverables
            captured["agent"] = agent
            captured["subtasks"] = subtasks
            captured["strict_dependency"] = strict_dependency
            captured["task_types"] = task_types
            return {"task_id": "task-serial", "status": "pending"}

    monkeypatch.setattr("across_agents_assistant.api_server._check_llm_provider_readiness", lambda: [])
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())

    response = TestClient(app).post(
        "/api/tasks/auto",
        json={
            "description": "\n".join([
                "Wave 1 Contract: create docs/contract.json and docs/architecture.md.",
                "Wave 2 API: create api/server.mjs, must read docs/contract.json from Wave 1.",
                "Wave 3 UI: 创建 web/index.html、web/styles.css、web/app.js，UI 必须展示 API 派生阶段。",
                "Wave 4 Evidence: 最终创建 README.md 和 evidence/summary.json，说明每个 wave 的依赖证据。",
                "Do not create package.json or node_modules.",
            ]),
            "task_types": ["functional"],
            "owner_agent": "auto",
            "allowed_subtask_agents": ["hermes", "deepseek"],
            "project_dir": str(tmp_path),
        },
    )

    assert response.status_code == 200
    assert captured["agent"] == "hermes"
    assert captured["strict_dependency"] is True
    assert captured["task_types"] == ["functional"]
    assert captured["deliverables"] == [
        "docs/contract.json",
        "docs/architecture.md",
        "api/server.mjs",
        "web/index.html",
        "web/styles.css",
        "web/app.js",
        "README.md",
        "evidence/summary.json",
    ]
    assert [item["path"] for item in captured["subtasks"]] == [
        "docs/contract.json",
        "docs/architecture.md",
        "api/server.mjs",
        "web/index.html",
        "web/styles.css",
        "web/app.js",
        "README.md",
        "evidence/summary.json",
    ]
    assert [item["wave"] for item in captured["subtasks"]] == [1, 1, 2, 3, 3, 3, 4, 4]
    assert captured["subtasks"][0]["agent"] == "hermes"
    assert captured["subtasks"][1]["agent"] == "deepseek"
    assert captured["subtasks"][2]["dependencies"] == ["wave-1-1", "wave-1-2"]
    assert captured["subtasks"][3]["dependencies"] == ["wave-2-1"]
    assert captured["subtasks"][6]["dependencies"] == ["wave-3-1", "wave-3-2", "wave-3-3"]

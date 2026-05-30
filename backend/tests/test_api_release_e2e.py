import os

os.environ["ACROSS_AGENTS_DB_PATH"] = os.path.join(
    os.environ.get("TMPDIR", "/tmp"),
    "test_api_release_e2e.db",
)
os.makedirs(os.path.dirname(os.environ["ACROSS_AGENTS_DB_PATH"]), exist_ok=True)

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app
from across_agents_assistant.task_manager.orchestration.release_e2e import (
    RELEASE_E2E_SCENARIO_ID,
)


def test_release_e2e_scenarios_endpoint_exposes_full_gate():
    response = TestClient(app).get("/api/release/e2e/scenarios")

    assert response.status_code == 200
    body = response.json()
    scenario = next(item for item in body["scenarios"] if item["id"] == RELEASE_E2E_SCENARIO_ID)
    assert scenario["complexity_score"] >= 90
    assert "browser_e2e" in scenario["required_quality_gates"]
    assert "api/server.mjs" in scenario["required_files"]


def test_release_e2e_task_endpoint_submits_frontend_runnable_complex_task(monkeypatch, tmp_path):
    captured = {}

    class FakeOrchestrator:
        def submit_task(self, description, context):
            captured["description"] = description
            captured["context"] = context
            return "task-release-e2e"

    monkeypatch.setattr(
        "across_agents_assistant.api_server._check_llm_provider_readiness",
        lambda: [],
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_task_orchestrator",
        lambda: FakeOrchestrator(),
    )

    response = TestClient(app).post(
        "/api/release/e2e/tasks",
        json={
            "scenario_id": RELEASE_E2E_SCENARIO_ID,
            "project_dir": str(tmp_path / "frontend-release-e2e"),
            "run_label": "api-unit",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "task-release-e2e"
    assert body["scenario_id"] == RELEASE_E2E_SCENARIO_ID
    assert body["required_files"] == [
        "README.md",
        "web/index.html",
        "web/styles.css",
        "web/app.js",
        "api/server.mjs",
        "cli/quality-check.mjs",
        "tests/e2e-smoke.mjs",
    ]
    assert captured["context"]["delivery_mode"] == "composite"
    assert captured["context"]["strict_dependency"] is True
    assert captured["context"]["enable_wave_gate"] is True
    assert "Node.js built-in http server" in captured["description"]
    assert "Do not create any other files" in captured["description"]

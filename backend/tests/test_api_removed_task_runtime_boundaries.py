from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app


def test_dispatch_route_rejects_removed_in_app_orchestration():
    client = TestClient(app)

    response = client.post("/api/tasks/task-legacy/dispatch", json={})

    assert response.status_code == 410
    detail = response.json()["detail"]
    assert "external Across Orchestrator plugin" in detail
    assert "/api/legacy/tasks" not in detail


def test_removed_dispatch_route_is_removed():
    client = TestClient(app)
    response = client.post("/api/legacy/tasks/task-legacy/dispatch", json={})

    assert response.status_code == 404


def test_restore_route_rejects_removed_in_app_orchestration():
    client = TestClient(app)

    response = client.post("/api/tasks/task-legacy/restore")

    assert response.status_code == 410
    detail = response.json()["detail"]
    assert "external Across Orchestrator plugin" in detail
    assert "/api/legacy/tasks" not in detail


def test_removed_restore_route_is_removed():
    client = TestClient(app)
    response = client.post("/api/legacy/tasks/task-legacy/restore")

    assert response.status_code == 404


def test_shadowed_resumable_tasks_alias_is_removed():
    client = TestClient(app)
    response = client.get("/api/tasks/resumable")

    assert response.status_code == 404

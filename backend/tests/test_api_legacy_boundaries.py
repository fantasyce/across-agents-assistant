from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app
from across_agents_assistant.task_manager.models import JobStatus, SubTask, Task
from across_agents_assistant.task_manager.state import TaskState


def test_generic_dispatch_route_rejects_legacy_runtime_operations():
    client = TestClient(app)

    response = client.post("/api/tasks/task-legacy/dispatch", json={})

    assert response.status_code == 410
    assert "/api/legacy/tasks/task-legacy/dispatch" in response.json()["detail"]


def test_legacy_dispatch_route_remains_available_for_internal_task_maintenance(monkeypatch):
    task = Task.new(description="Legacy maintenance task")
    subtask = SubTask(
        task_id=task.task_id,
        subtask_id="st-legacy",
        description="Repair legacy subtask",
        agent_id="demo",
    )
    task.subtasks.append(subtask)

    class DummyState:
        def get_task(self, task_id):
            return task if task_id == task.task_id else None

        def get_ready_subtasks(self, task_id):
            return [subtask] if task_id == task.task_id and subtask.status == JobStatus.PENDING else []

    class DummyDispatcher:
        def dispatch_subtask(self, item):
            item.status = JobStatus.DISPATCHED
            return SimpleNamespace(
                job_id="job-legacy",
                subtask_id=item.subtask_id,
                agent_id=item.agent_id,
                task_description=item.description,
                status=JobStatus.DISPATCHED,
                progress=0.0,
                logs=[],
                result=None,
                error=None,
            )

    monkeypatch.setattr(api_server, "_task_state", DummyState())
    monkeypatch.setattr(api_server, "get_task_dispatcher", lambda: DummyDispatcher())

    client = TestClient(app)
    response = client.post(f"/api/legacy/tasks/{task.task_id}/dispatch", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == task.task_id
    assert payload["dispatched_jobs"][0]["job_id"] == "job-legacy"


def test_generic_restore_route_rejects_legacy_runtime_operations():
    client = TestClient(app)

    response = client.post("/api/tasks/task-legacy/restore")

    assert response.status_code == 410
    assert "/api/legacy/tasks/task-legacy/restore" in response.json()["detail"]


def test_legacy_restore_route_remains_available_for_internal_task_maintenance(monkeypatch):
    state = TaskState()
    task = Task.new(description="Legacy persisted task")
    state._tasks[task.task_id] = task
    calls = {"resume": 0, "repair": 0}

    monkeypatch.setattr(state, "restore_task", lambda task_id: task_id == task.task_id)

    class DummyOrchestrator:
        def resume_task(self, restored):
            assert restored.task_id == task.task_id
            calls["resume"] += 1

        def repair_task_dispatch(self, task_id, reason):
            assert task_id == task.task_id
            assert reason == "api_legacy_restore"
            calls["repair"] += 1

    monkeypatch.setattr(api_server, "_task_state", state)
    monkeypatch.setattr(api_server, "get_task_orchestrator", lambda: DummyOrchestrator())

    client = TestClient(app)
    response = client.post(f"/api/legacy/tasks/{task.task_id}/restore")

    assert response.status_code == 200
    assert response.json()["task_id"] == task.task_id
    assert calls == {"resume": 1, "repair": 1}

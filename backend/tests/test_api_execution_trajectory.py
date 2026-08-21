from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from across_agents_assistant import api_server
from across_agents_assistant.api_server import app


def _event(event_id: str, sequence: int, event_type: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "sequence": sequence,
        "timestamp": float(sequence),
        "type": event_type,
        "task_id": "task-trajectory-api",
    }


def _orchestrator_receipt(**extra: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": "across-evidence-receipt/1.0",
        "verdict": "ready",
        **extra,
    }
    receipt["evidence_sha256"] = sha256(
        json.dumps(receipt, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return receipt


def _worker_receipt(**extra: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": "across-worker-evidence/1.0",
        "terminal_state": "completed",
        **extra,
    }
    receipt["receipt_hash"] = sha256(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return receipt


class FakeBridge:
    def __init__(self, result: dict[str, Any] | None = None):
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def read_only_status(self, task_id: str) -> dict[str, Any] | None:
        self.calls.append(("read_only_status", task_id))
        return deepcopy(self.result)

    def optional_status(self, _task_id: str) -> dict[str, Any] | None:
        raise AssertionError("trajectory API must not use side-effectful optional_status")

    def status(self, _task_id: str) -> dict[str, Any]:
        raise AssertionError("trajectory API must not use side-effectful status")


class FakePlugin:
    def __init__(self, evidence: dict[str, Any], fallback_events: list[dict[str, Any]] | None = None):
        self.evidence = evidence
        self.fallback_events = list(fallback_events or [])
        self.calls: list[tuple[str, str]] = []

    def get_evidence_bundle(self, task_id: str) -> dict[str, Any]:
        self.calls.append(("get_evidence_bundle", task_id))
        return deepcopy(self.evidence)

    def get_events(self, task_id: str) -> list[dict[str, Any]]:
        self.calls.append(("get_events", task_id))
        return deepcopy(self.fallback_events)

    def get_task(self, _task_id: str) -> dict[str, Any]:
        raise AssertionError("trajectory API must not warm the task index through get_task")

    def run_task(self, _task_id: str) -> dict[str, Any]:
        raise AssertionError("trajectory API must not run a task")

    def build_replay_plan(self, _payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("trajectory API must not build replay plans")

    def compare_run_snapshots(self, _payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("trajectory API must not compare runs")


def _install_external_fakes(monkeypatch, *, plugin: FakePlugin, bridge: FakeBridge) -> None:
    monkeypatch.setattr(api_server, "_is_external_orchestrator_task", lambda _task_id: True)
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: plugin)
    monkeypatch.setattr(api_server, "get_worker_task_bridge", lambda: bridge)


def test_external_trajectory_reads_one_bundle_and_never_falls_back_when_events_key_is_present(monkeypatch):
    events = [
        _event("event-3", 3, "task.completed"),
        _event("event-1", 1, "task.created"),
        _event("event-2", 2, "task.started"),
        _event("event-2", 2, "task.started"),
    ]
    evidence = {
        "task_id": "task-trajectory-api",
        "status": "completed",
        "events": events,
        "evidence_receipt": _orchestrator_receipt(private="private-receipt-marker"),
    }
    evidence_before = deepcopy(evidence)
    plugin = FakePlugin(evidence, fallback_events=[_event("must-not-read", 99, "task.failed")])
    bridge = FakeBridge()
    _install_external_fakes(monkeypatch, plugin=plugin, bridge=bridge)

    response = TestClient(app).get(
        "/api/tasks/task-trajectory-api/execution-trajectory",
        params={"offset": "0", "limit": "2"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "orchestrator_evidence"
    assert [item["event_id"] for item in body["items"]] == ["event-1", "event-2"]
    assert body["page"] == {
        "offset": 0,
        "limit": 2,
        "returned": 2,
        "total": 3,
        "next_offset": 2,
        "has_more": True,
    }
    assert body["audit"]["mutations_triggered"] is False
    assert bridge.calls == [("read_only_status", "task-trajectory-api")]
    assert plugin.calls == [("get_evidence_bundle", "task-trajectory-api")]
    assert evidence == evidence_before
    assert "private-receipt-marker" not in response.text


def test_external_trajectory_treats_present_empty_events_as_authoritative(monkeypatch):
    plugin = FakePlugin(
        {
            "task_id": "task-trajectory-api",
            "status": "completed",
            "events": [],
            "evidence_receipt": None,
        },
        fallback_events=[_event("must-not-read", 1, "task.failed")],
    )
    bridge = FakeBridge()
    _install_external_fakes(monkeypatch, plugin=plugin, bridge=bridge)

    response = TestClient(app).get("/api/tasks/task-trajectory-api/execution-trajectory")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert plugin.calls == [("get_evidence_bundle", "task-trajectory-api")]


def test_external_trajectory_uses_one_get_events_fallback_only_when_events_key_is_absent(monkeypatch):
    plugin = FakePlugin(
        {
            "task_id": "task-trajectory-api",
            "status": "completed",
            "evidence_receipt": _orchestrator_receipt(),
        },
        fallback_events=[_event("fallback-1", 1, "task.completed")],
    )
    bridge = FakeBridge()
    _install_external_fakes(monkeypatch, plugin=plugin, bridge=bridge)

    response = TestClient(app).get("/api/tasks/task-trajectory-api/execution-trajectory")

    assert response.status_code == 200
    assert [item["event_id"] for item in response.json()["items"]] == ["fallback-1"]
    assert plugin.calls == [
        ("get_evidence_bundle", "task-trajectory-api"),
        ("get_events", "task-trajectory-api"),
    ]


def test_malformed_present_events_fails_502_without_fallback(monkeypatch):
    plugin = FakePlugin(
        {
            "task_id": "task-trajectory-api",
            "status": "completed",
            "events": {"private": "private-container-marker"},
            "evidence_receipt": _orchestrator_receipt(),
        },
        fallback_events=[_event("must-not-read", 1, "task.completed")],
    )
    bridge = FakeBridge()
    _install_external_fakes(monkeypatch, plugin=plugin, bridge=bridge)

    response = TestClient(app).get("/api/tasks/task-trajectory-api/execution-trajectory")

    assert response.status_code == 502
    assert response.json() == {"detail": "execution trajectory evidence is invalid"}
    assert "private-container-marker" not in response.text
    assert plugin.calls == [("get_evidence_bundle", "task-trajectory-api")]


def test_worker_trajectory_uses_read_only_status_and_never_reads_orchestrator_evidence(monkeypatch):
    remote = {
        "task_id": "task-trajectory-api",
        "job_id": "job-1",
        "status": "completed",
        "events": [_event("worker-1", 1, "task.completed")],
        "evidence_receipt": _worker_receipt(summary="完成"),
    }
    bridge = FakeBridge(remote)
    plugin = FakePlugin({"private": "must-not-read"})
    _install_external_fakes(monkeypatch, plugin=plugin, bridge=bridge)

    response = TestClient(app).get("/api/tasks/task-trajectory-api/execution-trajectory")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "worker_projection"
    assert body["receipt"]["integrity_state"] == "hash_valid"
    assert [item["event_id"] for item in body["items"]] == ["worker-1"]
    assert bridge.calls == [("read_only_status", "task-trajectory-api")]
    assert plugin.calls == []


def test_local_trajectory_reads_observability_without_plugin_or_worker_calls(monkeypatch):
    bridge = FakeBridge()
    plugin = FakePlugin({"private": "must-not-read"})
    monkeypatch.setattr(api_server, "_is_external_orchestrator_task", lambda _task_id: False)
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: plugin)
    monkeypatch.setattr(api_server, "get_worker_task_bridge", lambda: bridge)
    monkeypatch.setattr(
        api_server,
        "_load_task_info_read_only",
        lambda task_id: {
            "task_id": task_id,
            "status": "completed",
            "observability": {
                "timeline": [
                    {
                        "kind": "task_created",
                        "status": "running",
                        "at": 1.0,
                        "summary": "private-local-marker",
                    }
                ]
            },
        },
    )

    response = TestClient(app).get("/api/tasks/task-local/execution-trajectory")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "local_task_observability"
    assert body["task_id"] == "task-local"
    assert body["items"][0]["event_id"] == "local-000001"
    assert "private-local-marker" not in response.text
    assert bridge.calls == []
    assert plugin.calls == []


@pytest.mark.parametrize(
    "params",
    [
        {"offset": "true"},
        {"offset": "1.0"},
        {"offset": "+1"},
        {"offset": "01"},
        {"offset": "-1"},
        {"limit": "0"},
        {"limit": "501"},
        {"limit": "1.5"},
        {"offset": "9" * 5000},
    ],
)
def test_invalid_pagination_uses_fixed_422_without_echoing_caller_value(monkeypatch, params):
    monkeypatch.setattr(api_server, "_is_external_orchestrator_task", lambda _task_id: False)
    monkeypatch.setattr(
        api_server,
        "_load_task_info_read_only",
        lambda task_id: {"task_id": task_id, "status": "completed", "observability": {"timeline": []}},
    )

    response = TestClient(app).get(
        "/api/tasks/task-local/execution-trajectory",
        params=params,
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid execution trajectory pagination"}
    assert next(iter(params.values())) not in response.text


@pytest.mark.parametrize(
    "observability",
    [
        [],
        {"timeline": ""},
    ],
)
def test_falsey_malformed_local_event_containers_are_not_treated_as_empty(monkeypatch, observability):
    monkeypatch.setattr(api_server, "_is_external_orchestrator_task", lambda _task_id: False)
    monkeypatch.setattr(
        api_server,
        "_load_task_info_read_only",
        lambda task_id: {"task_id": task_id, "status": "completed", "observability": observability},
    )

    response = TestClient(app).get("/api/tasks/task-local/execution-trajectory")

    assert response.status_code == 502
    assert response.json() == {"detail": "execution trajectory evidence is invalid"}


def test_route_counters_for_execution_and_plugin_lifecycle_stay_zero(monkeypatch):
    class MutationGuardPlugin(FakePlugin):
        mutation_names = {
            "run_task",
            "resume_task",
            "repair_task",
            "cancel_task",
            "build_replay_plan",
            "compare_run_snapshots",
            "approve_task",
            "install",
            "repair",
            "upgrade",
            "uninstall",
            "rollback",
        }

        def __init__(self, evidence: dict[str, Any]):
            super().__init__(evidence)
            self.mutation_calls: list[str] = []

        def __getattr__(self, name: str):
            if name not in self.mutation_names:
                raise AttributeError(name)

            def forbidden(*_args, **_kwargs):
                self.mutation_calls.append(name)
                return {}

            return forbidden

    plugin = MutationGuardPlugin(
        {
            "task_id": "task-trajectory-api",
            "status": "completed",
            "events": [_event("event-1", 1, "task.completed")],
            "evidence_receipt": _orchestrator_receipt(),
        }
    )
    bridge = FakeBridge()
    _install_external_fakes(monkeypatch, plugin=plugin, bridge=bridge)

    response = TestClient(app).get("/api/tasks/task-trajectory-api/execution-trajectory")

    assert response.status_code == 200
    assert plugin.mutation_calls == []


def test_private_source_exception_maps_to_fixed_unavailable_error(monkeypatch):
    class FailingPlugin(FakePlugin):
        def get_evidence_bundle(self, task_id: str) -> dict[str, Any]:
            raise RuntimeError("private-source-marker /Users/private/project")

    plugin = FailingPlugin({})
    bridge = FakeBridge()
    _install_external_fakes(monkeypatch, plugin=plugin, bridge=bridge)

    response = TestClient(app).get("/api/tasks/task-trajectory-api/execution-trajectory")

    assert response.status_code == 503
    assert response.json() == {"detail": "execution trajectory source is unavailable"}
    assert "private-source-marker" not in response.text
    assert "/Users/private/project" not in response.text


def test_internal_projection_exception_maps_to_fixed_error(monkeypatch):
    monkeypatch.setattr(api_server, "_is_external_orchestrator_task", lambda _task_id: False)
    monkeypatch.setattr(
        api_server,
        "_load_task_info_read_only",
        lambda task_id: {"task_id": task_id, "status": "completed", "observability": {"timeline": []}},
    )
    monkeypatch.setattr(
        api_server,
        "project_execution_trajectory",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("private-projector-marker")),
        raising=False,
    )

    response = TestClient(app).get("/api/tasks/task-local/execution-trajectory")

    assert response.status_code == 500
    assert response.json() == {"detail": "execution trajectory could not be prepared"}
    assert "private-projector-marker" not in response.text


def test_existing_task_not_found_contract_is_preserved(monkeypatch):
    monkeypatch.setattr(api_server, "_is_external_orchestrator_task", lambda _task_id: False)
    monkeypatch.setattr(
        api_server,
        "_load_task_info_read_only",
        lambda _task_id: (_ for _ in ()).throw(HTTPException(status_code=404, detail="Task missing-task not found")),
    )

    response = TestClient(app).get("/api/tasks/missing-task/execution-trajectory")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task missing-task not found"}

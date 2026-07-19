import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app


class _NoExternalTasks:
    def list_task_summaries(self):
        return []


def _interop_payload(status="not_run", *, failed_count=0, passed_count=0):
    return {
        "status": status,
        "summary": {
            "passed_count": passed_count,
            "failed_count": failed_count,
            "host_target_count": 5 if status == "passed" else 0,
            "mcp_server_count": 3 if status == "passed" else 0,
            "protocol_readiness_score": 70 if status == "passed" else None,
        },
        "checks": [],
    }


def _quality_row(task_id: str, *, score: int = 90, gate: str = "passed"):
    return {
        "task_id": task_id,
        "description": f"Release candidate task {task_id}",
        "status": "completed",
        "progress": 1.0,
        "completed_count": 3,
        "total_count": 3,
        "created_at": 1.0,
        "updated_at": 2.0,
        "project_dir": "/tmp/release-eval",
        "owner_agent": "hermes",
        "allowed_subtask_agents": ["deepseek", "openclaw"],
        "task_types": ["functional"],
        "delivery_mode": "functional",
        "last_owner_decision": {
            "delivery_quality": {
                "delivery_quality": gate,
                "probe_results": [
                    {"probe_type": "workspace_hygiene", "passed": True},
                    {"probe_type": "security_privacy", "passed": True},
                    {"probe_type": "static_web", "passed": True},
                    {"probe_type": "api_service", "passed": True},
                    {"probe_type": "cli_generic", "passed": True},
                    {"probe_type": "browser_e2e", "passed": True},
                ],
                "quality_report": {
                    "quality_gate": gate,
                    "final_quality_score": score,
                    "generated_quality_score": score - 10,
                    "remediation_count": 1 if score < 90 else 0,
                    "required_failed_count": 1 if gate == "failed" else 0,
                    "manual_required_count": 0,
                    "required_skipped_count": 0,
                },
            }
        },
    }


@pytest.mark.asyncio
async def test_release_evaluation_does_not_block_core_api_event_loop(monkeypatch):
    import across_agents_assistant.api_server as api_server

    class SlowExternalTasks:
        def list_task_summaries(self):
            time.sleep(0.15)
            return []

    class FakePersistence:
        def get_task_summaries(self, *, limit=50, offset=0):
            return ([], 0)

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: SlowExternalTasks())
    monkeypatch.setattr(api_server, "load_agent_interop_e2e_latest", lambda: _interop_payload())
    started_at = time.perf_counter()
    evaluation = asyncio.create_task(api_server._release_evaluation_payload())
    await asyncio.sleep(0.02)

    assert time.perf_counter() - started_at < 0.1
    assert not evaluation.done()
    assert (await evaluation)["evaluated_task_count"] == 0


def test_release_evaluation_endpoint_uses_lightweight_task_rows(monkeypatch):
    import across_agents_assistant.api_server as api_server

    class FakePersistence:
        def get_task_summaries(self, *, limit=50, offset=0):
            assert limit == 100
            assert offset == 0
            return ([
                _quality_row("task-a", score=91),
                _quality_row("task-b", score=88),
                _quality_row("task-c", score=94),
            ], 3)

        def get_full_task(self, _task_id):
            raise AssertionError("release evaluation must not hydrate full task details")

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: _NoExternalTasks())
    monkeypatch.setattr(api_server, "load_agent_interop_e2e_latest", lambda: _interop_payload())

    response = TestClient(app).get("/api/release/evaluation")

    assert response.status_code == 200
    body = response.json()
    assert body["release_readiness"] == "ready"
    assert body["evaluated_task_count"] == 3
    assert body["pass_rate"] == 1.0
    assert body["recent_evaluations"][0]["task_id"] == "task-a"


def test_release_evaluation_endpoint_clamps_limit_and_reports_blockers(monkeypatch):
    import across_agents_assistant.api_server as api_server

    class FakePersistence:
        def get_task_summaries(self, *, limit=50, offset=0):
            assert limit == 500
            assert offset == 0
            return ([
                _quality_row("task-good", score=90),
                _quality_row("task-failed", score=45, gate="failed"),
            ], 2)

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: _NoExternalTasks())
    monkeypatch.setattr(api_server, "load_agent_interop_e2e_latest", lambda: _interop_payload("passed", passed_count=28))

    response = TestClient(app).get("/api/release/evaluation?limit=9999")

    assert response.status_code == 200
    body = response.json()
    assert body["release_readiness"] == "blocked"
    assert body["blocked_task_count"] == 1
    assert body["top_risks"][0]["kind"] == "required_gate_failure"
    assert body["release_evidence_count"] == 3


def test_release_evaluation_endpoint_uses_interop_e2e_when_task_quality_is_empty(monkeypatch):
    import across_agents_assistant.api_server as api_server

    class FakePersistence:
        def get_task_summaries(self, *, limit=50, offset=0):
            return ([], 0)

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: _NoExternalTasks())
    monkeypatch.setattr(api_server, "load_agent_interop_e2e_latest", lambda: _interop_payload("passed", passed_count=28))

    response = TestClient(app).get("/api/release/evaluation")

    assert response.status_code == 200
    body = response.json()
    assert body["release_readiness"] == "attention"
    assert body["evaluated_task_count"] == 0
    assert body["release_evidence_count"] == 1
    assert body["passed_evidence_count"] == 1
    assert body["supplemental_evidence"][0]["id"] == "agent_interop_e2e"
    assert body["supplemental_evidence"][0]["kind"] == "host_interop_e2e"
    assert body["supplemental_evidence"][0]["quality_gate"] == "passed"
    assert "quality-gated release task evidence" in body["recommendation"]


def test_release_evaluation_endpoint_hydrates_latest_release_e2e_read_only(monkeypatch):
    import across_agents_assistant.api_server as api_server

    summary_row = {
        "task_id": "task-release-e2e",
        "description": "Run host-agent full delivery conformance. Scenario ID: cross_agent_full_delivery_v1.",
        "status": "completed",
        "created_at": 1.0,
        "updated_at": 4.0,
    }
    full_payload = _quality_row("task-release-e2e", score=92)
    full_payload["description"] = summary_row["description"]
    full_payload["task_types"] = ["functional", "artifact"]
    full_payload["delivery_mode"] = "composite"

    class FakePersistence:
        def get_task_summaries(self, *, limit=50, offset=0):
            return ([summary_row], 1)

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    loaded_task_ids = []

    def load_read_only(task_id):
        loaded_task_ids.append(task_id)
        return full_payload

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: _NoExternalTasks())
    monkeypatch.setattr(api_server, "load_agent_interop_e2e_latest", lambda: _interop_payload("passed", passed_count=28))
    monkeypatch.setattr(api_server, "_load_task_info_read_only", load_read_only)

    response = TestClient(app).get("/api/release/evaluation")

    assert response.status_code == 200
    body = response.json()
    assert loaded_task_ids == ["task-release-e2e"]
    assert body["evaluated_task_count"] == 1
    assert body["passed_task_count"] == 1
    assert body["release_evidence_count"] == 2
    assert body["passed_evidence_count"] == 2
    assert body["recent_evaluations"][0]["task_id"] == "task-release-e2e"

import json
import os
import tempfile

os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from fastapi.testclient import TestClient

from across_agents_assistant import api_server
from across_agents_assistant.api_server import app


def _task_info(task_id: str) -> api_server.TaskInfo:
    return api_server.TaskInfo(
        task_id=task_id,
        description="Build a complex release dashboard with route evidence.",
        status="completed",
        task_types=["functional", "artifact"],
        delivery_mode="composite",
        owner_agent="hermes",
        allowed_subtask_agents=["openclaw", "deepseek"],
        project_dir="/tmp/across-evidence",
        subtasks=[],
        progress=1.0,
        created_at=10.0,
        updated_at=20.0,
        owner_delivery_contract={
            "contract_id": "contract-release",
            "deliverables": [{"path_hint": "web/index.html", "required": True}],
        },
        requirement_manifest={
            "requirements": [{"id": "req-web", "description": "Web UI", "required": True}],
        },
        last_owner_decision={
            "provider_api_key": "placeholder-key-should-not-leak",
            "delivery_quality": {
                "delivery_quality": "passed",
                "produced_required": [{"path_hint": "web/index.html"}],
                "probe_results": [
                    {"probe_type": "static_web_smoke", "passed": True, "required": True},
                    {"probe_type": "browser_e2e", "passed": True, "required": True},
                ],
                "quality_report": {
                    "quality_gate": "passed",
                    "final_quality_score": 88,
                    "required_failed_count": 0,
                    "manual_required_count": 0,
                    "required_skipped_count": 0,
                    "gate_results": [
                        {"adapter_id": "workspace_hygiene", "status": "passed", "required": True}
                    ],
                },
            },
        },
        quality_health={
            "quality_gate": "passed",
            "delivery_quality": "passed",
            "delivery_quality_report": {
                "produced_required": [{"path_hint": "web/index.html"}],
                "probe_results": [
                    {"probe_type": "static_web_smoke", "passed": True, "required": True},
                    {"probe_type": "browser_e2e", "passed": True, "required": True},
                ],
                "quality_report": {
                    "quality_gate": "passed",
                    "final_quality_score": 88,
                    "required_failed_count": 0,
                    "manual_required_count": 0,
                    "required_skipped_count": 0,
                },
            },
        },
        delivery_report={
            "quality_gate": "passed",
            "final_status": "completed",
            "remediation": {"subtask_count": 1, "active_subtasks": []},
        },
        observability={
            "agent_mix": {
                "actual_agents": ["hermes", "openclaw", "deepseek"],
                "local_agents": ["hermes", "openclaw"],
                "cloud_agents": ["deepseek"],
            }
        },
    )


def test_task_evidence_bundle_endpoint_is_read_only_and_sanitized(monkeypatch):
    class FakeState:
        _persistence = None

        def get_task(self, task_id):
            return object()

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_task_to_info", lambda _task, _state: _task_info("task-evidence"))
    monkeypatch.setattr(
        api_server,
        "_repair_task_dispatch_if_possible",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not repair from evidence API")),
    )

    response = TestClient(app).get(
        "/api/tasks/task-evidence/evidence-bundle",
        params={
            "expected_files": "web/index.html",
            "required_probes": "static_web_smoke,browser_e2e",
            "min_quality_score": "80",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["task_id"] == "task-evidence"
    assert body["audit"]["read_only"] is True
    assert body["delivery_contract"]["contract_id"] == "contract-release"
    assert body["requirement_manifest"]["requirements"][0]["id"] == "req-web"
    assert body["benchmark"]["status"] == "passed"
    assert body["benchmark"]["scenarios"][0]["checks"]["browser_e2e_passed"] is True
    encoded = json.dumps(body)
    assert "placeholder-key-should-not-leak" not in encoded
    assert body["last_owner_decision"]["provider_api_key"] == "[redacted]"


def test_external_evidence_bundle_uses_unlocked_task_snapshot(monkeypatch):
    class FakeExternalPlugin:
        def is_external_task(self, task_id):
            assert task_id == "task-external-snapshot"
            return True

        def get_task(self, _task_id):
            raise AssertionError("evidence reads must not wait on the runtime operation lock")

        def get_task_snapshot(self, task_id):
            return {
                "task_id": task_id,
                "goal": "Inspect completed external evidence",
                "status": "completed",
            }

        def get_evidence_snapshot(self, task_id):
            return {"task_id": task_id, "status": "completed"}

    async def project_task(_payload):
        return {"remote_execution": False}

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeExternalPlugin())
    monkeypatch.setattr(api_server, "_external_task_info_with_worker", project_task)
    monkeypatch.setattr(
        api_server,
        "external_evidence_to_app_bundle",
        lambda evidence, **_kwargs: {"task_id": evidence["task_id"], "snapshot": True},
    )

    response = TestClient(app).get("/api/tasks/task-external-snapshot/evidence-bundle")

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-external-snapshot", "snapshot": True}

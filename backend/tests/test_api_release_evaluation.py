from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app


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

    response = TestClient(app).get("/api/release/evaluation?limit=9999")

    assert response.status_code == 200
    body = response.json()
    assert body["release_readiness"] == "blocked"
    assert body["blocked_task_count"] == 1
    assert body["top_risks"][0]["kind"] == "required_gate_failure"

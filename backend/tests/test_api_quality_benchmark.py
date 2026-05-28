import os
import tempfile

os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from fastapi.testclient import TestClient

from across_agents_assistant import api_server
from across_agents_assistant.api_server import app


def test_task_quality_benchmark_endpoint_evaluates_current_task(monkeypatch):
    async def fake_get_task_status(task_id):
        return {
            "task_id": task_id,
            "status": "completed",
            "quality_health": {
                "quality_gate": "passed",
                "delivery_quality_report": {
                    "produced_required": ["index.html", "styles.css", "app.js", "README.md"],
                    "probe_results": [
                        {"probe_type": "static_web_smoke", "passed": True, "required": True},
                        {"probe_type": "browser_e2e", "passed": True, "required": True},
                    ],
                    "quality_report": {
                        "quality_gate": "passed",
                        "final_quality_score": 75,
                        "required_failed_count": 0,
                        "manual_required_count": 0,
                        "required_skipped_count": 0,
                    },
                },
            },
            "delivery_report": {
                "quality_gate": "passed",
                "final_status": "completed",
                "remediation": {"attempts_by_requirement": {}, "active_subtasks": []},
            },
        }

    monkeypatch.setattr(api_server, "get_task_status", fake_get_task_status)

    response = TestClient(app).get(
        "/api/tasks/task-good/quality-benchmark",
        params={
            "expected_files": "index.html,styles.css,app.js,README.md",
            "required_probes": "static_web_smoke,browser_e2e",
            "min_quality_score": "70",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["scenarios"][0]["task_id"] == "task-good"
    assert body["scenarios"][0]["checks"]["browser_e2e_passed"] is True

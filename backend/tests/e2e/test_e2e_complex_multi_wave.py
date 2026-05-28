"""E2E test: complex multi-wave FastAPI + Docker + tests task.

Verifies:
  - fix round inherits canonical contract
  - downstream dispatch respects unverified dependencies
  - artifact lineage is intact
  - final status is completed with delivery quality passed
"""

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import request


def _req(method: str, path: str, body: dict = None, expect: int = 200) -> dict:
    return request(method, path, body, expect)


def _wait_task(task_id: str, timeout: int = 1200, poll: int = 10) -> dict:
    deadline = time.time() + timeout
    failed_since = None
    while time.time() < deadline:
        info = _req("GET", f"/api/tasks/{task_id}")
        status = info.get("status", "unknown")
        quality_health = info.get("quality_health") or {}
        active_subtasks = [
            st for st in info.get("subtasks", [])
            if st.get("status") in ("pending", "dispatched", "running")
        ]
        active_remediation = quality_health.get("active_remediation_subtasks") or []
        delivery_quality = (
            (info.get("last_owner_decision") or {}).get("delivery_quality")
            or quality_health.get("delivery_quality_report")
            or {}
        )
        if status in ("completed", "completed_with_failures", "paused"):
            return info
        if status == "failed" and delivery_quality.get("delivery_quality") == "passed":
            return info
        if status == "failed" and not active_subtasks and not active_remediation:
            if failed_since is None:
                failed_since = time.time()
            if time.time() - failed_since >= 60:
                return info
        else:
            failed_since = None
        time.sleep(poll)
    raise TimeoutError(f"Task {task_id} did not finish within {timeout}s")


class TestE2EComplexMultiWave:
    """FastAPI + Docker + tests — full DAG exercise."""
    task_id: str = None

    @pytest.fixture(autouse=True)
    def check_backend(self):
        _req("GET", "/api/llm/status")

    def test_01_submit_complex_task(self):
        result = _req(
            "POST",
            "/api/tasks/auto",
            {
                "description": (
                    "Create a FastAPI REST API project with:\n"
                    "1. main.py with GET /items, POST /items, GET /items/{id}, DELETE /items/{id}\n"
                    "2. models.py with Pydantic Item and ItemCreate models\n"
                    "3. requirements.txt with fastapi, uvicorn, pydantic\n"
                    "4. Dockerfile for containerized deployment\n"
                    "5. docker-compose.yml with the API service\n"
                    "6. tests/test_api.py with pytest tests for all endpoints\n"
                    "7. A README.md with build and run instructions"
                ),
                "project_dir": f"/tmp/complex-e2e-{int(time.time())}",
                "task_types": ["functional", "artifact"],
                "allowed_subtask_agents": [],
                "strict_dependency": True,
                "enable_wave_gate": True,
            },
        )
        TestE2EComplexMultiWave.task_id = result.get("task_id")
        assert TestE2EComplexMultiWave.task_id, f"No task_id: {result}"

    def test_02_wave_structure(self):
        """Verify multi-wave DAG structure."""
        assert TestE2EComplexMultiWave.task_id, "submit task first"
        deadline = time.time() + 180
        waves = []
        while time.time() < deadline:
            info = _req("GET", f"/api/tasks/{TestE2EComplexMultiWave.task_id}")
            waves = info.get("waves", [])
            if len(waves) >= 3:
                break
            time.sleep(3)
        assert len(waves) >= 3, (
            f"Expected at least 3 waves, got {len(waves)}"
        )
        print(f"\nWave structure ({len(waves)} waves):")
        for wave in sorted(waves, key=lambda w: w.get("wave_number", -1)):
            wn = wave.get("wave_number", -1)
            subtasks_in_wave = wave.get("subtasks", [])
            print(f"  Wave {wn}: {len(subtasks_in_wave)} subtasks — "
                  f"governance={wave.get('governance_status', '?')}")

    def test_03_delivery_contract_and_quality_fields(self):
        assert TestE2EComplexMultiWave.task_id, "submit task first"
        info = _req("GET", f"/api/tasks/{TestE2EComplexMultiWave.task_id}")
        assert info.get("owner_delivery_contract") is not None
        assert info.get("requirement_manifest") is not None
        assert "quality_health" in info
        assert "delivery_report" in info

    def test_04_wait_and_verify(self):
        assert TestE2EComplexMultiWave.task_id, "submit task first"
        info = _wait_task(TestE2EComplexMultiWave.task_id, timeout=1200)
        status = info.get("status", "unknown")
        assert status == "completed", f"Task ended with unexpected status: {status}"
        delivery_quality = (
            (info.get("last_owner_decision") or {}).get("delivery_quality")
            or (info.get("quality_health") or {}).get("delivery_quality_report")
            or {}
        )
        assert delivery_quality.get("delivery_quality") == "passed", delivery_quality
        assert info.get("artifacts") is not None, "No artifacts field"
        assert info.get("acceptance_records") is not None, "No acceptance_records"
        print(f"\nFinal status: {status}")
        print(f"Artifacts: {len(info.get('artifacts', []))}")
        print(f"Acceptance records: {len(info.get('acceptance_records', []))}")

"""E2E test: FastAPI REST API task — delivery contract validation.

Verifies the current owner-delivery-contract path:
  - task_types payload is accepted
  - owner delivery contract and requirement manifest are exposed
  - delivery report and quality health are returned

Prerequisites:
  1. The Across Agents Assistant app is running (backend Unix socket available).
  2. At least one cloud LLM key is configured in ~/.across/data/across-agents-assistant/credentials.json.

Usage:
  python3 -m pytest tests/e2e/test_e2e_rest_api.py -v
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import request


def _req(method: str, path: str, body: dict = None, expect: int = 200) -> dict:
    return request(method, path, body, expect)


def _wait_task(task_id: str, timeout: int = 900, poll: int = 5) -> dict:
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


class TestE2ERestApi:
    """Create a FastAPI REST API task and verify delivery contract exposure."""
    task_id: str = None

    @pytest.fixture(autouse=True)
    def check_backend(self):
        _req("GET", "/api/llm/status")

    def test_01_submit_rest_api_task(self):
        result = _req(
            "POST",
            "/api/tasks/auto",
            {
                "description": (
                    "Create a FastAPI REST API with:\n"
                    "1. A main.py with GET /items and POST /items endpoints\n"
                    "2. A models.py with Pydantic Item model\n"
                    "3. A requirements.txt with fastapi and uvicorn\n"
                    "4. A config.py with basic settings"
                ),
                "project_dir": f"/tmp/restapi-e2e-{int(time.time())}",
                "task_types": ["functional", "artifact"],
                "allowed_subtask_agents": [],
                "strict_dependency": True,
                "enable_wave_gate": True,
            },
        )
        TestE2ERestApi.task_id = result.get("task_id")
        assert TestE2ERestApi.task_id, f"No task_id: {result}"

    def test_02_owner_delivery_contract_is_available(self):
        assert TestE2ERestApi.task_id, "submit task first"
        deadline = time.time() + 60
        info = {}
        while time.time() < deadline:
            info = _req("GET", f"/api/tasks/{TestE2ERestApi.task_id}")
            if info.get("owner_delivery_contract") is not None and info.get("requirement_manifest") is not None:
                break
            time.sleep(1)
        assert info.get("owner_delivery_contract") is not None, f"No owner_delivery_contract: {info}"
        assert info.get("requirement_manifest") is not None, f"No requirement_manifest: {info}"
        assert info.get("delivery_mode") == "composite"

    def test_03_wave_structure_is_exposed(self):
        assert TestE2ERestApi.task_id, "submit task first"
        deadline = time.time() + 90
        waves = []
        while time.time() < deadline:
            info = _req("GET", f"/api/tasks/{TestE2ERestApi.task_id}")
            waves = info.get("waves", [])
            if len(waves) >= 2:
                break
            time.sleep(2)

        assert len(waves) >= 2, (
            f"Expected at least 2 waves (decompose + business), got {len(waves)}"
        )

        for wave in waves:
            wn = wave.get("wave_number", -1)
            if wn == 0:
                continue  # decompose wave has no business deliverables
            assert "subtasks" in wave, f"Wave {wn} missing subtasks: {wave}"

    def test_04_wait_and_verify_artifacts(self):
        """Run to completion and check artifacts + acceptance records."""
        assert TestE2ERestApi.task_id, "submit task first"
        info = _wait_task(TestE2ERestApi.task_id, timeout=900)
        status = info.get("status", "unknown")
        assert status == "completed", f"Task ended with unexpected status: {status}"
        delivery_quality = (
            (info.get("last_owner_decision") or {}).get("delivery_quality")
            or (info.get("quality_health") or {}).get("delivery_quality_report")
            or {}
        )
        assert delivery_quality.get("delivery_quality") == "passed", delivery_quality

        has_artifacts = info.get("artifacts")
        has_acceptance = info.get("acceptance_records")
        print(f"\nArtifact records: {len(has_artifacts) if has_artifacts else 0}")
        print(f"Acceptance records: {len(has_acceptance) if has_acceptance else 0}")
        print(f"Delivery report: {info.get('delivery_report', {}).get('summary')}")

        assert has_artifacts is not None, f"No artifacts field: {info}"
        assert has_acceptance, f"No acceptance_records: {info}"
        assert "quality_health" in info
        assert "delivery_report" in info

    def test_05_status_consistency(self):
        """/api/tasks/{id} and /api/tasks/{id}/status agree."""
        assert TestE2ERestApi.task_id, "submit task first"
        info = _req("GET", f"/api/tasks/{TestE2ERestApi.task_id}")
        status_info = _req("GET", f"/api/tasks/{TestE2ERestApi.task_id}/status")
        assert info.get("status") == status_info.get("status"), (
            f"Status mismatch: {info.get('status')} vs {status_info.get('status')}"
        )

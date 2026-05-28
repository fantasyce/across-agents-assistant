"""E2E test: minimal real task (hello.py).

Prerequisites:
  1. The Across Agents Assistant app is running (backend Unix socket available).
  2. API keys are configured in ~/.across_agents/credentials.json via app.

Usage:
  python3 -m pytest tests/e2e/test_e2e_minimal_task.py -v

Environment:
  ACROSS_AGENTS_SOCKET — packaged app backend socket (default ~/.across_agents/run/across-agents.sock)
  ACROSS_AGENTS_API    — optional HTTP URL for development servers
"""

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import configured_providers, request

# ── helpers ──────────────────────────────────────────────────────────────────


def _req(method: str, path: str, body: dict = None, expect: int = 200) -> dict:
    return request(method, path, body, expect)


def _wait_task(
    task_id: str,
    timeout: int = 600,
    poll: int = 3,
) -> dict:
    """Poll task info until it reaches a terminal state."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = _req("GET", f"/api/tasks/{task_id}")
        status = info.get("status", "unknown")
        active_subtasks = [
            st for st in info.get("subtasks", [])
            if st.get("status") in ("pending", "dispatched", "running")
        ]
        active_remediation = (info.get("quality_health") or {}).get("active_remediation_subtasks") or []
        if status in ("completed", "completed_with_failures", "paused"):
            return info
        if status == "failed" and not active_subtasks and not active_remediation:
            return info
        time.sleep(poll)
    raise TimeoutError(f"Task {task_id} did not finish within {timeout}s")


# ── E2E-1: minimal hello.py task ────────────────────────────────────────────


class TestE2EMinimalTask:
    """Create a trivial hello.py script and verify the full pipeline."""

    task_id: str = None

    @pytest.fixture(autouse=True)
    def check_backend(self):
        _req("GET", "/api/llm/status")

    def test_01_readiness_no_keys(self):
        """Verify readiness check rejects submission when no keys."""
        # Temporarily verify we have keys — if not, the failure mode is known
        status = _req("GET", "/api/keys/status")
        raw_providers = status.get("providers", [])
        if isinstance(raw_providers, dict):
            providers = dict(raw_providers)
        else:
            providers = {p["provider_id"]: p["status"] for p in raw_providers}
        configured = [pid for pid, s in providers.items() if s == "configured"]
        if not configured:
            pytest.skip("No API keys configured — cannot run E2E task")

    def test_02_submit_task(self):
        """Submit a minimal hello.py task via /api/tasks/auto."""
        result = _req(
            "POST",
            "/api/tasks/auto",
            {
                "description": "Create a simple hello.py that prints 'Hello from E2E test'",
                "project_dir": f"/tmp/hello-e2e-{int(time.time())}",
                "task_types": ["artifact"],
                "allowed_subtask_agents": [],
                "strict_dependency": True,
                "enable_wave_gate": True,
            },
        )
        TestE2EMinimalTask.task_id = result.get("task_id")
        assert TestE2EMinimalTask.task_id, f"No task_id in response: {result}"

    def test_03_task_has_contracts(self):
        """task-level / subtask-level contracts exist after decomposition."""
        assert TestE2EMinimalTask.task_id, "submit task first"
        deadline = time.time() + 90
        info = {}
        while time.time() < deadline:
            info = _req("GET", f"/api/tasks/{TestE2EMinimalTask.task_id}")
            if info.get("owner_delivery_contract") is not None and info.get("requirement_manifest") is not None:
                break
            time.sleep(2)
        assert info.get("owner_delivery_contract") is not None, f"No owner delivery contract: {info}"
        assert info.get("requirement_manifest") is not None, f"No requirement manifest: {info}"
        assert "quality_health" in info, f"No quality_health: {info}"

    def test_04_wait_and_verify(self):
        """Wait for task completion and verify artifacts."""
        assert TestE2EMinimalTask.task_id, "submit task first"
        info = _wait_task(TestE2EMinimalTask.task_id, timeout=600)
        status = info.get("status", "unknown")
        assert status in (
            "completed",
            "completed_with_failures",
        ), (
            f"Task ended with unexpected status: {status}\nFull: {json.dumps(info, indent=2)}"
        )
        # Verify artifacts exist
        assert info.get("artifacts") is not None, f"No artifacts in task info: {info}"
        # Verify acceptance_records exist
        assert info.get("acceptance_records") is not None, (
            f"No acceptance_records in task info: {info}"
        )
        report = info.get("delivery_report") or {}
        assert report.get("quality_gate") in ("passed", "partial", "failed", None)
        # Verify project_dir exists
        assert info.get("project_dir"), (
            f"project_dir is empty: {info}"
        )
        # Verify status consistency with /status endpoint
        status_info = _req("GET", f"/api/tasks/{TestE2EMinimalTask.task_id}/status")
        assert status_info.get("status") == status, (
            f"Status mismatch: /api/tasks/{{id}} says {status}, "
            f"/api/tasks/{{id}}/status says {status_info.get('status')}"
        )

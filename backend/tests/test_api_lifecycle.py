"""Tests for API server lifecycle side effects."""

import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_importing_api_server_does_not_run_orphan_recovery():
    """Importing api_server should not mutate persistence or run startup recovery."""
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"

    script = """
import os
import tempfile

os.environ["ACROSS_AGENTS_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from across_agents_assistant.task_manager.state import TaskState

def fake_recovery(self, *args, **kwargs):
    print("RECOVERY_CALLED")
    return 0

TaskState.recover_orphaned_persisted_tasks = fake_recovery

import across_agents_assistant.api_server  # noqa: F401
print("IMPORTED")
"""

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "IMPORTED" in result.stdout
    assert "RECOVERY_CALLED" not in result.stdout


def test_api_startup_configures_persistence_without_task_recovery():
    """FastAPI startup should make persistence available without scanning task history."""
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"

    script = """
import os
import tempfile

from fastapi.testclient import TestClient

os.environ["ACROSS_AGENTS_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from across_agents_assistant.task_manager.state import TaskState

calls = {"recovery": 0, "restore_scan": 0}

def fake_recovery(self, *args, **kwargs):
    calls["recovery"] += 1
    return 0

def fake_restore_scan(self, *args, **kwargs):
    calls["restore_scan"] += 1
    return 0

TaskState.recover_orphaned_persisted_tasks = fake_recovery
TaskState.restore_from_persistence = fake_restore_scan

import across_agents_assistant.api_server as srv

with TestClient(srv.app):
    pass

with TestClient(srv.app):
    pass

print(f"RECOVERY_CALLS={calls['recovery']}")
print(f"RESTORE_SCAN_CALLS={calls['restore_scan']}")
print(f"PERSISTENCE_INITIALIZED={srv._task_persistence_initialized}")
"""

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "RECOVERY_CALLS=0" in result.stdout
    assert "RESTORE_SCAN_CALLS=0" in result.stdout
    assert "PERSISTENCE_INITIALIZED=True" in result.stdout


def test_auto_resume_env_does_not_resume_tasks_during_startup():
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"

    script = """
import os
import tempfile
from fastapi.testclient import TestClient

os.environ["ACROSS_AGENTS_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ACROSS_AGENTS_AUTO_RESUME_ORPHANS"] = "1"

import across_agents_assistant.api_server as srv

srv._task_persistence_initialized = False

with TestClient(srv.app):
    pass

print("STARTUP_COMPLETED=1")
"""

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "STARTUP_COMPLETED=1" in result.stdout


def test_health_endpoint_reports_backend_socket_and_database(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as srv

    socket_path = tmp_path / "across-agents.sock"
    socket_path.write_text("", encoding="utf-8")
    db_path = tmp_path / "assistant.db"
    fake_state = SimpleNamespace(
        _persistence=SimpleNamespace(db=SimpleNamespace(db_path=str(db_path))),
        get_all_tasks=lambda: [SimpleNamespace(), SimpleNamespace()],
    )
    monkeypatch.setattr(srv, "SOCKET_PATH", str(socket_path))
    monkeypatch.setattr(srv, "_task_state", fake_state)

    response = TestClient(srv.app).get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["socket"]["path"] == str(socket_path)
    assert payload["socket"]["exists"] is True
    assert payload["database"]["path"] == str(db_path)
    assert payload["orchestrator"]["known_tasks"] == 2


def test_backend_singleton_lock_rejects_duplicate_socket_owner(monkeypatch, tmp_path):
    import fcntl

    import across_agents_assistant.api_server as srv

    socket_path = tmp_path / "across-agents.sock"
    lock_path = socket_path.with_suffix(".lock")
    monkeypatch.setattr(srv, "SOCKET_PATH", str(socket_path))
    if srv._backend_lock_fd is not None:
        os.close(srv._backend_lock_fd)
    srv._backend_lock_fd = None

    external_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(external_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert srv._acquire_backend_singleton_lock() is False
    finally:
        fcntl.flock(external_fd, fcntl.LOCK_UN)
        os.close(external_fd)

    try:
        assert srv._acquire_backend_singleton_lock() is True
        assert lock_path.read_text(encoding="utf-8") == str(os.getpid())
    finally:
        if srv._backend_lock_fd is not None:
            os.close(srv._backend_lock_fd)
        srv._backend_lock_fd = None


def test_shutdown_suspends_running_tasks_instead_of_cancelling(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as srv
    from across_agents_assistant.task_manager.models import TaskStatus

    calls = []

    class FakeState:
        def __init__(self):
            self._tasks = {
                "task-running": SimpleNamespace(status=TaskStatus.RUNNING),
                "task-done": SimpleNamespace(status=TaskStatus.COMPLETED),
            }

        def pause_task(self, task_id):
            calls.append(("pause", task_id))
            return True

        def set_task_status(self, task_id, status, error=None):
            calls.append(("status", task_id, status, error))
            return True

        def cancel_task(self, task_id):
            raise AssertionError("shutdown must not cancel running tasks")

    marker_path = tmp_path / "backend_shutdown.json"
    monkeypatch.setattr(srv, "_task_state", FakeState())
    monkeypatch.setattr(srv, "_shutdown_marker_path", lambda: marker_path)

    suspended = srv._suspend_running_tasks_for_shutdown(signal.SIGTERM)

    assert suspended == ["task-running"]
    assert ("pause", "task-running") in calls
    status_calls = [call for call in calls if call[0] == "status"]
    assert status_calls == [
        ("status", "task-running", TaskStatus.PAUSED, "suspended_for_restart: backend received signal 15")
    ]
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["signal"] == signal.SIGTERM
    assert marker["reason"] == "sigterm"
    assert marker["active_tasks"] == ["task-running"]

import json
import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app


@pytest.mark.asyncio
async def test_lifespan_does_not_wait_for_optional_worker_runtime(monkeypatch):
    worker_release = threading.Event()

    class FakeRuntime:
        def reconcile(self):
            worker_release.wait(timeout=2)
            return {"status": "running"}

        def shutdown(self):
            return None

    class FakePresence:
        def snapshot(self):
            return {"nodes": []}

    runtime = FakeRuntime()
    monkeypatch.setattr(api_server, "_restrict_api_socket_permissions", lambda: None)
    monkeypatch.setattr(api_server, "_init_task_persistence", lambda: None)
    monkeypatch.setattr(api_server, "_restore_self_iteration_scheduler_on_startup", lambda: {"status": "ready"})
    monkeypatch.setattr(api_server, "_stop_autopilot_trigger_scheduler_for_shutdown", lambda: None)
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: runtime)
    monkeypatch.setattr(api_server, "get_worker_presence_cache", lambda: FakePresence())

    started_at = time.perf_counter()
    async with api_server._api_lifespan(api_server.app):
        assert time.perf_counter() - started_at < 0.1
        await asyncio.sleep(0)
        worker_release.set()


@pytest.mark.asyncio
async def test_core_health_uses_cached_worker_state_during_reconciliation(monkeypatch):
    cached = {"status": "ready", "node_count": 1, "online_count": 1}
    with api_server._worker_health_cache_lock:
        api_server._worker_health_cache.clear()
        api_server._worker_health_cache.update(cached)

    def locked_worker_snapshot():
        time.sleep(0.2)
        return {"health": {"status": "late"}}

    monkeypatch.setattr(api_server, "_worker_control_snapshot_with_presence", locked_worker_snapshot)
    started_at = time.perf_counter()
    health = await api_server.get_health()

    assert time.perf_counter() - started_at < 0.15
    assert health["worker_control"] == cached


@pytest.mark.asyncio
async def test_core_health_does_not_wait_for_task_restoration_lock(monkeypatch):
    class LockedTaskState:
        _persistence = None

        def get_all_tasks(self):
            time.sleep(0.2)
            return [object()]

    monkeypatch.setattr(api_server, "_task_state", LockedTaskState())
    monkeypatch.setattr(
        api_server,
        "_worker_health_for_core_probe",
        lambda: asyncio.sleep(0, result={"status": "ready"}),
    )
    started_at = time.perf_counter()
    health = await api_server.get_health()

    assert time.perf_counter() - started_at < 0.15
    assert health["orchestrator"]["known_tasks"] == 0


@pytest.mark.asyncio
async def test_startup_diagnostics_do_not_block_core_api_event_loop(monkeypatch):
    def slow_diagnostics():
        time.sleep(0.15)
        return {"status": "ready"}

    monkeypatch.setattr(api_server, "_build_startup_diagnostics", slow_diagnostics)
    started_at = time.perf_counter()
    diagnostics = asyncio.create_task(api_server.get_startup_diagnostics())
    await asyncio.sleep(0.02)

    assert time.perf_counter() - started_at < 0.1
    assert not diagnostics.done()
    assert await diagnostics == {"status": "ready"}


@pytest.mark.asyncio
async def test_task_page_does_not_block_core_api_event_loop(monkeypatch):
    def slow_task_page(**_kwargs):
        time.sleep(0.15)
        return {"tasks": [], "total": 0, "limit": 50, "offset": 0, "has_more": False}

    monkeypatch.setattr(api_server, "_list_task_summaries_sync", slow_task_page)
    started_at = time.perf_counter()
    task_page = asyncio.create_task(api_server.list_task_summaries())
    await asyncio.sleep(0.02)

    assert time.perf_counter() - started_at < 0.1
    assert not task_page.done()
    assert await task_page == {
        "tasks": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
        "has_more": False,
    }


@pytest.mark.asyncio
async def test_task_page_uses_in_memory_snapshot_during_task_state_mutation(monkeypatch):
    class LockedTaskState:
        _tasks = {}
        _persistence = None

        def get_all_tasks(self):
            time.sleep(0.2)
            return []

    class NoExternalTasks:
        def list_task_summaries(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", LockedTaskState())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: NoExternalTasks())
    started_at = time.perf_counter()
    page = await api_server.list_task_summaries()

    assert time.perf_counter() - started_at < 0.1
    assert page.tasks == []


@pytest.mark.asyncio
async def test_task_page_uses_cached_worker_projection(monkeypatch):
    class NoPersistenceTaskState:
        _tasks = {}
        _persistence = None

    class OneExternalTask:
        def list_task_summaries(self):
            return [{
                "task_id": "task-worker-cached",
                "description": "Cached Worker task",
                "status": "pending",
                "updated_at": 1,
            }]

    class CachedOnlyBridge:
        def cached_status(self, task_id):
            assert task_id == "task-worker-cached"
            return {"status": "running", "updated_at": 2}

        def optional_status(self, _task_id):
            raise AssertionError("task list must not contact the live Worker runtime")

        def project_task_summary(self, summary, remote):
            return {**summary, "status": remote["status"], "updated_at": remote["updated_at"]}

    monkeypatch.setattr(api_server, "_task_state", NoPersistenceTaskState())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: OneExternalTask())
    monkeypatch.setattr(api_server, "get_worker_task_bridge", lambda: CachedOnlyBridge())

    page = await api_server.list_task_summaries()

    assert page.tasks[0].task_id == "task-worker-cached"
    assert page.tasks[0].status == "running"


@pytest.mark.asyncio
async def test_project_and_session_shell_reads_do_not_block_core_api_event_loop(monkeypatch):
    class SlowPersistence:
        def list_projects(self, *, session_limit):
            assert session_limit == 5
            time.sleep(0.15)
            return []

        def list_sessions(self, *, limit, offset, project_id):
            assert (limit, offset, project_id) == (50, 0, None)
            time.sleep(0.15)
            return ([], 0)

    monkeypatch.setattr(api_server, "persistence", SlowPersistence())
    started_at = time.perf_counter()
    projects = asyncio.create_task(api_server.list_projects())
    sessions = asyncio.create_task(api_server.list_sessions())
    await asyncio.sleep(0.02)

    assert time.perf_counter() - started_at < 0.1
    assert not projects.done()
    assert not sessions.done()
    assert (await projects).projects == []
    assert (await sessions).sessions == []


def _healthy_orchestrator_plugin_status(*, probe=True):
    return {
        "mode": "external",
        "implementation": "external",
        "available": True,
        "transport": "cli",
        "endpoint": None,
        "command_available": True,
        "task_index_count": 0,
        "install": {
            "installable": True,
            "installed": True,
            "source": "file:///Users/example/.across/plugins/across-orchestrator/packages/across_orchestrator-0.6.1-py3-none-any.whl",
        },
        "connection_note": "External Across Orchestrator CLI runtime.",
    }


def test_startup_diagnostics_endpoint_reports_safe_runtime_health(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    monkeypatch.setattr(api_server, "_orchestrator_plugin_status", _healthy_orchestrator_plugin_status)
    monkeypatch.setattr(
        api_server,
        "_worker_control_snapshot_with_presence",
        lambda: {
            "listener": {"enabled": False},
            "relay": {"enabled": False},
            "health": {
                "node_count": 1,
                "online_count": 1,
                "pending_count": 0,
                "incompatible_count": 0,
            },
        },
    )

    (tmp_path / "logs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "tmp").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "assistant.db").touch()
    (tmp_path / "run" / "across-agents.sock").touch()

    monkeypatch.setattr(api_server, "app_home", lambda: tmp_path)
    monkeypatch.setattr(api_server, "app_log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(api_server, "run_dir", lambda: tmp_path / "run")
    monkeypatch.setattr(api_server, "tmp_dir", lambda: tmp_path / "tmp")
    monkeypatch.setattr(api_server, "app_subdir", lambda name: tmp_path / name)
    monkeypatch.setattr(api_server, "backend_socket_path", lambda: str(tmp_path / "run" / "across-agents.sock"))
    monkeypatch.setattr(api_server, "_build_key_readiness", lambda: {
        "has_any_key": True,
        "providers": {"deepseek": "configured", "minimax": "not_configured"},
        "readiness_blockers": [],
    })

    class FakePersistence:
        class DB:
            db_path = tmp_path / "assistant.db"

        db = DB()

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return [{"task_id": "task-a"}]

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_task_persistence_initialized", True)

    response = TestClient(app).get("/api/diagnostics/startup")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "ready"
    assert body["summary"]["failed"] == 0
    assert body["summary"]["warnings"] == 0
    assert body["runtime"]["known_tasks"] == 1
    assert "orchestrator_initialized" not in body["runtime"]
    assert "dispatcher_initialized" not in body["runtime"]
    assert body["paths"]["app_home"] == str(tmp_path)
    assert body["keys"]["providers"]["deepseek"] == "configured"
    assert body["runtime"]["orchestrator_plugin"]["install"]["source"].startswith("file:///Users/example/.across/")
    assert {check["id"] for check in body["checks"]} >= {
        "backend_health",
        "app_home",
        "logs_dir",
        "run_dir",
        "backend_socket",
        "database",
        "provider_keys",
        "task_runtime",
    }
    worker_check = next(check for check in body["checks"] if check["id"] == "worker_nodes")
    assert worker_check["status"] == "passed"
    assert worker_check["metadata"]["online_count"] == 1
    encoded = json.dumps(body)
    assert "api_key" not in encoded.lower()
    assert "secret" not in encoded.lower()


def test_startup_diagnostics_warns_when_no_provider_key(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    monkeypatch.setattr(api_server, "_orchestrator_plugin_status", _healthy_orchestrator_plugin_status)

    (tmp_path / "logs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "tmp").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "run" / "across-agents.sock").touch()

    monkeypatch.setattr(api_server, "app_home", lambda: tmp_path)
    monkeypatch.setattr(api_server, "app_log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(api_server, "run_dir", lambda: tmp_path / "run")
    monkeypatch.setattr(api_server, "tmp_dir", lambda: tmp_path / "tmp")
    monkeypatch.setattr(api_server, "app_subdir", lambda name: tmp_path / name)
    monkeypatch.setattr(api_server, "backend_socket_path", lambda: str(tmp_path / "run" / "across-agents.sock"))
    monkeypatch.setattr(api_server, "_build_key_readiness", lambda: {
        "has_any_key": False,
        "providers": {"deepseek": "not_configured", "minimax": "not_configured"},
        "readiness_blockers": ["api_keys"],
    })

    class FakeState:
        _persistence = None

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_task_persistence_initialized", False)

    response = TestClient(app).get("/api/diagnostics/startup")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "attention"
    provider_check = next(check for check in body["checks"] if check["id"] == "provider_keys")
    assert provider_check["status"] == "warning"
    assert provider_check["remediation"] == "Configure at least one cloud LLM provider in Model Settings."
    assert body["summary"]["warnings"] >= 1


def test_startup_diagnostics_blocks_default_when_orchestrator_plugin_missing(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    (tmp_path / "logs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "tmp").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "assistant.db").touch()
    (tmp_path / "run" / "across-agents.sock").touch()

    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", raising=False)
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", raising=False)
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_COMMAND", str(tmp_path / "missing-across-orchestrator"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_PLUGIN_HOME", str(tmp_path / "plugins"))
    monkeypatch.setattr(api_server, "_orchestrator_plugin_manager", None)
    monkeypatch.setattr(api_server, "app_home", lambda: tmp_path)
    monkeypatch.setattr(api_server, "app_log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(api_server, "run_dir", lambda: tmp_path / "run")
    monkeypatch.setattr(api_server, "tmp_dir", lambda: tmp_path / "tmp")
    monkeypatch.setattr(api_server, "app_subdir", lambda name: tmp_path / name)
    monkeypatch.setattr(api_server, "backend_socket_path", lambda: str(tmp_path / "run" / "across-agents.sock"))
    monkeypatch.setattr(api_server, "_build_key_readiness", lambda: {
        "has_any_key": True,
        "providers": {"deepseek": "configured"},
        "readiness_blockers": [],
    })

    class FakePersistence:
        class DB:
            db_path = tmp_path / "assistant.db"

        db = DB()

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_task_persistence_initialized", True)

    response = TestClient(app).get("/api/diagnostics/startup")

    assert response.status_code == 200
    body = response.json()
    plugin_check = next(check for check in body["checks"] if check["id"] == "orchestrator_plugin")
    assert body["status"] == "blocked"
    assert plugin_check["status"] == "failed"
    assert plugin_check["metadata"]["mode"] == "external"
    assert plugin_check["metadata"]["install"]["installable"] is True

import json

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app


def _healthy_orchestrator_plugin_status(*, probe=True):
    return {
        "mode": "external",
        "implementation": "external",
        "available": True,
        "transport": "cli",
        "endpoint": None,
        "command_available": True,
        "task_index_count": 0,
        "install": {"installable": True, "installed": True},
        "connection_note": "External Across Orchestrator CLI runtime.",
    }


def test_startup_diagnostics_endpoint_reports_safe_runtime_health(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    monkeypatch.setattr(api_server, "_orchestrator_plugin_status", _healthy_orchestrator_plugin_status)

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
    monkeypatch.setattr(api_server, "_task_orchestrator", object())
    monkeypatch.setattr(api_server, "_task_dispatcher", object())

    response = TestClient(app).get("/api/diagnostics/startup")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "ready"
    assert body["summary"]["failed"] == 0
    assert body["summary"]["warnings"] == 0
    assert body["runtime"]["known_tasks"] == 1
    assert body["paths"]["app_home"] == str(tmp_path)
    assert body["keys"]["providers"]["deepseek"] == "configured"
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
    monkeypatch.setattr(api_server, "_task_orchestrator", None)
    monkeypatch.setattr(api_server, "_task_dispatcher", None)

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
    monkeypatch.setattr(api_server, "_task_orchestrator", None)
    monkeypatch.setattr(api_server, "_task_dispatcher", None)

    response = TestClient(app).get("/api/diagnostics/startup")

    assert response.status_code == 200
    body = response.json()
    plugin_check = next(check for check in body["checks"] if check["id"] == "orchestrator_plugin")
    assert body["status"] == "blocked"
    assert plugin_check["status"] == "failed"
    assert plugin_check["metadata"]["mode"] == "external"
    assert plugin_check["metadata"]["install"]["installable"] is True

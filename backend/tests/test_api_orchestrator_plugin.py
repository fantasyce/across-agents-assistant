import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app
from across_agents_assistant.task_manager.orchestration.release_e2e import RELEASE_E2E_SCENARIO_ID


REQUIRED_FILES = [
    "README.md",
    "web/index.html",
    "web/styles.css",
    "web/app.js",
    "api/server.mjs",
    "cli/quality-check.mjs",
    "tests/e2e-smoke.mjs",
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _task(task_id: str, project_dir: str, status: str) -> dict:
    subtask_status = "completed" if status == "completed" else "pending"
    return {
        "task_id": task_id,
        "goal": "Release E2E scenario: Cross-Agent Full Delivery Gate",
        "project_root": project_dir,
        "status": status,
        "agent": "app-grade",
        "subtasks": [
            {
                "subtask_id": "subtask-api",
                "goal": "Create Node API service",
                "path": "api/server.mjs",
                "agent": "deepseek",
                "status": subtask_status,
                "wave": 1,
                "attempts": 1 if status == "completed" else 0,
                "error": None,
            },
            {
                "subtask_id": "subtask-browser",
                "goal": "Verify browser E2E behavior",
                "path": "tests/e2e-smoke.mjs",
                "agent": "openclaw",
                "status": subtask_status,
                "wave": 1,
                "attempts": 1 if status == "completed" else 0,
                "error": None,
            },
        ],
        "contract": {
            "contractVersion": "0.4-app-grade",
            "engine": "app_grade_release_e2e",
            "scenarioId": RELEASE_E2E_SCENARIO_ID,
            "requiredArtifacts": REQUIRED_FILES,
            "qualityGates": [
                "workspace_hygiene",
                "security_privacy",
                "static_web",
                "api_service",
                "cli_generic",
                "browser_e2e",
            ],
            "requiredAgentMix": {
                "min_distinct_agents": 3,
                "min_local_agents": 2,
                "min_cloud_agents": 1,
            },
        },
        "metadata": {},
        "created_at": 1_700_000_000.0,
        "updated_at": 1_700_000_100.0,
    }


def _evidence(task_id: str, project_dir: str) -> dict:
    gate_results = [
        {"adapter_id": "artifact_integrity", "status": "passed"},
        {"adapter_id": "workspace_hygiene", "status": "passed"},
        {"adapter_id": "security_privacy", "status": "passed"},
        {"adapter_id": "agent_mix", "status": "passed"},
        {"adapter_id": "static_web_smoke", "status": "passed"},
        {"adapter_id": "browser_e2e", "status": "passed"},
        {"adapter_id": "api_service", "status": "passed"},
        {"adapter_id": "cli_generic", "status": "passed"},
    ]
    return {
        "schema_version": "0.1",
        "task_id": task_id,
        "goal": "Release E2E scenario: Cross-Agent Full Delivery Gate",
        "status": "completed",
        "project_root": project_dir,
        "contract": _task(task_id, project_dir, "completed")["contract"],
        "subtasks": _task(task_id, project_dir, "completed")["subtasks"],
        "artifacts": [
            {"path": path, "present": True, "size": 10, "sha256": "b" * 64}
            for path in REQUIRED_FILES
        ],
        "quality": {"status": "passed"},
        "events": [{"type": "task.completed", "task_id": task_id}],
        "app_grade": {
            "scenario_id": RELEASE_E2E_SCENARIO_ID,
            "scenario_title": "Cross-Agent Full Delivery Gate",
            "complexity_score": 94,
            "project_root": project_dir,
            "required_files": REQUIRED_FILES,
            "written_files": REQUIRED_FILES,
            "exact_files": sorted(REQUIRED_FILES),
            "delivery_quality": "passed",
            "quality_report": {
                "task_id": task_id,
                "status": "passed",
                "quality_gate": "passed",
                "required_failed_count": 0,
                "gate_results": gate_results,
                "probe_results": [
                    {"probe_type": item["adapter_id"], "passed": True}
                    for item in gate_results
                ],
            },
        },
    }


class FakeHTTPOrchestrator:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.task_id = "task-api-external"
        self.status = "pending"
        self.requests = []
        self.port = _free_port()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def _json(self, payload, status=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                owner.requests.append(("GET", self.path))
                if self.path == "/health":
                    self._json({"status": "ok"})
                    return
                if self.path == "/.well-known/agent-card.json":
                    self._json({"name": "Across Orchestrator", "version": "0.2.0"})
                    return
                if self.path == f"/tasks/{owner.task_id}":
                    self._json(_task(owner.task_id, owner.project_dir, owner.status))
                    return
                if self.path == f"/tasks/{owner.task_id}/evidence-bundle":
                    self._json(_evidence(owner.task_id, owner.project_dir))
                    return
                if self.path == f"/tasks/{owner.task_id}/quality-benchmark":
                    self._json({"status": "passed"})
                    return
                if self.path == f"/tasks/{owner.task_id}/events":
                    self._json([{"type": "task.completed", "task_id": owner.task_id}])
                    return
                self._json({"error": "not_found"}, 404)

            def do_POST(self):
                owner.requests.append(("POST", self.path))
                length = int(self.headers.get("Content-Length") or "0")
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}") if length else {}
                if self.path == "/release-e2e":
                    owner.last_submit = payload
                    self._json(_task(owner.task_id, owner.project_dir, "pending"), 201)
                    return
                if self.path == "/tasks":
                    owner.last_submit = payload
                    self._json(_task(owner.task_id, payload.get("projectRoot") or owner.project_dir, "pending"), 201)
                    return
                if self.path == f"/tasks/{owner.task_id}/run":
                    owner.status = "completed"
                    self._json(_task(owner.task_id, owner.project_dir, "completed"))
                    return
                self._json({"error": "not_found"}, 404)

        self.last_submit = {}
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_exc):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _reset_plugin_manager():
    api_server._orchestrator_plugin_manager = None


def test_release_e2e_uses_external_orchestrator_slot_for_full_task_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", "external")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_AUTORUN", "0")

    with FakeHTTPOrchestrator(str(tmp_path / "project")) as server:
        monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", server.endpoint)
        _reset_plugin_manager()

        client = TestClient(app)
        created = client.post(
            "/api/release/e2e/tasks",
            json={
                "scenario_id": RELEASE_E2E_SCENARIO_ID,
                "project_dir": str(tmp_path / "project"),
                "run_label": "api-slot",
            },
        )
        assert created.status_code == 200
        task_id = created.json()["task_id"]

        detail = client.get(f"/api/tasks/{task_id}").json()
        run = client.post(f"/api/tasks/{task_id}/run").json()
        status = client.get(f"/api/tasks/{task_id}/status").json()
        evidence = client.get(
            f"/api/tasks/{task_id}/evidence-bundle",
            params={
                "expected_files": ",".join(REQUIRED_FILES),
                "required_probes": "static_web_smoke,browser_e2e,api_service,cli_generic",
            },
        ).json()

    assert created.json()["implementation"] == "external"
    assert created.json()["external_task"] is True
    assert task_id == "task-api-external"
    assert detail["observability"]["orchestrator_plugin"]["implementation"] == "external"
    assert run["status"] == "completed"
    assert status["status"] == "completed"
    assert status["quality_health"]["delivery_quality"] == "passed"
    assert evidence["benchmark"]["status"] == "passed"
    assert evidence["audit"]["expected_files"] == REQUIRED_FILES
    assert ("POST", "/release-e2e") in server.requests
    assert ("POST", "/tasks/task-api-external/run") in server.requests


def test_task_page_and_startup_diagnostics_include_orchestrator_plugin(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", "external")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_AUTORUN", "0")

    (tmp_path / "app-home" / "logs").mkdir(parents=True)
    (tmp_path / "app-home" / "run").mkdir(parents=True)
    (tmp_path / "app-home" / "tmp").mkdir(parents=True)
    (tmp_path / "app-home" / "evidence").mkdir(parents=True)
    (tmp_path / "app-home" / "assistant.db").touch()
    (tmp_path / "app-home" / "run" / "across-agents.sock").touch()

    monkeypatch.setattr(api_server, "_build_key_readiness", lambda: {
        "has_any_key": True,
        "providers": {"deepseek": "configured"},
        "readiness_blockers": [],
    })
    monkeypatch.setattr(api_server, "_task_persistence_initialized", True)

    with FakeHTTPOrchestrator(str(tmp_path / "project")) as server:
        monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", server.endpoint)
        _reset_plugin_manager()
        client = TestClient(app)
        created = client.post(
            "/api/release/e2e/tasks",
            json={"project_dir": str(tmp_path / "project"), "run_label": "diagnostics"},
        )
        assert created.status_code == 200

        page = client.get("/api/tasks/page").json()
        diagnostics = client.get("/api/diagnostics/startup").json()

    assert any(item["task_id"] == "task-api-external" for item in page["tasks"])
    plugin_check = next(check for check in diagnostics["checks"] if check["id"] == "orchestrator_plugin")
    assert plugin_check["status"] == "passed"
    assert plugin_check["metadata"]["implementation"] == "external"
    assert diagnostics["runtime"]["orchestrator_plugin"]["implementation"] == "external"


def test_auto_task_submission_uses_external_orchestrator_plugin(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", "external")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_AUTORUN", "0")

    with FakeHTTPOrchestrator(str(tmp_path / "project")) as server:
        monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", server.endpoint)
        _reset_plugin_manager()
        response = TestClient(app).post(
            "/api/tasks/auto",
            json={
                "description": "Build the public README task handoff",
                "task_types": ["artifact"],
                "owner_agent": "openclaw",
                "project_dir": str(tmp_path / "project"),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["implementation"] == "external"
    assert body["external_task"] is True
    assert body["task_id"] == "task-api-external"
    assert ("POST", "/tasks") in server.requests
    assert server.last_submit["goal"] == "Build the public README task handoff"
    assert server.last_submit["agent"] == "openclaw"
    assert server.last_submit["deliverables"] == ["README.md"]


def test_release_e2e_builtin_mode_still_requires_orchestrator_plugin(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", "builtin")
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", raising=False)
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_COMMAND", str(tmp_path / "missing-across-orchestrator"))
    _reset_plugin_manager()

    response = TestClient(app).post(
        "/api/release/e2e/tasks",
        json={"project_dir": str(tmp_path / "project"), "run_label": "builtin-disabled"},
    )

    assert response.status_code == 503
    assert "Across Orchestrator" in response.json()["detail"]


def test_default_release_e2e_requires_orchestrator_plugin(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", raising=False)
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", raising=False)
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_COMMAND", str(tmp_path / "missing-across-orchestrator"))
    _reset_plugin_manager()

    response = TestClient(app).post(
        "/api/release/e2e/tasks",
        json={"project_dir": str(tmp_path / "project"), "run_label": "default-missing-plugin"},
    )

    assert response.status_code == 503
    assert "Across Orchestrator" in response.json()["detail"]


def test_orchestrator_plugin_status_endpoint_reports_installable_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", raising=False)
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", raising=False)
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_COMMAND", str(tmp_path / "missing-across-orchestrator"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_PLUGIN_HOME", str(tmp_path / "plugins"))
    _reset_plugin_manager()

    response = TestClient(app).get("/api/orchestrator/plugin")

    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["mode"] == "external"
    assert body["runtime"]["available"] is False
    assert body["install"]["installable"] is True
    assert body["install"]["install_dir"] == str(tmp_path / "plugins" / "across-orchestrator")


def test_orchestrator_plugin_install_endpoint_triggers_installer(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.install_called = False

        def implementation_status(self, probe=True):
            return {
                "mode": "external",
                "implementation": "external",
                "available": self.install_called,
                "transport": "cli" if self.install_called else None,
                "command": "/tmp/across-orchestrator",
                "connection_note": "installed" if self.install_called else "missing",
                "install": self.install_status(),
            }

        def install_status(self):
            return {
                "status": "installed" if self.install_called else "not_installed",
                "installed": self.install_called,
                "installable": True,
                "command": "/tmp/across-orchestrator",
                "install_dir": "/tmp/across-orchestrator-plugin",
                "logs": [],
            }

        def install_plugin(self):
            self.install_called = True
            return self.install_status()

    fake = FakeManager()
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: fake)

    response = TestClient(app).post("/api/orchestrator/plugin/install")

    assert response.status_code == 200
    body = response.json()
    assert body["install"]["status"] == "installed"
    assert body["runtime"]["available"] is True
    assert fake.install_called is True


def test_release_e2e_external_required_fails_when_runtime_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", "external")
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", raising=False)
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_COMMAND", str(tmp_path / "missing-across-orchestrator"))
    _reset_plugin_manager()

    response = TestClient(app).post(
        "/api/release/e2e/tasks",
        json={"project_dir": str(tmp_path / "project"), "run_label": "missing-external"},
    )

    assert response.status_code == 503
    assert "External Across Orchestrator" in response.json()["detail"]

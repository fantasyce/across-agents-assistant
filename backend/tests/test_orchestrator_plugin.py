import json
import os
import socket
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import across_agents_assistant.orchestrator_plugin as orchestrator_plugin
from across_agents_assistant.orchestrator_plugin import (
    OrchestratorPluginInstaller,
    OrchestratorPluginConfig,
    OrchestratorPluginManager,
    evaluate_app_grade_quality,
    external_task_to_app_info,
)


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


def _external_task(task_id: str, project_dir: str, status: str = "pending") -> dict:
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
                "goal": "Create api/server.mjs",
                "path": "api/server.mjs",
                "agent": "deepseek",
                "status": subtask_status,
                "wave": 1,
                "attempts": 1 if status == "completed" else 0,
                "error": None,
            },
            {
                "subtask_id": "subtask-web",
                "goal": "Create web UI",
                "path": "web/index.html",
                "agent": "hermes",
                "status": subtask_status,
                "wave": 1,
                "attempts": 1 if status == "completed" else 0,
                "error": None,
            },
        ],
        "contract": {
            "contractVersion": "0.4-app-grade",
            "engine": "app_grade_release_e2e",
            "scenarioId": "cross_agent_full_delivery_v1",
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


def _external_evidence(task_id: str, project_dir: str) -> dict:
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
        "contract": _external_task(task_id, project_dir, "completed")["contract"],
        "subtasks": _external_task(task_id, project_dir, "completed")["subtasks"],
        "artifacts": [
            {"path": path, "present": True, "size": 10, "sha256": "a" * 64}
            for path in REQUIRED_FILES
        ],
        "quality": {"status": "passed"},
        "events": [{"type": "task.completed", "task_id": task_id}],
        "app_grade": {
            "scenario_id": "cross_agent_full_delivery_v1",
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


class _FakeOrchestratorHTTPServer:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.task_id = "task-external-http"
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
                    self._json(_external_task(owner.task_id, owner.project_dir, owner.status))
                    return
                if self.path == f"/tasks/{owner.task_id}/evidence-bundle":
                    self._json(_external_evidence(owner.task_id, owner.project_dir))
                    return
                if self.path == f"/tasks/{owner.task_id}/quality-benchmark":
                    self._json({"status": "passed", "present_artifacts": len(REQUIRED_FILES)})
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
                    self._json(_external_task(owner.task_id, owner.project_dir, "pending"), 201)
                    return
                if self.path == f"/tasks/{owner.task_id}/run":
                    owner.status = "completed"
                    self._json(_external_task(owner.task_id, owner.project_dir, "completed"))
                    return
                self._json({"error": "not_found"}, 404)

        self.status = "pending"
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


def test_auto_mode_without_external_runtime_requires_plugin(tmp_path):
    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="auto",
            endpoint=None,
            command=str(tmp_path / "missing-across-orchestrator"),
            registry_path=tmp_path / "tasks.json",
        )
    )

    status = manager.implementation_status()

    assert status["mode"] == "external"
    assert status["implementation"] == "external"
    assert status["available"] is False
    assert status["error"] == "across-orchestrator not found"
    assert "required" in status["connection_note"].lower()


def test_builtin_mode_is_normalized_to_external_plugin_boundary(tmp_path):
    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="builtin",
            endpoint=None,
            command=str(tmp_path / "missing-across-orchestrator"),
            registry_path=tmp_path / "tasks.json",
        )
    )

    status = manager.implementation_status()

    assert status["mode"] == "external"
    assert status["implementation"] == "external"
    assert status["available"] is False


def test_default_mode_requires_external_runtime_and_reports_install_plan(monkeypatch, tmp_path):
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", raising=False)
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", raising=False)
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_COMMAND", str(tmp_path / "missing-across-orchestrator"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_PLUGIN_HOME", str(tmp_path / "plugins"))

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig.from_env(registry_path=tmp_path / "tasks.json")
    )

    status = manager.implementation_status(probe=False)

    assert status["mode"] == "external"
    assert status["implementation"] == "external"
    assert status["available"] is False
    assert status["install"]["installable"] is True
    assert status["install"]["install_dir"] == str(tmp_path / "plugins" / "across-orchestrator")
    assert "required" in status["connection_note"].lower()


def test_app_managed_orchestrator_command_is_discovered_before_path_lookup(tmp_path):
    plugin_home = tmp_path / "plugins"
    cli_path = plugin_home / "across-orchestrator" / "venv" / "bin" / "across-orchestrator"
    cli_path.parent.mkdir(parents=True)
    cli_path.write_text(
        """#!/usr/bin/env python3
import json, sys
if sys.argv[1:3] == ["agent-card", "--json"]:
    print(json.dumps({"name": "Across Orchestrator", "version": "0.2.0"}))
else:
    print(json.dumps({"error": "unsupported"}))
    sys.exit(2)
""",
        encoding="utf-8",
    )
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command="missing-across-orchestrator",
            registry_path=tmp_path / "tasks.json",
            plugin_home=plugin_home,
        )
    )

    status = manager.implementation_status()

    assert status["implementation"] == "external"
    assert status["available"] is True
    assert status["transport"] == "cli"
    assert status["command"] == str(cli_path)
    assert status["install"]["installed"] is True


def test_external_cli_runtime_does_not_inherit_app_pythonpath(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONPATH", "/tmp/app-backend-src-that-must-not-leak")
    cli_path = tmp_path / "across-orchestrator"
    cli_path.write_text(
        """#!/usr/bin/env python3
import json, os, sys
if os.environ.get("PYTHONPATH"):
    print("PYTHONPATH leaked", file=sys.stderr)
    sys.exit(9)
print(json.dumps({"name": "Across Orchestrator", "version": "0.2.0"}))
""",
        encoding="utf-8",
    )
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command=str(cli_path),
            registry_path=tmp_path / "tasks.json",
        )
    )

    status = manager.implementation_status()

    assert status["available"] is True
    assert status["transport"] == "cli"


def test_orchestrator_plugin_installer_installs_into_app_managed_venv(tmp_path):
    plugin_home = tmp_path / "plugins"
    source = tmp_path / "across-orchestrator-src"
    source.mkdir()
    calls = []

    def fake_run(args, **_kwargs):
        calls.append([str(item) for item in args])
        if args[:3] == [os.sys.executable, "-m", "venv"]:
            cli_path = plugin_home / "across-orchestrator" / "venv" / "bin" / "across-orchestrator"
            cli_path.parent.mkdir(parents=True, exist_ok=True)
            cli_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    installer = OrchestratorPluginInstaller(
        plugin_home=plugin_home,
        source=str(source),
        runner=fake_run,
    )

    state = installer.install()

    assert state["status"] == "installed"
    assert state["installed"] is True
    assert state["command"] == str(plugin_home / "across-orchestrator" / "venv" / "bin" / "across-orchestrator")
    assert calls[0][:3] == [os.sys.executable, "-m", "venv"]
    assert calls[1][1:4] == ["-m", "pip", "install"]
    assert calls[2][1:4] == ["-m", "pip", "install"]


def test_packaged_installer_uses_real_python_instead_of_backend_executable(monkeypatch, tmp_path):
    backend_binary = tmp_path / "backend"
    backend_binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    backend_binary.chmod(backend_binary.stat().st_mode | stat.S_IXUSR)
    real_python = tmp_path / "python3.11"
    real_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    real_python.chmod(real_python.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(orchestrator_plugin.sys, "executable", str(backend_binary))
    monkeypatch.setattr(orchestrator_plugin.sys, "frozen", True, raising=False)
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_PYTHON", str(real_python))

    installer = OrchestratorPluginInstaller(
        plugin_home=tmp_path / "plugins",
        source=str(tmp_path / "source"),
        runner=lambda *_args, **_kwargs: None,
    )

    assert installer.python_executable == str(real_python)


def test_external_http_runtime_submits_runs_and_maps_app_task(tmp_path):
    with _FakeOrchestratorHTTPServer(str(tmp_path / "project")) as server:
        manager = OrchestratorPluginManager(
            OrchestratorPluginConfig(
                mode="external",
                endpoint=server.endpoint,
                command="missing-across-orchestrator",
                registry_path=tmp_path / "tasks.json",
                auto_run=False,
            )
        )

        status = manager.implementation_status()
        task = manager.submit_release_e2e_task(project_dir=str(tmp_path / "project"), run_label="unit")
        completed = manager.run_task(task["task_id"])
        app_task = external_task_to_app_info(completed)
        evidence = manager.get_evidence_bundle(task["task_id"])
        quality = evaluate_app_grade_quality(evidence)

    assert status["implementation"] == "external"
    assert status["transport"] == "http"
    assert task["task_id"] == "task-external-http"
    assert completed["status"] == "completed"
    assert app_task["delivery_mode"] == "composite"
    assert app_task["completed_count"] == app_task["total_count"]
    assert quality["status"] == "passed"
    assert quality["checks"]["browser_e2e"] is True
    assert ("POST", "/release-e2e") in server.requests
    assert ("POST", "/tasks/task-external-http/run") in server.requests
    assert server.last_submit["runLabel"] == "unit"


def test_external_cli_runtime_uses_canonical_command_protocol(tmp_path):
    task_id = "task-external-cli"
    project_dir = str(tmp_path / "project")
    calls_path = tmp_path / "calls.jsonl"
    cli_path = tmp_path / "across-orchestrator"
    cli_path.write_text(
        f"""#!/usr/bin/env python3
import json, pathlib, sys
task_pending = json.loads({json.dumps(_external_task(task_id, project_dir, "pending"))!r})
task_completed = json.loads({json.dumps(_external_task(task_id, project_dir, "completed"))!r})
evidence = json.loads({json.dumps(_external_evidence(task_id, project_dir))!r})
calls = pathlib.Path({str(calls_path)!r})
calls.parent.mkdir(parents=True, exist_ok=True)
with calls.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
cmd = sys.argv[1]
if cmd == "agent-card":
    print(json.dumps({{"name": "Across Orchestrator", "version": "0.2.0"}}))
elif cmd == "submit-release-e2e":
    print(json.dumps(task_pending))
elif cmd == "run":
    print(json.dumps(task_completed))
elif cmd == "status":
    print(json.dumps(task_completed))
elif cmd == "evidence":
    print(json.dumps(evidence))
else:
    print(json.dumps({{"error": "unsupported"}}))
    sys.exit(2)
""",
        encoding="utf-8",
    )
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            endpoint=None,
            command=str(cli_path),
            registry_path=tmp_path / "tasks.json",
            auto_run=False,
        )
    )

    status = manager.implementation_status()
    task = manager.submit_release_e2e_task(project_dir=project_dir, run_label="cli-unit")
    completed = manager.run_task(task["task_id"])
    evidence = manager.get_evidence_bundle(task["task_id"])
    calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]

    assert status["implementation"] == "external"
    assert status["transport"] == "cli"
    assert task["task_id"] == task_id
    assert completed["status"] == "completed"
    assert evaluate_app_grade_quality(evidence)["status"] == "passed"
    assert ["submit-release-e2e", "--project", project_dir, "--run-label", "cli-unit", "--json"] in calls
    assert ["run", task_id, "--json"] in calls

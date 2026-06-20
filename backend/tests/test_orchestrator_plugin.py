import io
import json
import os
import socket
import stat
import threading
import urllib.parse
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


def test_plugin_child_env_strips_pyinstaller_launcher_state():
    env = orchestrator_plugin._sanitize_python_child_env(
        {
            "_PYI_ARCHIVE_FILE": "/Applications/Across Agents Assistant.app/backend",
            "_PYI_PARENT_PROCESS_LEVEL": "1",
            "__PYVENV_LAUNCHER__": "/tmp/venv/bin/python",
            "PYTHONPATH": "/tmp/app",
            "PYTHONHOME": "/tmp/python",
            "PYTHONEXECUTABLE": "/tmp/python",
            "PYINSTALLER_RESET_ENVIRONMENT": "1",
            "ACROSS_HOME": "/Users/example/.across",
            "PATH": "/usr/bin",
        }
    )

    assert "_PYI_ARCHIVE_FILE" not in env
    assert "_PYI_PARENT_PROCESS_LEVEL" not in env
    assert "__PYVENV_LAUNCHER__" not in env
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    assert "PYTHONEXECUTABLE" not in env
    assert "PYINSTALLER_RESET_ENVIRONMENT" not in env
    assert env["ACROSS_HOME"] == "/Users/example/.across"
    assert env["PATH"] == "/usr/bin"


def test_orchestrator_sidecar_env_enables_across_context_memory_provider(tmp_path):
    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command=str(tmp_path / "missing-across-orchestrator"),
            registry_path=tmp_path / "tasks.json",
            plugin_home=tmp_path / "plugins",
        )
    )

    env = manager._env()

    assert env["ACROSS_ORCHESTRATOR_MEMORY_PROVIDER"] == "across-context"
    assert env["ACROSS_CONTEXT_COMMAND"].endswith("/across-context")
    assert not any(path.endswith(".across_agents/plugins/bin") for path in env["PATH"].split(os.pathsep))


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
        self.loop_id = "loop-external-http"
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

            def _sse(self, events, status=200):
                body = "".join(
                    f"event: {event.get('type', 'message')}\n"
                    f"data: {json.dumps(event, sort_keys=True)}\n\n"
                    for event in events
                ).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                owner.requests.append(("GET", self.path))
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
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
                if self.path == f"/loops/{owner.loop_id}":
                    self._json(owner._loop_payload("completed"))
                    return
                if self.path == f"/loops/{owner.loop_id}/health":
                    self._json(owner._loop_health_payload("completed"))
                    return
                if self.path == f"/loops/{owner.loop_id}/telemetry":
                    self._json(owner._loop_telemetry_payload("completed"))
                    return
                if parsed.path == f"/loops/{owner.loop_id}/events":
                    after_sequence = int((query.get("after_sequence") or ["0"])[0] or "0")
                    self._json([
                        event for event in owner._loop_events()
                        if int(event.get("sequence") or 0) > after_sequence
                    ])
                    return
                if parsed.path == f"/loops/{owner.loop_id}/events/stream":
                    after_sequence = int((query.get("after_sequence") or ["0"])[0] or "0")
                    self._sse([
                        event for event in owner._loop_events()
                        if int(event.get("sequence") or 0) > after_sequence
                    ])
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
                if self.path == "/tasks":
                    owner.last_submit = payload
                    self._json(_external_task(owner.task_id, owner.project_dir, "pending"), 201)
                    return
                if self.path == f"/tasks/{owner.task_id}/run":
                    owner.status = "completed"
                    self._json(_external_task(owner.task_id, owner.project_dir, "completed"))
                    return
                if self.path == "/loops":
                    owner.last_loop_submit = payload
                    self._json(owner._loop_payload("pending"), 201)
                    return
                if self.path == f"/loops/{owner.loop_id}/run":
                    owner.loop_status = "completed"
                    self._json(owner._loop_payload("completed"))
                    return
                self._json({"error": "not_found"}, 404)

        self.status = "pending"
        self.loop_status = "pending"
        self.last_submit = {}
        self.last_loop_submit = {}
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

    def _loop_payload(self, status: str) -> dict:
        return {
            "loop_id": self.loop_id,
            "goal": "External loop smoke",
            "project_root": self.project_dir,
            "status": status,
            "agent": "owner",
            "max_turns": 8,
            "turn_count": 5 if status == "completed" else 0,
            "memory_policy": {"provider": "across-context", "read": True, "writeCandidates": True},
            "approval_policy": {"requireApprovalFor": []},
            "steps": [
                {"action": {"type": "memory_search"}},
                {"action": {"type": "task_dispatch"}},
                {"action": {"type": "quality_gate"}},
                {"action": {"type": "memory_write_candidate"}},
                {"action": {"type": "final_output"}},
            ] if status == "completed" else [],
            "checkpoint_count": 5 if status == "completed" else 0,
            "final_output": "Agent loop completed for: External loop smoke" if status == "completed" else None,
        }

    def _loop_health_payload(self, status: str) -> dict:
        return {
            "schema_version": "0.1",
            "loop_id": self.loop_id,
            "status": status,
            "current_action_type": None if status == "completed" else "memory_search",
            "current_step_id": None,
            "pending_approval": None,
            "lease": {"active": False, "lease_seconds": 300.0, "heartbeat_at": 1_700_000_001.0},
            "detached_dispatch_count": 0,
            "recent_failure_types": {},
            "executable_actions": [],
            "cancellation_requested": False,
            "cancel_ack_pending": False,
            "budget": {"max_turns": 8, "turn_count": 5 if status == "completed" else 0, "remaining_turns": 3},
        }

    def _loop_events(self) -> list[dict]:
        return [
            {"event_id": "loop-event-http-1", "sequence": 1, "type": "loop.started", "loop_id": self.loop_id},
            {"event_id": "loop-event-http-2", "sequence": 2, "type": "loop.completed", "loop_id": self.loop_id},
        ]

    def _loop_telemetry_payload(self, status: str) -> dict:
        return {
            "schema_version": "agent-loop-telemetry/1.0",
            "loop_id": self.loop_id,
            "status": status,
            "summary": {"event_count": 2, "turn_count": 5, "memory_candidate_count": 0},
            "metrics": [{"id": "events.total", "value": 2}],
            "latest_sequence": 2,
            "budget": {"max_turns": 8, "turn_count": 5, "remaining_turns": 3},
        }


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


def test_external_http_runtime_proxies_agent_loop_lifecycle(tmp_path):
    with _FakeOrchestratorHTTPServer(str(tmp_path / "project")) as server:
        manager = OrchestratorPluginManager(
            OrchestratorPluginConfig(
                mode="external",
                endpoint=server.endpoint,
                registry_path=tmp_path / "tasks.json",
                auto_run=False,
            )
        )

        loop = manager.start_agent_loop(
            goal="External loop smoke",
            project_dir=str(tmp_path / "project"),
            agent="owner",
            max_turns=8,
        )
        completed = manager.run_agent_loop(loop["loop_id"])
        status = manager.get_agent_loop(loop["loop_id"])
        health = manager.get_agent_loop_health(loop["loop_id"])
        events = manager.get_agent_loop_events(loop["loop_id"])
        resumed_events = manager.get_agent_loop_events(loop["loop_id"], after_sequence=1)
        stream_events = manager.get_agent_loop_events_stream(loop["loop_id"], follow=True, after_sequence=1)
        telemetry = manager.get_agent_loop_telemetry(loop["loop_id"])

    assert loop["loop_id"] == "loop-external-http"
    assert completed["status"] == "completed"
    assert status["final_output"] == "Agent loop completed for: External loop smoke"
    assert health["status"] == "completed"
    assert health["loop_id"] == "loop-external-http"
    assert health["budget"]["remaining_turns"] == 3
    assert events[0]["type"] == "loop.started"
    assert resumed_events == [events[1]]
    assert stream_events == [events[1]]
    assert telemetry["schema_version"] == "agent-loop-telemetry/1.0"
    assert telemetry["latest_sequence"] == 2
    assert ("POST", "/loops") in server.requests
    assert ("POST", "/loops/loop-external-http/run") in server.requests
    assert ("GET", "/loops/loop-external-http/health") in server.requests
    assert ("GET", "/loops/loop-external-http/events?after_sequence=1") in server.requests
    assert ("GET", "/loops/loop-external-http/events/stream?follow=true&after_sequence=1") in server.requests
    assert ("GET", "/loops/loop-external-http/telemetry") in server.requests


def test_external_http_get_wraps_http_errors(monkeypatch, tmp_path):
    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            endpoint="http://127.0.0.1:9",
            registry_path=tmp_path / "tasks.json",
            auto_run=False,
        )
    )
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["accept"] = request.get_header("Accept")
        raise orchestrator_plugin.urllib.error.HTTPError(
            request.full_url,
            404,
            "Not Found",
            hdrs={},
            fp=io.BytesIO(b'{"error":"not_found"}'),
        )

    monkeypatch.setattr(orchestrator_plugin.urllib.request, "urlopen", fake_urlopen)

    try:
        manager._http_get("/loops/missing")
    except orchestrator_plugin.OrchestratorPluginHTTPError as exc:
        assert "HTTP 404" in str(exc)
        assert exc.status_code == 404
        assert exc.detail == '{"error":"not_found"}'
    else:
        raise AssertionError("_http_get should wrap HTTPError as OrchestratorPluginError")

    assert captured == {
        "url": "http://127.0.0.1:9/loops/missing",
        "method": "GET",
        "accept": "application/json",
    }


def test_external_cli_agent_loop_start_passes_policy_and_metadata(monkeypatch, tmp_path):
    captured = {}
    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command=str(tmp_path / "across-orchestrator"),
            registry_path=tmp_path / "tasks.json",
            auto_run=False,
        )
    )
    manager._transport = "cli"
    monkeypatch.setattr(manager, "_ensure_external", lambda: None)

    def fake_cli_json(args):
        captured["args"] = args
        return {"loop_id": "loop-cli", "status": "pending"}

    monkeypatch.setattr(manager, "_cli_json", fake_cli_json)

    loop = manager.start_agent_loop(
        goal="CLI loop smoke",
        project_dir=str(tmp_path / "project"),
        memory_policy={"read": False, "writeCandidates": False},
        approval_policy={"requireApprovalFor": ["task_dispatch"]},
        metadata={"scenario": "cli-fallback"},
    )

    assert loop["loop_id"] == "loop-cli"
    args = captured["args"]
    assert "--memory-policy-json" in args
    assert json.loads(args[args.index("--memory-policy-json") + 1]) == {"read": False, "writeCandidates": False}
    assert "--approval-policy-json" in args
    assert json.loads(args[args.index("--approval-policy-json") + 1]) == {"requireApprovalFor": ["task_dispatch"]}
    assert "--metadata-json" in args
    assert json.loads(args[args.index("--metadata-json") + 1]) == {"scenario": "cli-fallback"}
    assert args.count("--require-approval-for") == 1


def test_external_cli_agent_loop_control_actions(monkeypatch, tmp_path):
    captured = []
    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command=str(tmp_path / "across-orchestrator"),
            registry_path=tmp_path / "tasks.json",
            auto_run=False,
        )
    )
    manager._transport = "cli"
    monkeypatch.setattr(manager, "_ensure_external", lambda: None)

    def fake_cli_json(args):
        captured.append(args)
        return {"loop_id": "loop-cli", "status": "ok"}

    monkeypatch.setattr(manager, "_cli_json", fake_cli_json)

    manager.cancel_agent_loop("loop-cli", reason="operator cancelled")
    manager.reject_agent_loop_action("loop-cli", "action-cli", reason="operator rejected")
    manager.retry_agent_loop_step("loop-cli", "step-cli")
    manager.get_agent_loop_health("loop-cli")
    manager.get_agent_loop_events("loop-cli", after_sequence=7)
    manager.get_agent_loop_telemetry("loop-cli")

    assert captured[0] == ["loop-cancel", "loop-cli", "--reason", "operator cancelled", "--json"]
    assert captured[1] == ["loop-reject", "loop-cli", "action-cli", "--reason", "operator rejected", "--json"]
    assert captured[2] == ["loop-retry", "loop-cli", "step-cli", "--json"]
    assert captured[3] == ["loop-health", "loop-cli", "--json"]
    assert captured[4] == ["loop-events", "loop-cli", "--after-sequence", "7", "--json"]
    assert captured[5] == ["loop-telemetry", "loop-cli", "--json"]


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
    stale_source = (
        plugin_home
        / "across-orchestrator"
        / "source"
        / "src"
        / "across_agents_assistant"
        / "__init__.py"
    )
    stale_pth = plugin_home / "across-orchestrator" / "venv" / "lib" / "python3.11" / "site-packages" / "__editable__.across_orchestrator.pth"
    stale_source.parent.mkdir(parents=True)
    stale_pth.parent.mkdir(parents=True)
    stale_source.write_text("# stale AAA namespace\n", encoding="utf-8")
    stale_pth.write_text("/Users/example/Documents/projects/across-orchestrator/src\n", encoding="utf-8")
    calls = []

    def fake_run(args, **_kwargs):
        calls.append([str(item) for item in args])
        if str(args[1:3]) == str(["-m", "venv"]):
            assert not stale_source.exists()
            assert not stale_pth.exists()
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
    assert not (plugin_home / "across-orchestrator" / "source").exists()
    assert calls[0][:3] == [installer.python_executable, "-m", "venv"]
    assert calls[1][1:4] == ["-m", "pip", "install"]
    assert calls[2][1:4] == ["-m", "pip", "install"]


def test_orchestrator_plugin_status_rejects_stale_aaa_source_tree(tmp_path):
    plugin_home = tmp_path / "plugins"
    install_dir = plugin_home / "across-orchestrator"
    cli_path = install_dir / "venv" / "bin" / "across-orchestrator"
    marker_path = tmp_path / "cli-was-run"
    stale_source = install_dir / "source" / "src" / "across_agents_assistant" / "__init__.py"
    cli_path.parent.mkdir(parents=True)
    stale_source.parent.mkdir(parents=True)
    cli_path.write_text(
        f"#!/bin/sh\ntouch {marker_path}\nprintf '{{\"name\":\"Across Orchestrator\"}}\\n'\n",
        encoding="utf-8",
    )
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)
    stale_source.write_text("# old AAA runtime namespace\n", encoding="utf-8")

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command="across-orchestrator",
            registry_path=tmp_path / "tasks.json",
            plugin_home=plugin_home,
        )
    )

    status = manager.implementation_status(probe=True)

    assert status["available"] is False
    assert status["command_available"] is False
    assert status["install"]["status"] == "needs_repair"
    assert status["install"]["integrity_ok"] is False
    assert any("stale Across Agents Assistant source" in issue for issue in status["install"]["integrity_issues"])
    assert not marker_path.exists()


def test_orchestrator_plugin_status_rejects_editable_runtime_reference(tmp_path):
    plugin_home = tmp_path / "plugins"
    install_dir = plugin_home / "across-orchestrator"
    cli_path = install_dir / "venv" / "bin" / "across-orchestrator"
    site_packages = install_dir / "venv" / "lib" / "python3.11" / "site-packages"
    marker_path = tmp_path / "cli-was-run"
    cli_path.parent.mkdir(parents=True)
    site_packages.mkdir(parents=True)
    cli_path.write_text(
        f"#!/bin/sh\ntouch {marker_path}\nprintf '{{\"name\":\"Across Orchestrator\"}}\\n'\n",
        encoding="utf-8",
    )
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)
    (site_packages / "__editable__.across_orchestrator.pth").write_text(
        "/Users/example/Documents/projects/across-orchestrator/src\n",
        encoding="utf-8",
    )

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command="across-orchestrator",
            registry_path=tmp_path / "tasks.json",
            plugin_home=plugin_home,
        )
    )

    status = manager.implementation_status(probe=True)

    assert status["available"] is False
    assert status["command_available"] is False
    assert status["install"]["status"] == "needs_repair"
    assert status["install"]["integrity_ok"] is False
    assert "needs repair" in status["error"]
    assert not marker_path.exists()


def test_orchestrator_command_override_rejects_protected_user_directory(monkeypatch, tmp_path):
    protected_root = tmp_path / "Documents"
    cli_path = protected_root / "projects" / "across-orchestrator" / "bin" / "across-orchestrator"
    cli_path.parent.mkdir(parents=True)
    cli_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(
        orchestrator_plugin,
        "_protected_user_reference_roots",
        lambda: [protected_root],
    )

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command=str(cli_path),
            registry_path=tmp_path / "tasks.json",
            plugin_home=tmp_path / "plugins",
        )
    )

    status = manager.implementation_status(probe=False)

    assert status["available"] is False
    assert status["command_available"] is False
    assert status["error"] == "across-orchestrator not found"


def test_orchestrator_plugin_status_reports_actual_wheel_install_source(tmp_path):
    plugin_home = tmp_path / "plugins"
    install_dir = plugin_home / "across-orchestrator"
    cli_path = install_dir / "venv" / "bin" / "across-orchestrator"
    site_packages = install_dir / "venv" / "lib" / "python3.11" / "site-packages"
    dist_info = site_packages / "across_orchestrator-0.6.1.dist-info"
    package_path = install_dir / "packages" / "across_orchestrator-0.6.1-py3-none-any.whl"
    cli_path.parent.mkdir(parents=True)
    dist_info.mkdir(parents=True)
    package_path.parent.mkdir(parents=True)
    cli_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)
    package_path.write_text("wheel", encoding="utf-8")
    (dist_info / "direct_url.json").write_text(
        json.dumps({"url": package_path.as_uri(), "archive_info": {"hash": "sha256=abc"}}),
        encoding="utf-8",
    )

    installer = OrchestratorPluginInstaller(
        plugin_home=plugin_home,
        source="git+https://github.com/fantasyce/across-orchestrator.git",
    )

    status = installer.status()

    assert status["installed"] is True
    assert status["source"] == package_path.as_uri()
    assert "github.com/fantasyce/across-orchestrator" not in status["source"]


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


def test_python_resolver_skips_unsupported_python314(monkeypatch, tmp_path):
    python314 = tmp_path / "python3.14"
    python314.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python314.chmod(python314.stat().st_mode | stat.S_IXUSR)
    python311 = tmp_path / "python3.11"
    python311.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python311.chmod(python311.stat().st_mode | stat.S_IXUSR)

    def fake_which(name, path=None):
        return {
            "python3.14": str(python314),
            "python3.11": str(python311),
            "python3": str(python314),
        }.get(name)

    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_PYTHON", raising=False)
    monkeypatch.setattr(orchestrator_plugin.sys, "frozen", True, raising=False)
    monkeypatch.setattr(orchestrator_plugin.shutil, "which", fake_which)

    assert orchestrator_plugin._resolve_python_executable() == str(python311)


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
        task = manager.submit_release_e2e_task(
            project_dir=str(tmp_path / "project"),
            run_label="unit",
            allowed_subtask_agents=["openclaw", "deepseek"],
        )
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
    assert server.last_submit["allowedSubtaskAgents"] == ["openclaw", "deepseek"]


def test_external_http_runtime_forwards_declared_agent_adapters(tmp_path):
    agent_adapters = {
        "claude": {
            "type": "command",
            "command": ["python3", "-m", "across_agents_assistant.orchestrator_agent_adapter", "--agent", "claude"],
        },
        "hermes": {
            "type": "command",
            "command": ["python3", "-m", "across_agents_assistant.orchestrator_agent_adapter", "--agent", "hermes"],
        },
    }
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

        manager.implementation_status()
        task = manager.submit_task(
            goal="Build with host-provided agents",
            project_dir=str(tmp_path / "project"),
            deliverables=["README.md"],
            agent="claude",
            subtasks=[{"id": "stage-1", "path": "README.md", "agent": "hermes"}],
            agent_adapters=agent_adapters,
        )

    assert task["task_id"] == "task-external-http"
    assert server.last_submit["agentAdapters"] == agent_adapters


def test_external_app_task_artifacts_include_client_file_metadata(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "README.md").write_text("hello\n", encoding="utf-8")
    task = _external_task("task-external-artifacts", str(project_dir), "completed")
    evidence = _external_evidence(task["task_id"], task["project_root"])
    evidence["artifacts"][0] = {
        "path": "README.md",
        "present": True,
        "size": 6,
        "sha256": "c" * 64,
    }

    app_task = external_task_to_app_info(task, evidence)
    artifact = next(item for item in app_task["artifacts"] if item["name"] == "README.md")

    assert artifact["id"] == "external-README.md"
    assert artifact["file_name"] == "README.md"
    assert artifact["file_path"].endswith("README.md")
    assert artifact["content_ref"] == artifact["file_path"]
    assert artifact["normalized_content_ref"] == artifact["file_path"]
    assert artifact["file_size"] == "6 B"
    assert artifact["size"] == 6


def test_external_acceptance_record_is_stable_without_task_timestamps(tmp_path):
    task = _external_task("task-external-stable-acceptance", str(tmp_path / "project"), "completed")
    task.pop("created_at")
    task.pop("updated_at")
    evidence = _external_evidence(task["task_id"], task["project_root"])
    evidence["artifacts"].append(dict(evidence["artifacts"][0]))

    app_task = external_task_to_app_info(task, evidence)
    record = app_task["acceptance_records"][0]

    assert record["created_at"] is None
    assert record["root_cause_artifact_ids"]
    assert len(record["root_cause_artifact_ids"]) == len(set(record["root_cause_artifact_ids"]))
    assert record["decision"] == "approve"


def test_external_expected_artifacts_compute_size_from_project_file(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "README.md").write_text("hello\n", encoding="utf-8")
    task = _external_task("task-external-expected-artifacts", str(project_dir), "pending")
    task["contract"]["requiredArtifacts"] = ["README.md"]

    app_task = external_task_to_app_info(task)
    artifact = app_task["artifacts"][0]

    assert artifact["name"] == "README.md"
    assert artifact["file_name"] == "README.md"
    assert artifact["file_path"].endswith("README.md")
    assert artifact["file_size"] == "6 B"
    assert artifact["status"] == "expected"


def test_external_generic_artifact_task_quality_does_not_require_release_probes(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "README.md").write_text("hello\n", encoding="utf-8")
    task = _external_task("task-generic-artifact", str(project_dir), "completed")
    task["agent"] = "demo"
    task["subtasks"] = [{**task["subtasks"][0], "agent": "demo", "path": "README.md"}]
    task["contract"] = {
        "contractVersion": "0.1",
        "goal": "Create README.md",
        "qualityGates": ["required_artifacts_present", "no_artifacts_outside_project"],
        "requiredArtifacts": ["README.md"],
    }
    task["metadata"] = {
        "task_types": ["artifact"],
        "delivery_mode": "artifact",
    }

    app_task = external_task_to_app_info(task)

    assert app_task["quality_health"]["delivery_quality"] == "passed"
    assert app_task["delivery_report"]["status"] == "passed"
    assert app_task["delivery_report"]["checks"] == {"artifact_integrity": True}


def test_external_generic_task_preserves_task_types_in_app_mapping(tmp_path):
    task = _external_task("task-generic-functional", str(tmp_path / "project"), "completed")
    task["contract"].pop("engine", None)
    task["metadata"] = {
        "task_types": ["functional"],
        "delivery_mode": "functional",
    }
    evidence = _external_evidence(task["task_id"], task["project_root"])
    evidence["contract"] = task["contract"]
    evidence.pop("app_grade", None)
    evidence["metadata"] = task["metadata"]
    evidence["quality"] = {
        "status": "passed",
        "gates": {
            "artifact_integrity": True,
            "workspace_hygiene": True,
            "security_privacy": True,
            "agent_mix": True,
            "static_web_smoke": True,
            "browser_e2e": True,
            "api_service": True,
            "cli_generic": True,
        },
    }

    app_task = external_task_to_app_info(task, evidence)

    assert app_task["task_types"] == ["functional"]
    assert app_task["delivery_mode"] == "functional"
    assert app_task["delivery_report"]["status"] == "passed"


def test_external_app_grade_mapping_migrates_legacy_role_agents(tmp_path):
    task = _external_task("task-legacy-role-agents", str(tmp_path / "project"), "completed")
    task["agent"] = "app-grade"
    task["subtasks"] = [
        {**task["subtasks"][0], "agent": "api-agent"},
        {**task["subtasks"][1], "agent": "html-agent"},
    ]

    app_task = external_task_to_app_info(task)

    assert app_task["owner_agent"] == "openclaw"
    assert app_task["allowed_subtask_agents"] == ["hermes", "openclaw"]
    assert [item["agent_id"] for item in app_task["subtasks"]] == ["openclaw", "hermes"]


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


def test_external_cli_runtime_preserves_strict_dependency_plan(tmp_path):
    task_id = "task-external-cli-plan"
    project_dir = str(tmp_path / "project")
    calls_path = tmp_path / "calls.jsonl"
    cli_path = tmp_path / "across-orchestrator"
    cli_path.write_text(
        f"""#!/usr/bin/env python3
import json, pathlib, sys
task_pending = json.loads({json.dumps(_external_task(task_id, project_dir, "pending"))!r})
calls = pathlib.Path({str(calls_path)!r})
calls.parent.mkdir(parents=True, exist_ok=True)
with calls.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
cmd = sys.argv[1]
if cmd == "agent-card":
    print(json.dumps({{"name": "Across Orchestrator", "version": "0.2.0"}}))
elif cmd == "submit":
    print(json.dumps(task_pending))
else:
    print(json.dumps({{"error": "unsupported"}}))
    sys.exit(2)
""",
        encoding="utf-8",
    )
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)
    subtasks = [
        {
            "id": "stage-design",
            "description": "Create release design note",
            "path": "README.md",
            "agent": "openclaw",
            "wave": 1,
        },
        {
            "id": "stage-build",
            "description": "Build after release design note",
            "path": "web/index.html",
            "agent": "hermes",
            "wave": 2,
            "dependencies": ["stage-design"],
        },
    ]
    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            endpoint=None,
            command=str(cli_path),
            registry_path=tmp_path / "tasks.json",
            auto_run=False,
        )
    )

    manager.implementation_status()
    agent_adapters = {
        "openclaw": {
            "type": "command",
            "command": ["python3", "-m", "across_agents_assistant.orchestrator_agent_adapter", "--agent", "openclaw"],
        },
        "hermes": {
            "type": "command",
            "command": ["python3", "-m", "across_agents_assistant.orchestrator_agent_adapter", "--agent", "hermes"],
        },
    }
    task = manager.submit_task(
        goal="Build a serial validation chain",
        project_dir=project_dir,
        deliverables=["README.md", "web/index.html"],
        agent="openclaw",
        subtasks=subtasks,
        strict_dependency=True,
        task_types=["artifact"],
        agent_adapters=agent_adapters,
    )
    calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
    submit_call = next(call for call in calls if call and call[0] == "submit")

    assert task["task_id"] == task_id
    assert "--strict-dependency" in submit_call
    assert "--subtasks-json" in submit_call
    assert "--agent-adapters-json" in submit_call
    encoded_subtasks = submit_call[submit_call.index("--subtasks-json") + 1]
    assert json.loads(encoded_subtasks) == subtasks
    encoded_agent_adapters = submit_call[submit_call.index("--agent-adapters-json") + 1]
    assert json.loads(encoded_agent_adapters) == agent_adapters
    assert ["--task-type", "artifact"] == submit_call[
        submit_call.index("--task-type"):submit_call.index("--task-type") + 2
    ]

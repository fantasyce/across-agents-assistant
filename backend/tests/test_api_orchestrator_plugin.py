import json
import os
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app
from across_agents_assistant.task_review.release_e2e import RELEASE_E2E_SCENARIO_ID


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
        self.loop_id = "loop-api-external"
        self.loop_action_id = "action-api-external"
        self.status = "pending"
        self.loop_status = "pending"
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
                self.send_header("Cache-Control", "no-cache")
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
                    self._json(_task(owner.task_id, owner.project_dir, owner.status))
                    return
                if self.path == f"/tasks/{owner.task_id}/evidence-bundle":
                    self._json(_evidence(owner.task_id, owner.project_dir))
                    return
                if self.path == f"/tasks/{owner.task_id}/quality-benchmark":
                    self._json({"status": "passed"})
                    return
                if self.path == f"/tasks/{owner.task_id}/events":
                    self._json([
                        {
                            "event_id": "task-event-api-1",
                            "sequence": 1,
                            "type": "task.completed",
                            "task_id": owner.task_id,
                            "loop_id": owner.loop_id,
                            "correlation_id": f"loop:{owner.loop_id}",
                        }
                    ])
                    return
                if self.path == f"/loops/{owner.loop_id}":
                    self._json(owner._loop_payload(owner.loop_status))
                    return
                if self.path == f"/loops/{owner.loop_id}/health":
                    self._json(owner._loop_health_payload(owner.loop_status))
                    return
                if self.path == f"/loops/{owner.loop_id}/evidence-summary":
                    self._json(owner._loop_evidence_summary_payload(owner.loop_status))
                    return
                if self.path == f"/loops/{owner.loop_id}/telemetry":
                    self._json(owner._loop_telemetry_payload(owner.loop_status))
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
                if self.path == "/loops":
                    owner.last_loop_submit = payload
                    self._json(owner._loop_payload("pending"), 201)
                    return
                if self.path == f"/loops/{owner.loop_id}/run":
                    if (owner.last_loop_submit.get("approvalPolicy") or {}).get("requireApprovalFor"):
                        owner.loop_status = "awaiting_approval"
                    else:
                        owner.loop_status = "completed"
                    self._json(owner._loop_payload(owner.loop_status))
                    return
                if self.path == f"/loops/{owner.loop_id}/actions/{owner.loop_action_id}/approve":
                    owner.loop_status = "running"
                    self._json(owner._loop_payload("running", approved=True))
                    return
                if self.path == f"/loops/{owner.loop_id}/actions/{owner.loop_action_id}/reject":
                    owner.loop_status = "stopped"
                    self._json(owner._loop_payload("stopped", rejected=True))
                    return
                if self.path == f"/loops/{owner.loop_id}/cancel":
                    owner.loop_status = "cancelled"
                    self._json(owner._loop_payload("cancelled"))
                    return
                if self.path == f"/loops/{owner.loop_id}/steps/step-api-quality/retry":
                    owner.loop_status = "running"
                    self._json(owner._loop_payload("running"))
                    return
                self._json({"error": "not_found"}, 404)

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

    def _loop_payload(self, status: str, approved: bool = False, rejected: bool = False) -> dict:
        if status == "awaiting_approval":
            steps = [
                {"action": {"type": "memory_search"}},
                {
                    "status": "waiting_approval",
                    "action": {
                        "action_id": self.loop_action_id,
                        "type": "task_dispatch",
                        "requires_approval": True,
                        "approval_status": "pending",
                    },
                },
            ]
        elif rejected:
            steps = [
                {"action": {"type": "memory_search"}},
                {
                    "status": "rejected",
                    "action": {
                        "action_id": self.loop_action_id,
                        "type": "task_dispatch",
                        "requires_approval": True,
                        "approval_status": "rejected",
                    },
                },
            ]
        elif approved:
            steps = [
                {"action": {"type": "memory_search"}},
                {
                    "status": "completed",
                    "action": {
                        "action_id": self.loop_action_id,
                        "type": "task_dispatch",
                        "requires_approval": True,
                        "approval_status": "approved",
                    },
                },
            ]
        else:
            steps = [
                {"action": {"type": "memory_search"}},
                {"action": {"type": "task_dispatch"}},
                {"action": {"type": "quality_gate"}},
                {"action": {"type": "memory_write_candidate"}},
                {"action": {"type": "final_output"}},
            ] if status == "completed" else []
        return {
            "loop_id": self.loop_id,
            "goal": "API loop smoke",
            "project_root": self.project_dir,
            "status": status,
            "agent": "owner",
            "turn_count": 5 if status == "completed" else len(steps),
            "checkpoint_count": 5 if status == "completed" else max(0, len(steps) - 1),
            "memory_policy": {"provider": "across-context", "read": True, "writeCandidates": True},
            "approval_policy": self.last_loop_submit.get("approvalPolicy") or {"requireApprovalFor": []},
            "steps": steps,
            "final_output": "Agent loop completed for: API loop smoke" if status == "completed" else None,
            "error": "approval_rejected" if rejected else None,
        }

    def _loop_health_payload(self, status: str) -> dict:
        awaiting_approval = status == "awaiting_approval"
        cancelled = status == "cancelled"
        return {
            "schema_version": "0.1",
            "loop_id": self.loop_id,
            "status": status,
            "current_action_type": "task_dispatch" if awaiting_approval else None,
            "current_step_id": "step-api-dispatch" if awaiting_approval else None,
            "pending_approval": {
                "step_id": "step-api-dispatch",
                "action_id": self.loop_action_id,
                "action_type": "task_dispatch",
                "title": "Dispatch work through host adapter",
                "approval_status": "pending",
            } if awaiting_approval else None,
            "lease": {"active": False, "lease_seconds": 300.0, "heartbeat_at": 1_700_000_001.0},
            "detached_dispatch_count": 0,
            "recent_failure_types": {},
            "executable_actions": ["approve", "reject", "cancel", "retry"] if awaiting_approval else [],
            "cancellation_requested": cancelled,
            "cancellation_category": "user_requested" if cancelled else None,
            "cancel_ack_pending": False,
            "budget": {
                "max_turns_per_loop": 8,
                "turns_used": 5 if status == "completed" else 0,
                "turns_remaining": 3 if status == "completed" else 8,
            },
        }

    def _loop_evidence_summary_payload(self, status: str) -> dict:
        return {
            "schema_version": "0.1",
            "loop_id": self.loop_id,
            "status": status,
            "agent": "owner",
            "event_audit": {
                "event_count": 6,
                "sequence_contiguous": True,
                "event_id_coverage": True,
                "correlation_id_coverage": True,
            },
            "routing": {
                "schema_version": "agent-loop-routing/1.0",
                "routed_action_count": 1,
                "non_default_route_count": 1,
                "capability_hint_route_count": 1,
                "outcomes": [
                    {
                        "action_type": "task_dispatch",
                        "selected_agent": "builder",
                        "source": "metadata.agentCapabilityHints.preferred.task_dispatch",
                        "capability_hint": "implementation",
                        "reason": "preferred capability hint matched task_dispatch",
                        "alternatives": [
                            {"agent_id": "owner", "selected": False, "reason": "fallback owner"},
                            {"agent_id": "builder", "selected": True, "reason": "implementation hint"},
                        ],
                    }
                ],
            },
            "recovery": {"decision_count": 1, "applied_count": 1, "blocked_count": 0, "decisions": []},
            "memory_candidates": {"candidate_count": 1, "candidates": []},
            "cancellation": {
                "requested": status == "cancelled",
                "category": "user_requested" if status == "cancelled" else None,
                "reason": "operator cancelled" if status == "cancelled" else None,
            },
            "host_release_evidence": {
                "schema_version": "0.1",
                "readiness": "attention",
                "loop_status": status,
                "checks": [
                    {"id": "event_audit", "status": "passed", "summary": "6 events complete."},
                    {
                        "id": "memory_candidates",
                        "status": "attention",
                        "summary": "1 structured memory candidate is pending host review.",
                        "candidate_count": 1,
                    },
                ],
                "risks": [
                    {
                        "id": "memory_review_pending",
                        "severity": "low",
                        "summary": "Structured memory candidates should be reviewed before release.",
                    }
                ],
                "risk_count": 1,
                "next_actions": ["Review pending structured memory candidates in Across Context."],
            },
            "budget": {
                "max_turns_per_loop": 8,
                "turns_used": 5 if status == "completed" else 0,
                "turns_remaining": 3 if status == "completed" else 8,
            },
        }

    def _loop_events(self) -> list[dict]:
        return [
            {
                "event_id": "loop-event-api-1",
                "sequence": 1,
                "type": "loop.started",
                "loop_id": self.loop_id,
                "correlation_id": f"loop:{self.loop_id}",
                "payload": {"status": "running"},
            },
            {
                "event_id": "loop-event-api-2",
                "sequence": 2,
                "type": "loop.completed",
                "loop_id": self.loop_id,
                "correlation_id": f"loop:{self.loop_id}",
                "payload": {
                    "status": "completed",
                    "traceback": "Traceback (most recent call last):\n  File '/private/path.py'",
                },
            },
        ]

    def _loop_telemetry_payload(self, status: str) -> dict:
        return {
            "schema_version": "agent-loop-telemetry/1.0",
            "loop_id": self.loop_id,
            "status": status,
            "summary": {
                "event_count": 2,
                "turn_count": 5 if status == "completed" else 0,
                "memory_candidate_count": 1,
            },
            "metrics": [
                {"id": "events.total", "value": 2},
                {"id": "turns.completed", "value": 5 if status == "completed" else 0},
            ],
            "latest_sequence": 2,
            "budget": {
                "max_turns_per_loop": 8,
                "turns_used": 5 if status == "completed" else 0,
                "turns_remaining": 3 if status == "completed" else 8,
            },
        }


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
    assert run["quality_health"]["delivery_quality"] == "passed"
    assert run["delivery_report"]["status"] == "passed"
    assert run["acceptance_records"][0]["level"] == "task"
    assert run["acceptance_records"][0]["deterministic_passed"] is True
    assert run["acceptance_records"][0]["root_cause_artifact_ids"]
    assert status["status"] == "completed"
    assert status["quality_health"]["delivery_quality"] == "passed"
    assert evidence["benchmark"]["status"] == "passed"
    assert evidence["audit"]["expected_files"] == REQUIRED_FILES
    assert ("POST", "/release-e2e") in server.requests
    assert ("POST", "/tasks/task-api-external/run") in server.requests
    assert ("GET", "/tasks/task-api-external/evidence-bundle") in server.requests


def test_external_orchestrator_tasks_reject_legacy_lifecycle_controls(monkeypatch, tmp_path):
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
                "run_label": "legacy-controls",
            },
        )
        assert created.status_code == 200
        task_id = created.json()["task_id"]

        responses = [
            client.post(f"/api/tasks/{task_id}/pause"),
            client.post(f"/api/tasks/{task_id}/resume"),
            client.post(f"/api/tasks/{task_id}/cancel"),
        ]

    assert [response.status_code for response in responses] == [409, 409, 409]
    assert all("external Across Orchestrator" in response.json()["detail"] for response in responses)
    assert ("POST", f"/tasks/{task_id}/pause") not in server.requests
    assert ("POST", f"/tasks/{task_id}/resume") not in server.requests
    assert ("POST", f"/tasks/{task_id}/cancel") not in server.requests


def test_api_proxies_external_agent_loop_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", "external")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_AUTORUN", "0")

    with FakeHTTPOrchestrator(str(tmp_path / "project")) as server:
        monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", server.endpoint)
        _reset_plugin_manager()
        client = TestClient(app)

        created = client.post(
            "/api/orchestrator/loops",
            json={
                "goal": "API loop smoke",
                "project_dir": str(tmp_path / "project"),
                "agent": "owner",
                "max_turns": 8,
                "memory_policy": {"read": False, "writeCandidates": False},
                "metadata": {"scenario": "aaa-api"},
            },
        )
        assert created.status_code == 200
        loop_id = created.json()["loop_id"]

        run = client.post(f"/api/orchestrator/loops/{loop_id}/run")
        status = client.get(f"/api/orchestrator/loops/{loop_id}")
        health = client.get(f"/api/orchestrator/loops/{loop_id}/health")
        summary = client.get(f"/api/orchestrator/loops/{loop_id}/evidence-summary")
        telemetry = client.get(f"/api/orchestrator/loops/{loop_id}/telemetry")
        events = client.get(f"/api/orchestrator/loops/{loop_id}/events")
        resumed_events = client.get(f"/api/orchestrator/loops/{loop_id}/events", params={"after_sequence": "1"})
        stream = client.get(f"/api/orchestrator/loops/{loop_id}/events/stream", params={"follow": "true"})
        resumed_stream = client.get(
            f"/api/orchestrator/loops/{loop_id}/events/stream",
            params={"follow": "true", "after_sequence": "1"},
        )
        snapshot_stream = client.get(f"/api/orchestrator/loops/{loop_id}/events/stream", params={"follow": "false"})

    assert loop_id == "loop-api-external"
    run_body = run.json()
    assert run_body["status"] == "completed"
    assert run_body["health"]["status"] == "completed"
    assert run_body["evidence_summary"]["schema_version"] == "0.1"
    assert run_body["evidence_summary"]["event_audit"]["sequence_contiguous"] is True
    assert run_body["evidence_summary"]["host_release_evidence"]["readiness"] == "attention"
    assert run_body["telemetry"]["schema_version"] == "agent-loop-telemetry/1.0"
    assert run_body["telemetry"]["latest_sequence"] == 2
    assert status.json()["final_output"] == "Agent loop completed for: API loop smoke"
    assert health.json()["status"] == "completed"
    assert health.json()["loop_id"] == "loop-api-external"
    assert health.json()["budget"]["turns_remaining"] == 3
    assert summary.json()["schema_version"] == "0.1"
    assert summary.json()["routing"]["capability_hint_route_count"] == 1
    assert summary.json()["routing"]["outcomes"][0]["alternatives"][1]["selected"] is True
    assert summary.json()["event_audit"]["sequence_contiguous"] is True
    assert summary.json()["host_release_evidence"]["risk_count"] == 1
    assert telemetry.json()["schema_version"] == "agent-loop-telemetry/1.0"
    assert telemetry.json()["summary"]["memory_candidate_count"] == 1
    assert events.json()[0]["type"] == "loop.started"
    assert events.json()[1]["type"] == "loop.completed"
    assert events.json()[1]["event_id"] == "loop-event-api-2"
    assert events.json()[1]["sequence"] == 2
    assert events.json()[1]["correlation_id"] == "loop:loop-api-external"
    assert [event["sequence"] for event in resumed_events.json()] == [2]
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: loop.completed" in stream.text
    assert '"event_id": "loop-event-api-2"' in stream.text
    assert '"correlation_id": "loop:loop-api-external"' in stream.text
    assert "Internal operation failed" in stream.text
    assert "Traceback" not in stream.text
    assert resumed_stream.status_code == 200
    assert "event: loop.started" not in resumed_stream.text
    assert "event: loop.completed" in resumed_stream.text
    assert snapshot_stream.status_code == 200
    assert "event: loop.completed" in snapshot_stream.text
    assert ("POST", "/loops") in server.requests
    assert server.requests.count(("GET", f"/loops/{server.loop_id}/health")) >= 2
    assert server.requests.count(("GET", f"/loops/{server.loop_id}/evidence-summary")) >= 2
    assert server.requests.count(("GET", f"/loops/{server.loop_id}/telemetry")) >= 2
    assert server.requests.count(("GET", f"/loops/{server.loop_id}/events")) >= 2
    assert ("GET", f"/loops/{server.loop_id}/events?after_sequence=1") in server.requests
    assert server.last_loop_submit["memoryPolicy"] == {"read": False, "writeCandidates": False}
    assert server.last_loop_submit["metadata"] == {"scenario": "aaa-api"}


def test_api_proxies_external_agent_loop_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", "external")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_AUTORUN", "0")

    with FakeHTTPOrchestrator(str(tmp_path / "project")) as server:
        monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", server.endpoint)
        _reset_plugin_manager()
        client = TestClient(app)

        created = client.post(
            "/api/orchestrator/loops",
            json={
                "goal": "API loop smoke",
                "project_dir": str(tmp_path / "project"),
                "approval_policy": {"requireApprovalFor": ["task_dispatch"]},
            },
        )
        loop_id = created.json()["loop_id"]
        waiting = client.post(f"/api/orchestrator/loops/{loop_id}/run").json()
        action_id = waiting["steps"][-1]["action"]["action_id"]

        approved = client.post(f"/api/orchestrator/loops/{loop_id}/actions/{action_id}/approve")

    approved_body = approved.json()
    assert approved.status_code == 200
    assert approved_body["steps"][-1]["action"]["approval_status"] == "approved"
    assert approved_body["health"]["status"] == "running"
    assert approved_body["evidence_summary"]["status"] == "running"
    assert approved_body["telemetry"]["status"] == "running"
    assert ("POST", f"/loops/{server.loop_id}/actions/{server.loop_action_id}/approve") in server.requests
    assert ("GET", f"/loops/{server.loop_id}/health") in server.requests
    assert ("GET", f"/loops/{server.loop_id}/evidence-summary") in server.requests
    assert ("GET", f"/loops/{server.loop_id}/telemetry") in server.requests


def test_api_proxies_external_agent_loop_control_actions(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", "external")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_AUTORUN", "0")

    with FakeHTTPOrchestrator(str(tmp_path / "project")) as server:
        monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", server.endpoint)
        _reset_plugin_manager()
        client = TestClient(app)

        created = client.post(
            "/api/orchestrator/loops",
            json={
                "goal": "API loop controls",
                "project_dir": str(tmp_path / "project"),
                "approval_policy": {"requireApprovalFor": ["task_dispatch"]},
            },
        )
        loop_id = created.json()["loop_id"]
        waiting = client.post(f"/api/orchestrator/loops/{loop_id}/run").json()
        action_id = waiting["steps"][-1]["action"]["action_id"]

        rejected = client.post(
            f"/api/orchestrator/loops/{loop_id}/actions/{action_id}/reject",
            json={"reason": "operator rejected"},
        )
        cancel_created = client.post(
            "/api/orchestrator/loops",
            json={
                "goal": "API loop cancel",
                "project_dir": str(tmp_path / "project"),
            },
        )
        cancel_loop_id = cancel_created.json()["loop_id"]
        cancelled = client.post(
            f"/api/orchestrator/loops/{cancel_loop_id}/cancel",
            json={"reason": "operator cancelled"},
        )
        retry = client.post(f"/api/orchestrator/loops/{loop_id}/steps/step-api-quality/retry")

    rejected_body = rejected.json()
    cancelled_body = cancelled.json()
    retry_body = retry.json()
    assert rejected.status_code == 200
    assert rejected_body["steps"][-1]["action"]["approval_status"] == "rejected"
    assert rejected_body["health"]["status"] == "stopped"
    assert rejected_body["evidence_summary"]["status"] == "stopped"
    assert rejected_body["telemetry"]["status"] == "stopped"
    assert cancelled.status_code == 200
    assert cancelled_body["status"] == "cancelled"
    assert cancelled_body["health"]["cancellation_category"] == "user_requested"
    assert cancelled_body["evidence_summary"]["cancellation"]["category"] == "user_requested"
    assert cancelled_body["telemetry"]["status"] == "cancelled"
    assert retry.status_code == 200
    assert retry_body["status"] == "running"
    assert retry_body["health"]["status"] == "running"
    assert retry_body["evidence_summary"]["status"] == "running"
    assert retry_body["telemetry"]["status"] == "running"
    assert ("POST", f"/loops/{server.loop_id}/actions/{server.loop_action_id}/reject") in server.requests
    assert ("POST", f"/loops/{server.loop_id}/cancel") in server.requests
    assert ("POST", f"/loops/{server.loop_id}/steps/step-api-quality/retry") in server.requests
    assert server.requests.count(("GET", f"/loops/{server.loop_id}/health")) >= 4
    assert server.requests.count(("GET", f"/loops/{server.loop_id}/evidence-summary")) >= 4
    assert server.requests.count(("GET", f"/loops/{server.loop_id}/telemetry")) >= 4


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


def test_external_agent_loop_event_stream_snapshot_does_not_follow(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.event_calls = 0

        def get_agent_loop_events(self, loop_id, after_sequence=None):
            self.event_calls += 1
            sequence = int(after_sequence or 0) + 1
            return [
                {
                    "event_id": f"event-{self.event_calls}",
                    "sequence": sequence,
                    "type": "loop.step.started",
                    "loop_id": loop_id,
                    "payload": {"status": "running"},
                }
            ]

    fake = FakeManager()
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: fake)

    client = TestClient(app)
    response = client.get("/api/orchestrator/loops/loop-snapshot/events/stream")
    explicit_response = client.get(
        "/api/orchestrator/loops/loop-snapshot/events/stream",
        params={"follow": "false"},
    )

    assert response.status_code == 200
    assert "event: loop.step.started" in response.text
    assert '"event_id": "event-1"' in response.text
    assert explicit_response.status_code == 200
    assert "event: loop.step.started" in explicit_response.text
    assert '"event_id": "event-2"' in explicit_response.text
    assert fake.event_calls == 2


def test_external_agent_loop_event_stream_forwards_resume_cursor(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.calls = []

        def get_agent_loop_events(self, loop_id, after_sequence=None):
            self.calls.append((loop_id, after_sequence))
            return [
                {
                    "event_id": "event-resumed",
                    "sequence": int(after_sequence or 0) + 1,
                    "type": "loop.completed",
                    "loop_id": loop_id,
                    "payload": {"status": "completed"},
                }
            ]

    fake = FakeManager()
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: fake)

    response = TestClient(app).get(
        "/api/orchestrator/loops/loop-resume/events/stream",
        params={"follow": "true", "after_sequence": "5"},
    )

    assert response.status_code == 200
    assert '"sequence": 6' in response.text
    assert fake.calls == [("loop-resume", 5)]


def test_external_agent_loop_health_forwards_orchestrator_404(monkeypatch):
    class FakeManager:
        def get_agent_loop_health(self, loop_id):
            raise api_server.OrchestratorPluginHTTPError(404, '{"error":"not_found"}')

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())

    response = TestClient(app).get("/api/orchestrator/loops/missing-loop/health")

    assert response.status_code == 404
    assert response.json()["detail"] == "External Across Orchestrator resource not found."


def test_external_agent_loop_health_maps_orchestrator_500_to_bad_gateway(monkeypatch):
    class FakeManager:
        def get_agent_loop_health(self, loop_id):
            raise api_server.OrchestratorPluginHTTPError(500, '{"error":"internal_error"}')

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())

    response = TestClient(app).get("/api/orchestrator/loops/broken-loop/health")

    assert response.status_code == 502
    assert response.json()["detail"] == "External Across Orchestrator agent loop health failed. See local backend logs for details."


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

import json

from fastapi.testclient import TestClient

from across_agents_assistant import agent_interop_e2e, api_server, release_verification
from across_agents_assistant.api_server import app


def _startup_report(status: str = "ready"):
    return {
        "schema_version": "1.0",
        "app_version": "0.4.0",
        "generated_at": "2026-05-31T12:00:00Z",
        "status": status,
        "summary": {
            "status": status,
            "passed": 10 if status == "ready" else 8,
            "warnings": 0 if status == "ready" else 1,
            "failed": 0,
            "check_count": 10,
        },
        "paths": {
            "app_home": "/tmp/across",
            "logs_dir": "/tmp/across/logs",
            "run_dir": "/tmp/across/run",
            "tmp_dir": "/tmp/across/tmp",
            "evidence_dir": "/tmp/across/evidence",
            "socket_path": "/tmp/across/run/across-agents.sock",
            "database_path": "/tmp/across/assistant.db",
        },
        "runtime": {
            "pid": 123,
            "started_at": 1.0,
            "uptime_sec": 4.0,
            "known_tasks": 1,
            "persistence_initialized": True,
        },
        "keys": {
            "has_any_key": True,
            "providers": {"deepseek": "configured", "minimax": "not_configured"},
            "readiness_blockers": [],
        },
        "checks": [
            {
                "id": "backend_health",
                "title": "Backend process",
                "status": "passed",
                "detail": "Backend process is serving requests.",
                "remediation": None,
                "metadata": {},
            }
        ],
    }


def _release_e2e_task(task_id: str) -> api_server.TaskInfo:
    expected_files = [
        "README.md",
        "web/index.html",
        "web/styles.css",
        "web/app.js",
        "api/server.mjs",
        "cli/quality-check.mjs",
        "tests/e2e-smoke.mjs",
    ]
    probes = [
        "workspace_hygiene",
        "security_privacy",
        "static_web_smoke",
        "browser_e2e",
        "api_service",
        "cli_generic",
    ]
    probe_results = [
        {"id": f"probe-{probe}", "probe_type": probe, "passed": True, "required": True}
        for probe in probes
    ]
    quality_report = {
        "quality_gate": "passed",
        "final_quality_score": 91,
        "required_failed_count": 0,
        "manual_required_count": 0,
        "required_skipped_count": 0,
    }
    delivery_quality = {
        "delivery_quality": "passed",
        "produced_required": [{"path_hint": path} for path in expected_files],
        "missing_required": [],
        "invalid_required": [],
        "failed_constraints": [],
        "probe_results": probe_results,
        "quality_report": quality_report,
    }
    return api_server.TaskInfo(
        task_id=task_id,
        description="Release E2E scenario: web api cli release candidate",
        status="completed",
        task_types=["functional", "artifact"],
        delivery_mode="composite",
        owner_agent="hermes",
        allowed_subtask_agents=["openclaw", "deepseek"],
        project_dir="/tmp/release-rc",
        subtasks=[],
        progress=1.0,
        created_at=10.0,
        updated_at=20.0,
        last_owner_decision={
            "provider_api_key": "rc-secret-should-not-leak",
            "delivery_quality": delivery_quality,
        },
        quality_health={
            "quality_gate": "passed",
            "delivery_quality": "passed",
            "delivery_quality_report": delivery_quality,
        },
        delivery_report={
            "quality_gate": "passed",
            "final_status": "completed",
            "remediation": {"subtask_count": 1, "active_subtasks": []},
        },
        observability={
            "agent_mix": {
                "actual_agents": ["hermes", "openclaw", "deepseek"],
                "local_agents": ["hermes", "openclaw"],
                "cloud_agents": ["deepseek"],
            }
        },
    )


def _interop_payload(status: str = "passed"):
    failed = 0 if status == "passed" else 1
    passed = 10 if status == "passed" else 9
    return {
        "schema_version": "1.0",
        "status": status,
        "generated_at": "2026-06-25T10:00:00Z",
        "summary": {
            "status": status,
            "passed_count": passed,
            "failed_count": failed,
            "host_target_count": 3,
            "mcp_server_count": 3,
            "protocol_readiness_score": 100 if status == "passed" else 70,
        },
        "endpoint": "/api/agent-interop/e2e",
    }


def _write_gate_evidence(
    report_root,
    gate_id: str,
    *,
    status: str = "passed",
    run_url: str | None = None,
    workspace_dirty: bool | str = False,
):
    report_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "gate_id": gate_id,
        "status": status,
        "source": "github_actions" if gate_id == "github_live_e2e" else "local_script",
        "summary": f"{gate_id} {status}",
        "tier": "all",
        "started_at": "2026-06-20T01:00:00Z",
        "completed_at": "2026-06-20T01:05:00Z",
        "duration_seconds": 300,
        "run_url": run_url,
        "workspace_dirty": workspace_dirty,
    }
    path = report_root / f"{gate_id}-gate-evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _materialize_source_markers(repo_root):
    (repo_root / "backend" / "src" / "across_agents_assistant").mkdir(parents=True, exist_ok=True)
    (repo_root / "macOS-Client").mkdir(parents=True, exist_ok=True)
    (repo_root / "macOS-Client" / "Package.swift").write_text("// package fixture\n", encoding="utf-8")


def _materialize_gate_paths(repo_root):
    _materialize_source_markers(repo_root)
    for definition in release_verification.PRE_RELEASE_GATE_DEFINITIONS:
        for relative_path in definition.get("paths") or []:
            path = repo_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if "." in path.name:
                path.write_text("# gate fixture\n", encoding="utf-8")
            else:
                path.mkdir(parents=True, exist_ok=True)


def test_release_verification_endpoint_writes_ready_report_without_secret_leaks(monkeypatch, tmp_path):
    class FakePersistence:
        def get_task_summaries(self, *, limit=100, offset=0):
            return (
                [
                    {
                        "task_id": "task-old",
                        "description": "Release E2E scenario: older",
                        "status": "completed",
                        "created_at": 1.0,
                        "updated_at": 1.0,
                    },
                    {
                        "task_id": "task-third",
                        "description": "Release E2E scenario: additional recent release candidate",
                        "status": "completed",
                        "created_at": 5.0,
                        "updated_at": 15.0,
                    },
                    {
                        "task_id": "task-rc",
                        "description": "Release E2E scenario: web api cli release candidate",
                        "status": "completed",
                        "created_at": 10.0,
                        "updated_at": 20.0,
                    },
                ],
                2,
            )

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_build_startup_diagnostics", lambda: _startup_report())
    monkeypatch.setattr(api_server, "app_subdir", lambda name: tmp_path / name)
    monkeypatch.setattr(api_server, "_load_task_info_read_only", lambda task_id: _release_e2e_task(task_id))
    monkeypatch.setattr(agent_interop_e2e, "load_agent_interop_e2e_latest", lambda: _interop_payload("passed"))
    monkeypatch.setattr(
        api_server,
        "_repair_task_dispatch_if_possible",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not repair during RC verification")),
    )
    for gate_id in [
        "backend_regression",
        "open_source_check",
        "swift_behavior_checks",
        "swift_package_gate",
        "quality_ci",
        "local_live_e2e",
    ]:
        _write_gate_evidence(tmp_path / "release-reports", gate_id)
    _write_gate_evidence(
        tmp_path / "release-reports",
        "github_live_e2e",
        run_url="https://github.com/fantasyce/across-agents-assistant/actions/runs/123",
    )
    (tmp_path / "release-reports" / "broken-gate-evidence.json").write_text("{not-json", encoding="utf-8")

    response = TestClient(app).post("/api/release/verification")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "ready"
    assert body["startup"]["summary"]["status"] == "ready"
    assert body["release_evaluation"]["release_readiness"] == "ready"
    assert body["release_evaluation"]["evaluated_task_count"] == 3
    assert body["release_evaluation"]["agent_interop_e2e_status"] == "passed"
    assert body["release_evaluation"]["release_evidence_count"] == 4
    assert body["release_evaluation"]["passed_evidence_count"] == 4
    assert body["release_evaluation"]["supplemental_evidence"][0]["kind"] == "host_interop_e2e"
    assert body["latest_release_e2e"]["task_id"] == "release-e2e-latest"
    assert body["latest_release_e2e"]["benchmark"]["status"] == "passed"
    assert body["pre_release_gate_summary"]["required_missing"] == 0
    assert body["pre_release_gate_summary"]["required_manual"] == 0
    assert body["pre_release_gate_summary"]["required_unverified"] == 0
    assert body["pre_release_gate_summary"]["passed"] == 7
    assert body["pre_release_gate_missing_paths"] == []
    assert len(body["pre_release_gates"]) == 7
    assert all(gate["id"].startswith("pre_release_gate_") for gate in body["pre_release_gates"])
    assert all(gate["status"] == "passed" for gate in body["pre_release_gates"])
    assert all(gate["evidence"]["run_url"] is None for gate in body["pre_release_gates"] if gate.get("evidence"))
    assert all(gate["evidence"]["evidence_path"] is None for gate in body["pre_release_gates"] if gate.get("evidence"))
    assert body["pre_release_gate_parse_errors"][0]["evidence_path"] == ""
    assert body["pre_release_gate_parse_errors"][0]["error_type"] == "ParseError"
    assert str(tmp_path) not in json.dumps(body["pre_release_gate_parse_errors"])
    assert body["audit"]["read_only"] is True
    assert body["audit"]["repair_or_resume_triggered"] is False
    assert body["audit"]["secrets_redacted"] is True
    assert body["report_files"]["json_path"] == ""
    assert body["report_files"]["markdown_path"] == ""
    assert (tmp_path / "release-reports").exists()
    markdown_files = sorted((tmp_path / "release-reports").glob("*.md"))
    assert markdown_files
    markdown = markdown_files[-1].read_text()
    assert "task-rc" in markdown
    assert "Pre-Release Gates" in markdown
    assert "Release Evaluation" in markdown
    assert "Agent interop E2E: passed" in markdown
    assert "- host_interop_e2e: passed (10 passed, 0 failed)" in markdown
    assert "Required missing: 0" in markdown
    assert "Required manual: 0" in markdown
    assert "Required unverified: 0" in markdown
    assert "bash scripts/run_live_e2e.sh all" in markdown
    assert "Run URL: https://github.com/fantasyce/across-agents-assistant/actions/runs/123" in markdown
    assert "Gate evidence parse errors:" in markdown
    assert "broken-gate-evidence.json" in markdown
    encoded = json.dumps(body)
    assert "rc-secret-should-not-leak" not in encoded
    assert "api_key" not in encoded.lower()


def test_pre_release_gate_parse_error_uses_public_error_shape(tmp_path):
    evidence_path = tmp_path / "private" / "nested" / "broken-gate-evidence.json"

    parse_error = release_verification._pre_release_gate_parse_error(evidence_path)

    assert parse_error["evidence_path"] == "broken-gate-evidence.json"
    assert parse_error["error_type"] == "ParseError"
    assert parse_error["message"] == "Could not parse pre-release gate evidence; see local report for details."
    assert str(tmp_path) not in json.dumps(parse_error)


def test_pre_release_gate_evidence_preserves_workspace_dirty(tmp_path):
    evidence_path = tmp_path / "quality_ci-gate-evidence.json"
    raw = {
        "schema_version": "1.0",
        "gates": [
            {
                "id": "quality_ci",
                "status": "passed",
                "summary": "quality passed",
                "workspace_dirty": "false",
            },
            {
                "id": "local_live_e2e",
                "status": "passed",
                "summary": "live e2e passed",
                "runner": "scripts/run_live_e2e.sh",
                "orchestrator_command": "across-orchestrator",
                "workspace_dirty": True,
            },
        ],
    }

    normalized = release_verification._normalize_pre_release_gate_evidence(raw, evidence_path=evidence_path)
    gates = release_verification._public_pre_release_gates(
        [
            {"id": "quality_ci", "label": "Quality CI", "source": "github_actions", "status": "passed", "evidence": normalized[0]},
            {
                "id": "local_live_e2e",
                "label": "Local Live E2E",
                "source": "local_script",
                "status": "passed",
                "evidence": normalized[1],
            },
        ]
    )

    gates_by_id = {gate["id"]: gate for gate in gates}
    assert gates_by_id["quality_ci"]["evidence"]["workspace_dirty"] is False
    assert gates_by_id["local_live_e2e"]["evidence"]["workspace_dirty"] is True
    assert gates_by_id["local_live_e2e"]["evidence"]["runner"] == "scripts/run_live_e2e.sh"
    assert gates_by_id["local_live_e2e"]["evidence"]["orchestrator_command"] == "across-orchestrator"


def test_pre_release_gates_do_not_report_source_paths_missing_in_packaged_runtime(tmp_path):
    gates = release_verification._build_pre_release_gates(repo_root=tmp_path / "Packaged.app" / "Resources")

    assert gates
    assert all(gate["status"] != "missing" for gate in gates)
    assert all(gate["source_checkout_available"] is False for gate in gates)
    assert any("attach gate evidence" in gate["detail"] for gate in gates)


def test_release_verification_reports_attention_when_release_e2e_is_missing(monkeypatch, tmp_path):
    class FakePersistence:
        def get_task_summaries(self, *, limit=100, offset=0):
            return ([{"task_id": "task-normal", "description": "ordinary task", "updated_at": 5.0}], 1)

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_build_startup_diagnostics", lambda: _startup_report())
    monkeypatch.setattr(api_server, "app_subdir", lambda name: tmp_path / name)
    monkeypatch.setattr(agent_interop_e2e, "load_agent_interop_e2e_latest", lambda: {})

    response = TestClient(app).post("/api/release/verification")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "attention"
    assert body["latest_release_e2e"] is None
    assert any("Release E2E" in item for item in body["remediations"])
    assert body["report_files"]["markdown_path"] == ""
    assert sorted((tmp_path / "release-reports").glob("*.md"))


def test_release_verification_reports_attention_when_manual_gate_evidence_is_missing(monkeypatch, tmp_path):
    class FakePersistence:
        def get_task_summaries(self, *, limit=100, offset=0):
            return (
                [
                    {
                        "task_id": "task-rc",
                        "description": "Release E2E scenario: web api cli release candidate",
                        "status": "completed",
                        "created_at": 10.0,
                        "updated_at": 20.0,
                    },
                ],
                1,
            )

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _materialize_gate_paths(repo_root)

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_build_startup_diagnostics", lambda: _startup_report())
    monkeypatch.setattr(api_server, "app_subdir", lambda name: tmp_path / name)
    monkeypatch.setattr(api_server, "_load_task_info_read_only", lambda task_id: _release_e2e_task(task_id))
    monkeypatch.setattr(release_verification, "_repository_root", lambda: repo_root)
    monkeypatch.setattr(agent_interop_e2e, "load_agent_interop_e2e_latest", lambda: {})

    response = TestClient(app).post("/api/release/verification")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "attention"
    assert body["pre_release_gate_summary"]["required_missing"] == 0
    assert body["pre_release_gate_summary"]["required_manual"] == 2
    assert any("manual pre-release gates" in item for item in body["remediations"])


def test_release_verification_reports_attention_when_required_gate_is_missing(monkeypatch, tmp_path):
    class FakePersistence:
        def get_task_summaries(self, *, limit=100, offset=0):
            return (
                [
                    {
                        "task_id": "task-rc",
                        "description": "Release E2E scenario: web api cli release candidate",
                        "status": "completed",
                        "created_at": 10.0,
                        "updated_at": 20.0,
                    },
                ],
                1,
            )

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _materialize_source_markers(repo_root)

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_build_startup_diagnostics", lambda: _startup_report())
    monkeypatch.setattr(api_server, "app_subdir", lambda name: tmp_path / name)
    monkeypatch.setattr(api_server, "_load_task_info_read_only", lambda task_id: _release_e2e_task(task_id))
    monkeypatch.setattr(release_verification, "_repository_root", lambda: repo_root)
    monkeypatch.setattr(agent_interop_e2e, "load_agent_interop_e2e_latest", lambda: {})

    response = TestClient(app).post("/api/release/verification")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "attention"
    assert body["pre_release_gate_summary"]["required_missing"] > 0
    assert "scripts/run_live_e2e.sh" in body["pre_release_gate_missing_paths"]
    assert any("pre-release verification gates" in item for item in body["remediations"])
    markdown_files = sorted((tmp_path / "release-reports").glob("*.md"))
    assert markdown_files
    markdown = markdown_files[-1].read_text()
    assert "Required missing: 7" in markdown
    assert "Missing required gate paths:" in markdown
    assert "scripts/run_live_e2e.sh" in markdown


def test_release_verification_evaluation_uses_interop_evidence_without_task_rows(tmp_path):
    report = release_verification._build_release_verification_report(
        write_report=False,
        task_state=None,
        startup_diagnostics=_startup_report(),
        write_report_directory=tmp_path,
        repo_root=tmp_path / "repo",
        agent_interop_e2e=_interop_payload("passed"),
    )

    assert report["status"] == "attention"
    assert report["release_evaluation"]["release_readiness"] == "attention"
    assert report["release_evaluation"]["release_evidence_count"] == 1
    assert report["release_evaluation"]["passed_evidence_count"] == 1
    assert report["release_evaluation"]["agent_interop_e2e_status"] == "passed"
    assert report["release_evaluation"]["supplemental_evidence"][0]["endpoint"] == "/api/autopilot/agent-interop-e2e"
    assert "quality-gated release task evidence" in report["release_evaluation"]["recommendation"]
    assert any("Release E2E" in item for item in report["remediations"])


def test_promotion_assembly_builds_release_evidence_without_writing_report(monkeypatch, tmp_path):
    observed = {}
    payloads = {
        task_id: {
            "task_id": task_id,
            "status": "completed",
            "last_owner_decision": {"delivery_quality": {"quality_gate": "passed"}},
        }
        for task_id in ("task-alpha", "task-zeta")
    }

    def build_report(**kwargs):
        observed.update(kwargs)
        scoped_rows = kwargs["task_state"].get_all_tasks()
        assert [row["task_id"] for row in scoped_rows] == ["task-alpha", "task-zeta"]
        assert [kwargs["task_row_mapper"](row)["task_id"] for row in scoped_rows] == [
            "task-alpha", "task-zeta"
        ]
        return {
            "status": "ready",
            "release_evaluation": {
                "evaluated_task_count": 2,
                "terminal_task_count": 2,
                "passed_task_count": 2,
            },
        }

    monkeypatch.setattr(api_server, "_build_release_verification_report", build_report)
    monkeypatch.setattr(api_server, "_build_startup_diagnostics", lambda: _startup_report())
    monkeypatch.setattr(api_server, "_load_task_info_read_only", lambda task_id: payloads[task_id])

    report = api_server._promotion_release_evidence(["task-alpha", "task-zeta"])

    assert report["task_scope"] == {
        "schema_version": "across-release-task-scope/1.0",
        "task_ids": ["task-alpha", "task-zeta"],
    }
    assert report["release_evaluation"]["task_ids"] == ["task-alpha", "task-zeta"]
    assert observed["write_report"] is False
    assert observed.get("write_report_directory") is None
    assert observed["external_task_rows"] is None

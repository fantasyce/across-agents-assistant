import json

from fastapi.testclient import TestClient

from across_agents_assistant import api_server, release_verification
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
    probes = ["static_web_smoke", "browser_e2e", "api_service", "cli_generic"]
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


def _write_gate_evidence(report_root, gate_id: str, *, status: str = "passed", run_url: str | None = None):
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
    }
    path = report_root / f"{gate_id}-gate-evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _materialize_gate_paths(repo_root):
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
    monkeypatch.setattr(
        api_server,
        "_repair_task_dispatch_if_possible",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not repair during RC verification")),
    )
    _write_gate_evidence(tmp_path / "release-reports", "local_live_e2e")
    _write_gate_evidence(
        tmp_path / "release-reports",
        "github_live_e2e",
        run_url="https://github.com/fantasyce/across-agents-assistant/actions/runs/123",
    )

    response = TestClient(app).post("/api/release/verification")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "ready"
    assert body["startup"]["summary"]["status"] == "ready"
    assert body["latest_release_e2e"]["task_id"] == "task-rc"
    assert body["latest_release_e2e"]["benchmark"]["status"] == "passed"
    assert body["pre_release_gate_summary"]["required_missing"] == 0
    assert body["pre_release_gate_summary"]["required_manual"] == 0
    assert body["pre_release_gate_summary"]["passed"] == 2
    assert body["pre_release_gate_missing_paths"] == []
    assert {gate["id"] for gate in body["pre_release_gates"]} >= {
        "backend_regression",
        "open_source_check",
        "swift_behavior_checks",
        "local_live_e2e",
        "github_live_e2e",
    }
    gates_by_id = {gate["id"]: gate for gate in body["pre_release_gates"]}
    assert gates_by_id["local_live_e2e"]["status"] == "passed"
    assert gates_by_id["github_live_e2e"]["evidence"]["run_url"].endswith("/123")
    assert gates_by_id["github_live_e2e"]["evidence"]["evidence_path"] == "github_live_e2e-gate-evidence.json"
    assert str(tmp_path) not in json.dumps(gates_by_id["github_live_e2e"]["evidence"])
    assert body["audit"]["read_only"] is True
    assert body["audit"]["repair_or_resume_triggered"] is False
    assert body["audit"]["secrets_redacted"] is True
    assert body["report_files"]["json_path"].endswith(".json")
    assert body["report_files"]["markdown_path"].endswith(".md")
    assert (tmp_path / "release-reports").exists()
    markdown = (tmp_path / "release-reports").joinpath(body["report_files"]["markdown_name"]).read_text()
    assert "task-rc" in markdown
    assert "Pre-Release Gates" in markdown
    assert "Required missing: 0" in markdown
    assert "Required manual: 0" in markdown
    assert "bash scripts/run_live_e2e.sh all" in markdown
    assert "Run URL: https://github.com/fantasyce/across-agents-assistant/actions/runs/123" in markdown
    encoded = json.dumps(body)
    assert "rc-secret-should-not-leak" not in encoded
    assert "api_key" not in encoded.lower()


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

    response = TestClient(app).post("/api/release/verification")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "attention"
    assert body["latest_release_e2e"] is None
    assert any("Release E2E" in item for item in body["remediations"])
    assert body["report_files"]["markdown_path"].endswith(".md")


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

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_build_startup_diagnostics", lambda: _startup_report())
    monkeypatch.setattr(api_server, "app_subdir", lambda name: tmp_path / name)
    monkeypatch.setattr(api_server, "_load_task_info_read_only", lambda task_id: _release_e2e_task(task_id))
    monkeypatch.setattr(release_verification, "_repository_root", lambda: repo_root)

    response = TestClient(app).post("/api/release/verification")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "attention"
    assert body["pre_release_gate_summary"]["required_missing"] > 0
    assert "scripts/run_live_e2e.sh" in body["pre_release_gate_missing_paths"]
    assert any("pre-release verification gates" in item for item in body["remediations"])
    markdown = (tmp_path / "release-reports").joinpath(body["report_files"]["markdown_name"]).read_text()
    assert "Required missing: 7" in markdown
    assert "Missing required gate paths:" in markdown
    assert "scripts/run_live_e2e.sh" in markdown

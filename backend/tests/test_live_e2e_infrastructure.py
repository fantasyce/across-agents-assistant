import subprocess
import re
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _load_live_e2e_client():
    path = ROOT / "backend/tests/e2e/client.py"
    spec = importlib.util.spec_from_file_location("aaa_live_e2e_client", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_live_e2e_runner_enables_live_gate_and_legacy_socket_e2e():
    script = _read("scripts/run_live_e2e.sh")

    assert "ACROSS_AGENTS_ORCHESTRATOR_COMMAND" in script
    assert "backend/tests/e2e/run_e2e.py --tier" in script
    assert "ACROSS_AGENTS_RUN_LIVE_E2E=1" in script
    assert "backend/tests/e2e/test_api_e2e.py -q" in script
    assert "mktemp -d" in script
    assert "/tmp/across-live-e2e" in script
    assert "ACROSS_AGENTS_HOME" in script
    assert "ACROSS_AGENTS_LIVE_E2E_EVIDENCE_PATH" in script
    assert "LIVE_E2E_GATE_ID" in script
    assert "scripts/write_pre_release_gate_evidence.sh" in script
    assert "ACROSS_AGENTS_PRE_RELEASE_GATE_RUNNER=\"scripts/run_live_e2e.sh\"" in script
    assert "ACROSS_AGENTS_PRE_RELEASE_GATE_ORCHESTRATOR_COMMAND" in script
    assert 'ORCHESTRATOR_COMMAND="$(cd "$(dirname "$ORCHESTRATOR_COMMAND")" && pwd)/$(basename "$ORCHESTRATOR_COMMAND")"' in script
    assert '$HOME/.across/bin/across-orchestrator' in script
    assert '$HOME/.across/plugins/across-orchestrator/venv/bin/across-orchestrator' in script
    assert '../across-orchestrator' not in script


def test_live_e2e_runner_records_interrupts_as_failed_evidence():
    script = _read("scripts/run_live_e2e.sh")

    assert 'INTERRUPTED_EXIT_CODE=""' in script
    assert 'trap \'INTERRUPTED_EXIT_CODE=130\' INT' in script
    assert 'trap \'INTERRUPTED_EXIT_CODE=143\' TERM' in script
    assert 'if [[ -n "$INTERRUPTED_EXIT_CODE" ]]; then' in script
    assert 'exit_code="$INTERRUPTED_EXIT_CODE"' in script


def test_live_e2e_requires_real_model_backed_tasks_instead_of_skipping():
    minimal = _read("backend/tests/e2e/test_e2e_minimal_task.py")
    rest_api = _read("backend/tests/e2e/test_e2e_rest_api.py")
    complex_task = _read("backend/tests/e2e/test_e2e_complex_multi_wave.py")
    legacy = _read("backend/tests/e2e/test_api_e2e.py")

    assert "require_live_model_route()" in minimal
    assert "live_task_agent_fields" in minimal
    assert "require_live_model_route()" in rest_api
    assert "live_task_agent_fields" in rest_api
    assert "require_live_model_route()" in complex_task
    assert "live_task_agent_fields" in complex_task
    assert "skip_if_model_provider_unavailable" not in legacy
    assert 'sys.path.insert(0, str(Path(__file__).resolve().parent))' in legacy


def test_live_e2e_uses_an_available_local_agent_when_the_isolated_profile_has_no_cloud_key(monkeypatch):
    client = _load_live_e2e_client()

    def fake_request(_method, path, _body=None, _expect=200):
        if path == "/api/keys/status":
            return {"providers": {"minimax": "not_configured"}}
        if path == "/api/agents/detect":
            return {
                "codex": {"available": True},
                "kimi": {"available": True},
            }
        raise AssertionError(path)

    monkeypatch.setattr(client, "request", fake_request)
    monkeypatch.delenv("ACROSS_AGENTS_LIVE_E2E_AGENT", raising=False)

    route = client.require_live_model_route()

    assert route == {"kind": "local_agent", "id": "codex"}
    assert client.live_task_agent_fields(route) == {
        "owner_agent": "codex",
        "allowed_subtask_agents": ["codex"],
    }


def test_live_e2e_fails_instead_of_skipping_when_no_real_model_route_exists(monkeypatch):
    client = _load_live_e2e_client()
    monkeypatch.setattr(
        client,
        "request",
        lambda _method, path, _body=None, _expect=200: (
            {"providers": {}} if path == "/api/keys/status" else {}
        ),
    )
    monkeypatch.delenv("ACROSS_AGENTS_LIVE_E2E_AGENT", raising=False)

    with pytest.raises(AssertionError, match="real model route"):
        client.require_live_model_route()


def test_live_e2e_projects_stay_under_the_runner_owned_root(monkeypatch, tmp_path):
    client = _load_live_e2e_client()
    owned_root = tmp_path / "projects"
    monkeypatch.setenv("ACROSS_AGENTS_LIVE_E2E_PROJECT_ROOT", str(owned_root))

    project_dir = client.live_project_dir("REST API / release")

    assert project_dir.parent == owned_root
    assert project_dir.is_dir()
    assert project_dir.name.startswith("rest-api-release-")


def test_live_e2e_accepts_a_structurally_passing_human_review_checkpoint():
    client = _load_live_e2e_client()

    client.assert_release_task_checkpoint({
        "status": "completed",
        "artifacts": [{"id": "artifact-1"}],
        "acceptance_records": [{
            "decision": "review",
            "deterministic_passed": True,
            "failed_checks": [],
        }],
        "delivery_report": {"quality_gate": "manual_required"},
    })


def test_live_e2e_rejects_a_failed_deterministic_gate_at_the_review_checkpoint():
    client = _load_live_e2e_client()

    with pytest.raises(AssertionError, match="deterministic acceptance gates"):
        client.assert_release_task_checkpoint({
            "status": "completed",
            "artifacts": [{"id": "artifact-1"}],
            "acceptance_records": [{
                "decision": "review",
                "deterministic_passed": False,
                "failed_checks": ["required artifact is missing"],
            }],
            "delivery_report": {"quality_gate": "manual_required"},
        })


def test_live_e2e_workflow_is_manual_and_uses_pinned_orchestrator():
    workflow = _read(".github/workflows/live-e2e.yml")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "git+https://github.com/fantasyce/across-orchestrator.git@v0.11.0" in workflow
    assert "scripts/run_live_e2e.sh" in workflow
    assert "ACROSS_AGENTS_ORCHESTRATOR_COMMAND" in workflow
    assert "ACROSS_AGENTS_LIVE_E2E_GATE_ID=\"github_live_e2e\"" in workflow
    assert re.search(r"uses:\s*actions/upload-artifact@v\d+\b", workflow)
    assert "live-e2e-gate-evidence" in workflow


def test_quality_workflow_runs_swift_behavior_checks():
    workflow = _read(".github/workflows/quality.yml")

    assert "swift build --package-path macOS-Client --skip-update" in workflow
    assert "bash scripts/run_swift_behavior_checks.sh" in workflow


def test_loop_engineering_e2e_can_verify_candidate_app_lifecycle():
    script = _read("scripts/run_loop_engineering_e2e.sh")

    assert "LOOP_ENGINEERING_VERIFY_CANDIDATE_APP" in script
    assert "LOOP_ENGINEERING_RUN_TIMEOUT_SECONDS" in script
    assert "request_timeout = float(sys.argv[5])" in script
    assert "scripts/candidate_app_lifecycle.sh" in script
    assert "candidate_repo_path" in script
    assert "candidate_runtime_preflight" in script
    assert "candidate_llm_status" in script
    assert 'candidate_llm_status.get("availability_source") == "candidate_model_lease"' in script
    assert 'candidate_lease_status.get("raw_credentials_allowed") is False' in script


def test_platform_self_repair_e2e_exercises_router_and_repair_loop():
    script = _read("scripts/run_platform_self_repair_e2e.sh")

    assert "aaa-platform-self-repair-router-case" in script
    assert "runtime.platform_self_repair" in script
    assert "auto_platform_self_repair" in script
    assert "platform_self_repair_case" in script
    assert 'assert "aaa-platform-self-repair" in built_in_ids' in script
    assert 'diagnosis["eligible"] is True' in script
    assert 'repair_trigger["spec_id"] == "aaa-platform-self-repair"' in script
    assert "PLATFORM_SELF_REPAIR_E2E_RUN_REPAIR" in script
    assert 'repair_dispatch["status"] == "completed"' in script
    assert 'candidate["promotion_package"]["human_approval_required"] is True' in script


def test_candidate_app_lifecycle_enforces_single_instance_cleanup_and_crash_gate():
    script = _read("scripts/candidate_app_lifecycle.sh")

    assert 'ACROSS_HOME="${ACROSS_HOME:-"$HOME/.across"}"' in script
    assert 'APP_PATH=""' in script
    assert "data/across-autopilot/candidate-apps/%s/Across Agents Assistant Candidate.app" in script
    assert 'APP_PATH="$(default_app_path)"' in script
    assert 'APP_PATH="$HOME/Applications/Across Agents Assistant Candidate.app"' not in script
    assert "MAX_SOCKET_BYTES" in script
    assert 'MAX_SOCKET_BYTES="${MAX_SOCKET_BYTES:-100}"' in script
    assert "cleanup_candidate_processes" in script
    assert "candidate_pids" in script
    assert "plist_set_or_add" in script
    assert "extract_json_object" in script
    assert "json_or_default" in script
    assert "json.JSONDecoder()" in script
    assert "HEALTH_FILE" in script
    assert "cat \"$HEALTH_FILE\"" in script
    assert "LLM_STATUS_FILE" in script
    assert "cat \"$LLM_STATUS_FILE\"" in script
    assert "http://localhost/api/llm/status" in script
    assert '"availability_source") != "candidate_model_lease"' in script
    assert '"secrets_included") is not False' in script
    assert "crash_reports_json" in script
    assert "AcrossAgentsAssistant-*.ips" in script
    assert "KEEP_CANDIDATE_APP_RUNNING" in script
    assert "KEEP_CANDIDATE_APP_BUNDLE" in script
    assert "cleanup_candidate_app_bundle" in script
    assert '"app_bundle_retained": pathlib.Path(app_path).exists()' in script
    assert "--env \"ACROSS_HOME=$RUNTIME_HOME\"" in script
    assert "--env \"ACROSS_AGENTS_HOME=$APP_HOME\"" in script
    assert "candidate-model-lease.json" in script
    assert "--env \"ACROSS_AAA_CANDIDATE_MODEL_LEASE=$model_lease\"" in script
    assert "local install_env=(" in script
    assert "\"ACROSS_PLUGIN_HOME=$RUNTIME_HOME/plugins\"" in script
    assert "\"ACROSS_BIN_HOME=$RUNTIME_HOME/bin\"" in script
    assert '"${install_env[@]}" node "$AUTOPILOT_ROOT/src/cli.js" install host-plugin --across-home "$RUNTIME_HOME"' in script
    assert "/usr/bin/env -u PYTHONPATH -u PYTHONHOME" in script
    assert "/bin/bash ./build_app.sh" in script
    assert "cleaned_up" in script


def test_build_app_bundles_candidate_app_lifecycle_helper():
    script = _read("build_app.sh")

    assert 'REQUIREMENTS_FILE="$PROJECT_ROOT/backend/requirements.txt"' in script
    assert "Installing critical backend runtime dependencies" in script
    assert '"mcp[cli]>=1.28.1"' in script
    assert "Verifying critical backend runtime modules" in script
    assert 'PYTHONPATH= "$PYTHON_BIN"' in script
    assert '"typer"' in script
    assert '"uvicorn"' in script
    assert '"anyio"' in script
    assert "Contents/Resources/scripts" in script
    assert "scripts/candidate_app_lifecycle.sh" in script
    assert "chmod +x \"$APP_DIR/Contents/Resources/scripts/candidate_app_lifecycle.sh\"" in script


def test_backend_requirements_include_mcp_cli_extra_for_pyinstaller_collection():
    for path in ("backend/requirements.txt", "backend/requirements_no_pyobjc.txt"):
        requirements = _read(path).splitlines()

        assert any(line.strip().startswith("mcp[cli]>=") for line in requirements), path


def test_packaged_backend_dispatches_autopilot_review_cli():
    main = _read("backend/main.py")

    assert 'sys.argv[1] == "autopilot-research-decision"' in main
    assert 'sys.argv[1] == "autopilot-code-iteration"' in main
    assert 'sys.argv[1] == "autopilot-review-decision"' in main
    assert "autopilot_review_decision_cli" in main
    assert "review_decision_main(sys.argv[2:])" in main


def test_candidate_app_lifecycle_extracts_health_json_from_noisy_output():
    completed = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts/candidate_app_lifecycle.sh"), "extract-json-object"],
        input='launch noise {"status":"ok","ready":true} trailing noise {"ignored":true}',
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert completed.stdout.strip() == '{"status":"ok","ready":true}'

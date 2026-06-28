import subprocess
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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


def test_live_e2e_workflow_is_manual_and_uses_pinned_orchestrator():
    workflow = _read(".github/workflows/live-e2e.yml")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "git+https://github.com/fantasyce/across-orchestrator.git@v0.7.7" in workflow
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


def test_candidate_app_lifecycle_enforces_single_instance_cleanup_and_crash_gate():
    script = _read("scripts/candidate_app_lifecycle.sh")

    assert "MAX_SOCKET_BYTES" in script
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
    assert "--env \"ACROSS_HOME=$RUNTIME_HOME\"" in script
    assert "--env \"ACROSS_AGENTS_HOME=$APP_HOME\"" in script
    assert "candidate-model-lease.json" in script
    assert "--env \"ACROSS_AAA_CANDIDATE_MODEL_LEASE=$model_lease\"" in script
    assert "cleaned_up" in script


def test_build_app_bundles_candidate_app_lifecycle_helper():
    script = _read("build_app.sh")

    assert "Contents/Resources/scripts" in script
    assert "scripts/candidate_app_lifecycle.sh" in script
    assert "chmod +x \"$APP_DIR/Contents/Resources/scripts/candidate_app_lifecycle.sh\"" in script


def test_candidate_app_lifecycle_extracts_health_json_from_noisy_output():
    completed = subprocess.run(
        ["bash", str(ROOT / "scripts/candidate_app_lifecycle.sh"), "extract-json-object"],
        input='launch noise {"status":"ok","ready":true} trailing noise {"ignored":true}',
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert completed.stdout.strip() == '{"status":"ok","ready":true}'

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
    assert "Live E2E evidence written" in script
    assert 'ORCHESTRATOR_COMMAND="$(cd "$(dirname "$ORCHESTRATOR_COMMAND")" && pwd)/$(basename "$ORCHESTRATOR_COMMAND")"' in script


def test_live_e2e_workflow_is_manual_and_uses_pinned_orchestrator():
    workflow = _read(".github/workflows/live-e2e.yml")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "git+https://github.com/fantasyce/across-orchestrator.git@v0.6.18" in workflow
    assert "scripts/run_live_e2e.sh" in workflow
    assert "ACROSS_AGENTS_ORCHESTRATOR_COMMAND" in workflow
    assert "ACROSS_AGENTS_LIVE_E2E_GATE_ID=\"github_live_e2e\"" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "live-e2e-gate-evidence" in workflow


def test_quality_workflow_runs_swift_behavior_checks():
    workflow = _read(".github/workflows/quality.yml")

    assert "swift build --package-path macOS-Client --skip-update" in workflow
    assert "bash scripts/run_swift_behavior_checks.sh" in workflow

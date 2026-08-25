#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_ROOT="${ACROSS_ORCHESTRATOR_SOURCE:-$ROOT_DIR/../across-orchestrator}"
CONTEXT_ROOT="${ACROSS_CONTEXT_SOURCE:-$ROOT_DIR/../across-context}"
AUTOPILOT_ROOT="${ACROSS_AUTOPILOT_SOURCE:-$ROOT_DIR/../across-autopilot}"
REPORT_ROOT="${ACROSS_VNEXT_ACCEPTANCE_REPORT_DIR:-$HOME/.across/data/across-agents-assistant/release-reports}"
RUN_ID="vnext-single-release-$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$REPORT_ROOT/$RUN_ID"
SUMMARY_PATH="$RUN_DIR/summary.json"
AUTOMATED_ONLY=0
INCLUDE_PACKAGED_APP="${ACROSS_VNEXT_INCLUDE_PACKAGED_APP:-0}"

usage() {
  echo "usage: $0 [--automated-only] [--include-packaged-app]"
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --automated-only)
      AUTOMATED_ONLY=1
      ;;
    --include-packaged-app)
      INCLUDE_PACKAGED_APP=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 64
      ;;
  esac
  shift
done

for repo in "$ROOT_DIR" "$ORCHESTRATOR_ROOT" "$CONTEXT_ROOT" "$AUTOPILOT_ROOT"; do
  if [[ ! -e "$repo/.git" ]]; then
    echo "Missing Across repository: $repo" >&2
    exit 2
  fi
done

mkdir -p "$RUN_DIR"
FAILED=0

run_gate() {
  local gate_id="$1"
  local workdir="$2"
  local command="$3"
  local log_path="$RUN_DIR/$gate_id.log"
  local result_path="$RUN_DIR/$gate_id.json"
  local started_at
  local completed_at
  local start_seconds
  local duration_seconds
  local exit_code=0
  local status="passed"

  started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  start_seconds="$(date +%s)"
  echo "== vNext acceptance: $gate_id =="
  (
    cd "$workdir"
    /bin/bash -lc "$command"
  ) > >(tee "$log_path") 2>&1 || exit_code="$?"
  completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  duration_seconds="$(($(date +%s) - start_seconds))"
  if [[ "$exit_code" -ne 0 ]]; then
    status="failed"
    FAILED=1
  fi

  GATE_ID="$gate_id" \
  STATUS="$status" \
  EXIT_CODE="$exit_code" \
  STARTED_AT="$started_at" \
  COMPLETED_AT="$completed_at" \
  DURATION_SECONDS="$duration_seconds" \
  COMMAND_NAME="${command%% *}" \
  RESULT_PATH="$result_path" \
  python3 - <<'PY'
import json
import os
from pathlib import Path

payload = {
    "gate_id": os.environ["GATE_ID"],
    "status": os.environ["STATUS"],
    "exit_code": int(os.environ["EXIT_CODE"]),
    "started_at": os.environ["STARTED_AT"],
    "completed_at": os.environ["COMPLETED_AT"],
    "duration_seconds": int(os.environ["DURATION_SECONDS"]),
    "runner": os.environ["COMMAND_NAME"],
}
Path(os.environ["RESULT_PATH"]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

run_gate \
  independent_design_scan \
  "$ROOT_DIR" \
  "if matches=\$(rg -n -i 'homerail|xiaotianfotos' macOS-Client/Sources backend/src assets README.md CHANGELOG.md build_app.sh); then printf '%s\\n' \"\$matches\"; exit 1; else scan_status=\$?; test \"\$scan_status\" -eq 1; fi"

run_gate \
  acceptance_environment_setup \
  "$ROOT_DIR" \
  "ACROSS_ORCHESTRATOR_SOURCE='$ORCHESTRATOR_ROOT' bash scripts/prepare_vnext_acceptance_environment.sh"

run_gate orchestrator_check "$ORCHESTRATOR_ROOT" "bash scripts/check.sh"
run_gate context_check "$CONTEXT_ROOT" "bash scripts/check.sh"
run_gate autopilot_check "$AUTOPILOT_ROOT" "env -u ACROSS_ORCHESTRATOR_SOURCE -u ACROSS_CONTEXT_SOURCE -u ACROSS_AUTOPILOT_SOURCE bash scripts/check.sh && npm audit --audit-level=high"
run_gate plugin_boundary_contracts "$ROOT_DIR" "bash scripts/run_plugin_boundary_checks.sh"
run_gate growth_asset_regeneration "$ROOT_DIR" "uv run --with pillow python scripts/prepare_growth_asset_atlases.py"
run_gate aaa_local_gates "$ROOT_DIR" "bash scripts/run_pre_release_local_gates.sh"
run_gate fresh_profile_plugin_no_key_e2e "$ROOT_DIR" "bash scripts/run_fresh_profile_plugin_no_key_e2e.sh"
run_gate aaa_vnext_fixture_e2e "$ROOT_DIR" "VNEXT_E2E_AGENT_MODE=fixture bash scripts/run_vnext_upgrade_e2e.sh"
run_gate aaa_sandbox_e2e "$ROOT_DIR" "bash scripts/run_agent_interop_sandbox_e2e.sh"

if [[ "$INCLUDE_PACKAGED_APP" == "1" ]]; then
  # A vNext acceptance candidate must exercise the four checkouts that were
  # just tested above. The default packaging path intentionally stays pinned to
  # public release commits, so opt this local, non-release build into the
  # sibling source trees explicitly.
  run_gate \
    packaged_app_build_install \
    "$ROOT_DIR" \
    "ACROSS_BUILD_ORCHESTRATOR_SOURCE_ROOT='$ORCHESTRATOR_ROOT' ACROSS_BUILD_CONTEXT_SOURCE_ROOT='$CONTEXT_ROOT' ACROSS_BUILD_AUTOPILOT_SOURCE_ROOT='$AUTOPILOT_ROOT' bash scripts/build_and_run.sh"
  run_gate packaged_app_runtime "$ROOT_DIR" "bash scripts/verify_packaged_vnext_runtime.sh"
  run_gate packaged_app_cross_plugin_e2e "$ROOT_DIR" "bash scripts/run_packaged_app_cross_plugin_e2e.sh"
fi

SUMMARY_GENERATION_EXIT=0
ROOT_DIR="$ROOT_DIR" \
ORCHESTRATOR_ROOT="$ORCHESTRATOR_ROOT" \
CONTEXT_ROOT="$CONTEXT_ROOT" \
AUTOPILOT_ROOT="$AUTOPILOT_ROOT" \
RUN_DIR="$RUN_DIR" \
SUMMARY_PATH="$SUMMARY_PATH" \
INCLUDE_PACKAGED_APP="$INCLUDE_PACKAGED_APP" \
python3 - <<'PY' || SUMMARY_GENERATION_EXIT="$?"
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


root_dir = Path(os.environ["ROOT_DIR"])
sys.path.insert(0, str(root_dir / "backend/src"))
sys.path.insert(0, str(root_dir / "scripts"))
from across_agents_assistant.release_evidence import (
    validate_manual_evidence,
    validate_release_decision,
)
from validate_vnext_synthetic_beginner_evidence import validate_synthetic_beginner_evidence


def repository_state(path: str) -> dict[str, object]:
    root = Path(path)
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    porcelain = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain"],
        text=True,
    )
    return {"commit": commit, "dirty": bool(porcelain.strip())}


run_dir = Path(os.environ["RUN_DIR"])
gates = []
for path in sorted(run_dir.glob("*.json")):
    if path.name == "summary.json":
        continue
    gates.append(json.loads(path.read_text(encoding="utf-8")))

report_root = run_dir.parent
manual_definitions = [
    ("packaged_ui_sweep", "vnext-ui-manual-evidence.json", "waiting-unlock"),
    ("voice_hardware_smoke", "vnext-voice-hardware-evidence.json", "waiting-unlock"),
    ("beginner_synthetic_simulation", "vnext-synthetic-beginner-evidence.json", "waiting-simulation"),
]
pyproject_text = (root_dir / "backend/pyproject.toml").read_text(encoding="utf-8")
version_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
if version_match is None:
    raise RuntimeError("Could not read the candidate version from backend/pyproject.toml")
expected_version = version_match.group(1)

release_decision_path = report_root / "vnext-release-decision.json"
release_decision = None
release_decision_status = "missing"
release_decision_error = None
if release_decision_path.exists():
    try:
        release_decision = json.loads(release_decision_path.read_text(encoding="utf-8"))
        release_decision_status, release_decision_error = validate_release_decision(
            release_decision,
            expected_version=expected_version,
            verify_installed_candidate=True,
        )
    except (OSError, json.JSONDecodeError):
        release_decision_status = "failed"
        release_decision_error = "release decision is unreadable"


manual_gates = []
for gate_id, filename, missing_status in manual_definitions:
    evidence_path = report_root / filename
    status = missing_status
    evidence = None
    if evidence_path.exists():
        try:
            candidate = json.loads(evidence_path.read_text(encoding="utf-8"))
            if gate_id == "beginner_synthetic_simulation":
                status, validation_error = validate_synthetic_beginner_evidence(
                    candidate,
                    report_root=report_root,
                    expected_version=expected_version,
                    verify_installed_candidate=True,
                )
            else:
                status, validation_error = validate_manual_evidence(
                    gate_id,
                    candidate,
                    report_root=report_root,
                    expected_version=expected_version,
                    verify_installed_candidate=True,
                )
            evidence = {
                "completed_at": candidate.get("completed_at"),
                "summary": candidate.get("summary"),
                "validation_error": validation_error,
            }
        except (OSError, json.JSONDecodeError):
            status = "failed"
    if (
        gate_id == "voice_hardware_smoke"
        and status != "passed"
        and release_decision_status == "passed"
    ):
        status = "waived"
        validation_error = None
        evidence = {
            "completed_at": release_decision.get("authorized_at"),
            "summary": release_decision.get("summary"),
            "validation_error": None,
            "scope": release_decision.get("voice_hardware_gate", {}).get("scope"),
            "no_full_coverage_claim": True,
        }
    manual_gates.append({"gate_id": gate_id, "status": status, "evidence": evidence})

automated_passed = bool(gates) and all(item.get("status") == "passed" for item in gates)
manual_passed = all(item.get("status") in {"passed", "waived"} for item in manual_gates)
release_authorized = (
    automated_passed
    and manual_passed
    and release_decision_status == "passed"
)
payload = {
    "schema_version": "across-vnext-single-release-acceptance/1.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "status": "passed" if automated_passed and manual_passed else (
        "failed" if not automated_passed else "manual_required"
    ),
    "release_authorized": release_authorized,
    "release_decision": {
        "status": release_decision_status,
        "validation_error": release_decision_error,
        "authorized_at": release_decision.get("authorized_at") if release_decision else None,
    },
    "automated_passed": automated_passed,
    "manual_passed": manual_passed,
    "packaged_app_included": os.environ["INCLUDE_PACKAGED_APP"] == "1",
    "repositories": {
        "across-orchestrator": repository_state(os.environ["ORCHESTRATOR_ROOT"]),
        "across-context": repository_state(os.environ["CONTEXT_ROOT"]),
        "across-autopilot": repository_state(os.environ["AUTOPILOT_ROOT"]),
        "across-agents-assistant": repository_state(os.environ["ROOT_DIR"]),
    },
    "automated_gates": gates,
    "manual_gates": manual_gates,
}
Path(os.environ["SUMMARY_PATH"]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(f"vNext acceptance summary written to {os.environ['SUMMARY_PATH']}")
print(f"status={payload['status']}")
PY

if [[ "$SUMMARY_GENERATION_EXIT" -ne 0 ]]; then
  echo "vNext acceptance summary generation failed." >&2
  exit "$SUMMARY_GENERATION_EXIT"
fi
if [[ "$FAILED" -ne 0 ]]; then
  exit 1
fi
if [[ "$AUTOMATED_ONLY" -eq 0 ]]; then
  SUMMARY_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$SUMMARY_PATH")"
  if [[ "$SUMMARY_STATUS" != "passed" ]]; then
    echo "Automated gates passed, but required manual evidence is incomplete." >&2
    exit 2
  fi
fi

RELEASE_AUTHORIZED="$(python3 -c 'import json,sys; print(str(json.load(open(sys.argv[1]))["release_authorized"]).lower())' "$SUMMARY_PATH")"
if [[ "$RELEASE_AUTHORIZED" == "true" ]]; then
  echo "vNext single-release acceptance passed and release is explicitly authorized."
else
  echo "vNext single-release acceptance passed. Release remains unauthorized."
fi

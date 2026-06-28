#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

run_gate() {
  local gate_id="$1"
  shift
  local started_at
  local start_seconds
  local completed_seconds
  local duration_seconds
  local exit_code=0
  started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  start_seconds="$(date +%s)"
  echo "== pre-release gate: $gate_id =="
  "$@" || exit_code="$?"
  completed_seconds="$(date +%s)"
  duration_seconds="$((completed_seconds - start_seconds))"
  ACROSS_AGENTS_PRE_RELEASE_GATE_STARTED_AT="$started_at" \
  ACROSS_AGENTS_PRE_RELEASE_GATE_DURATION_SECONDS="$duration_seconds" \
    bash scripts/write_pre_release_gate_evidence.sh \
      "$gate_id" \
      "$([[ "$exit_code" -eq 0 ]] && echo passed || echo failed)" \
      local_script \
      "$([[ "$exit_code" -eq 0 ]] && echo "$gate_id passed." || echo "$gate_id failed with exit code $exit_code.")"
  return "$exit_code"
}

run_gate backend_regression env PYTHONPATH=backend/src "$PYTHON_BIN" -m pytest backend/tests --ignore=backend/tests/e2e -q
run_gate open_source_check bash scripts/open_source_check.sh
run_gate swift_behavior_checks bash scripts/run_swift_behavior_checks.sh
run_gate swift_package_gate bash -c 'bash scripts/verify_swift_package_lock.sh && swift build --package-path macOS-Client --skip-update && swift test --package-path macOS-Client --skip-update'

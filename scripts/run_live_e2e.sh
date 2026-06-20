#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TIER="${1:-all}"
PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

LIVE_E2E_GATE_ID="${ACROSS_AGENTS_LIVE_E2E_GATE_ID:-local_live_e2e}"
LIVE_E2E_EVIDENCE_PATH="${ACROSS_AGENTS_LIVE_E2E_EVIDENCE_PATH:-$HOME/.across/data/across-agents-assistant/release-reports/${LIVE_E2E_GATE_ID}-gate-evidence.json}"
STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
START_SECONDS="$(date +%s)"
COMMIT_SHA="$(git rev-parse --verify HEAD 2>/dev/null || true)"
RUN_URL="${ACROSS_AGENTS_LIVE_E2E_RUN_URL:-}"
if [[ -z "$RUN_URL" && -n "${GITHUB_SERVER_URL:-}" && -n "${GITHUB_REPOSITORY:-}" && -n "${GITHUB_RUN_ID:-}" ]]; then
  RUN_URL="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
fi

ORCHESTRATOR_COMMAND="${ACROSS_AGENTS_ORCHESTRATOR_COMMAND:-}"
TMP_PARENT=""
ACROSS_HOME_DIR=""
AGENTS_HOME_DIR=""
SOCKET_PATH=""
BACKEND_PID=""

cleanup() {
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$TMP_PARENT" ]]; then
    rm -rf "$TMP_PARENT"
  fi
}

write_live_e2e_evidence() {
  local exit_code="$1"
  local status="failed"
  if [[ "$exit_code" -eq 0 ]]; then
    status="passed"
  fi
  local completed_at
  local completed_seconds
  local duration_seconds
  local orchestrator_command_name
  completed_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  completed_seconds="$(date +%s)"
  duration_seconds="$((completed_seconds - START_SECONDS))"
  orchestrator_command_name="not_configured"
  if [[ -n "$ORCHESTRATOR_COMMAND" ]]; then
    orchestrator_command_name="$(basename "$ORCHESTRATOR_COMMAND")"
  fi
  mkdir -p "$(dirname "$LIVE_E2E_EVIDENCE_PATH")"
  LIVE_E2E_STATUS="$status" \
  LIVE_E2E_EXIT_CODE="$exit_code" \
  LIVE_E2E_STARTED_AT="$STARTED_AT" \
  LIVE_E2E_COMPLETED_AT="$completed_at" \
  LIVE_E2E_DURATION_SECONDS="$duration_seconds" \
  LIVE_E2E_TIER="$TIER" \
  LIVE_E2E_GATE_ID="$LIVE_E2E_GATE_ID" \
  LIVE_E2E_RUN_URL="$RUN_URL" \
  LIVE_E2E_COMMIT_SHA="$COMMIT_SHA" \
  LIVE_E2E_ORCHESTRATOR_COMMAND_NAME="$orchestrator_command_name" \
  LIVE_E2E_EVIDENCE_PATH="$LIVE_E2E_EVIDENCE_PATH" \
  "$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["LIVE_E2E_EVIDENCE_PATH"])
payload = {
    "schema_version": "1.0",
    "gate_id": os.environ["LIVE_E2E_GATE_ID"],
    "status": os.environ["LIVE_E2E_STATUS"],
    "source": "github_actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local_script",
    "summary": "Live E2E passed." if os.environ["LIVE_E2E_STATUS"] == "passed" else f"Live E2E failed with exit code {os.environ['LIVE_E2E_EXIT_CODE']}.",
    "tier": os.environ["LIVE_E2E_TIER"],
    "started_at": os.environ["LIVE_E2E_STARTED_AT"],
    "completed_at": os.environ["LIVE_E2E_COMPLETED_AT"],
    "duration_seconds": int(os.environ["LIVE_E2E_DURATION_SECONDS"]),
    "runner": "scripts/run_live_e2e.sh",
    "orchestrator_command": os.environ["LIVE_E2E_ORCHESTRATOR_COMMAND_NAME"],
    "commit_sha": os.environ.get("LIVE_E2E_COMMIT_SHA") or None,
    "run_url": os.environ.get("LIVE_E2E_RUN_URL") or None,
}
payload = {key: value for key, value in payload.items() if value not in (None, "")}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"Live E2E evidence written to {path}")
PY
}

finish() {
  local exit_code="$?"
  trap - EXIT
  write_live_e2e_evidence "$exit_code" || true
  cleanup
  exit "$exit_code"
}
trap finish EXIT

if [[ -z "$ORCHESTRATOR_COMMAND" ]]; then
  if command -v across-orchestrator >/dev/null 2>&1; then
    ORCHESTRATOR_COMMAND="$(command -v across-orchestrator)"
  elif [[ -x "$ROOT_DIR/../across-orchestrator/.venv/bin/across-orchestrator" ]]; then
    ORCHESTRATOR_COMMAND="$ROOT_DIR/../across-orchestrator/.venv/bin/across-orchestrator"
  else
    echo "External Across Orchestrator command is required for live E2E." >&2
    echo "Set ACROSS_AGENTS_ORCHESTRATOR_COMMAND or install across-orchestrator on PATH." >&2
    exit 2
  fi
fi

if [[ "$ORCHESTRATOR_COMMAND" == */* && ! -x "$ORCHESTRATOR_COMMAND" ]]; then
  echo "Across Orchestrator command is not executable: $ORCHESTRATOR_COMMAND" >&2
  exit 2
fi
if [[ "$ORCHESTRATOR_COMMAND" == */* ]]; then
  ORCHESTRATOR_COMMAND="$(cd "$(dirname "$ORCHESTRATOR_COMMAND")" && pwd)/$(basename "$ORCHESTRATOR_COMMAND")"
fi

TMP_PARENT="$(mktemp -d "/tmp/across-live-e2e.XXXXXX")"
ACROSS_HOME_DIR="$TMP_PARENT/across-home"
AGENTS_HOME_DIR="$TMP_PARENT/across-agents-home"
SOCKET_PATH="$AGENTS_HOME_DIR/run/across-agents.sock"

echo "Starting temporary AAA backend for live E2E..."
# Developer mode is intentional here: the runner may use a source-checkout
# Orchestrator command during local verification, while product-mode path
# boundary behavior remains covered by backend regression tests.
ACROSS_HOME="$ACROSS_HOME_DIR" \
ACROSS_AGENTS_HOME="$AGENTS_HOME_DIR" \
ACROSS_AGENTS_DEVELOPER_MODE=1 \
ACROSS_ORCHESTRATOR_DEVELOPER_MODE=1 \
ACROSS_AGENTS_ORCHESTRATOR_COMMAND="$ORCHESTRATOR_COMMAND" \
ACROSS_AGENTS_ORCHESTRATOR_AUTORUN=1 \
PYTHONPATH=backend/src \
"$PYTHON_BIN" -c "from across_agents_assistant.api_server import start_api_server; start_api_server()" &
BACKEND_PID="$!"

echo "Waiting for backend socket: $SOCKET_PATH"
ACROSS_AGENTS_SOCKET="$SOCKET_PATH" "$PYTHON_BIN" - <<'PY'
import os
import time
from pathlib import Path

import httpx

socket_path = os.environ["ACROSS_AGENTS_SOCKET"]
deadline = time.time() + 30
while time.time() < deadline:
    if Path(socket_path).exists():
        try:
            transport = httpx.HTTPTransport(uds=socket_path)
            with httpx.Client(transport=transport, timeout=2) as client:
                response = client.get("http://backend/api/llm/status")
            if response.status_code == 200:
                raise SystemExit(0)
        except Exception:
            pass
    time.sleep(0.5)
raise SystemExit(f"Backend socket did not become ready: {socket_path}")
PY

echo "Running live E2E tier: $TIER"
ACROSS_AGENTS_SOCKET="$SOCKET_PATH" \
PYTHONPATH=backend/src \
"$PYTHON_BIN" backend/tests/e2e/run_e2e.py --tier "$TIER"

echo "Running legacy socket API E2E with live runtime gate enabled"
ACROSS_AGENTS_SOCKET="$SOCKET_PATH" \
ACROSS_AGENTS_RUN_LIVE_E2E=1 \
PYTHONPATH=backend/src \
"$PYTHON_BIN" -m pytest backend/tests/e2e/test_api_e2e.py -q

echo "Live E2E passed."

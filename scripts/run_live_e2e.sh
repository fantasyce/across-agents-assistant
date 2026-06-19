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

ORCHESTRATOR_COMMAND="${ACROSS_AGENTS_ORCHESTRATOR_COMMAND:-}"
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

TMP_PARENT="$(mktemp -d "/tmp/across-live-e2e.XXXXXX")"
ACROSS_HOME_DIR="$TMP_PARENT/across-home"
AGENTS_HOME_DIR="$TMP_PARENT/across-agents-home"
SOCKET_PATH="$AGENTS_HOME_DIR/run/across-agents.sock"
BACKEND_PID=""

cleanup() {
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_PARENT"
}
trap cleanup EXIT

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

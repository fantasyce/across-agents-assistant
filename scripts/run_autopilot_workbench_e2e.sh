#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
fi

PYTHONPATH="$ROOT_DIR/backend/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m pytest \
  backend/tests/test_aaa_ecosystem_roadmap.py \
  backend/tests/test_autopilot_workbench.py \
  backend/tests/test_external_agent_plugin_gateway.py \
  backend/tests/e2e/test_autopilot_workbench_e2e.py \
  backend/tests/e2e/test_agent_plugin_runtime_cross_process_e2e.py

bash scripts/run_swift_behavior_checks.sh

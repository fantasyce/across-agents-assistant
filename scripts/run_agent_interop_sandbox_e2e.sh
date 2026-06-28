#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
fi

PYTHONPATH="$ROOT_DIR/backend/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m pytest \
  backend/tests/e2e/test_agent_interop_sandbox_evidence_e2e.py

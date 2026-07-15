#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ACROSS_AAA_TEST_PYTHON:-$ROOT_DIR/backend/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "Python 3 is required for the beginner-study session helper." >&2
  exit 2
fi

PYTHONPATH="$ROOT_DIR/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" -m across_agents_assistant.beginner_study_session "$@"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_ROOT="${ACROSS_ORCHESTRATOR_SOURCE:-$ROOT_DIR/../across-orchestrator}"
AAA_PYTHON="$ROOT_DIR/backend/.venv/bin/python"
ORCHESTRATOR_PYTHON="$ORCHESTRATOR_ROOT/.venv/bin/python"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to prepare the vNext acceptance environments." >&2
  exit 2
fi

if [[ ! -f "$ROOT_DIR/backend/requirements_no_pyobjc.txt" ]]; then
  echo "Missing AAA acceptance requirements." >&2
  exit 2
fi
if [[ ! -f "$ORCHESTRATOR_ROOT/pyproject.toml" ]]; then
  echo "Missing Across Orchestrator pyproject.toml." >&2
  exit 2
fi

if [[ ! -x "$AAA_PYTHON" ]]; then
  uv venv "$ROOT_DIR/backend/.venv" --python 3.11
fi
uv pip install --python "$AAA_PYTHON" \
  --requirement "$ROOT_DIR/backend/requirements_no_pyobjc.txt"

if [[ ! -x "$ORCHESTRATOR_PYTHON" ]]; then
  uv venv "$ORCHESTRATOR_ROOT/.venv" --python 3.11
fi
uv pip install --python "$ORCHESTRATOR_PYTHON" \
  --editable "$ORCHESTRATOR_ROOT[dev]"

"$AAA_PYTHON" -c 'import pytest, fastapi, mcp'
"$ORCHESTRATOR_PYTHON" -c 'import pytest, across_orchestrator'
test -x "$ORCHESTRATOR_ROOT/.venv/bin/across-orchestrator"

echo "vNext acceptance environments are ready."

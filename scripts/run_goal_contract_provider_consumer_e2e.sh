#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_ROOT="${ACROSS_ORCHESTRATOR_SOURCE:-$ROOT_DIR/../across-orchestrator}"
PYTHON_BIN=""

for candidate in "$ROOT_DIR/backend/.venv/bin/python" "$ROOT_DIR/.venv/bin/python"; do
  if [[ -x "$candidate" ]]; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [[ ! -f "$ORCHESTRATOR_ROOT/pyproject.toml" ]]; then
  echo "Across Orchestrator source is missing: $ORCHESTRATOR_ROOT" >&2
  exit 2
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "No AAA Python environment is available; run prepare_vnext_acceptance_environment.sh first." >&2
  exit 2
fi

cd "$ROOT_DIR"
ACROSS_ORCHESTRATOR_PROVIDER_ROOT="$ORCHESTRATOR_ROOT" \
PYTHONPATH=backend/src \
  "$PYTHON_BIN" -m pytest -p no:cacheprovider \
    backend/tests/test_goal_contract_real_provider.py -q

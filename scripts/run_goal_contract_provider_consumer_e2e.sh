#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_ROOT="${ACROSS_ORCHESTRATOR_SOURCE:-$ROOT_DIR/../across-orchestrator}"

if [[ ! -f "$ORCHESTRATOR_ROOT/pyproject.toml" ]]; then
  echo "Across Orchestrator source is missing: $ORCHESTRATOR_ROOT" >&2
  exit 2
fi

cd "$ROOT_DIR"
ACROSS_ORCHESTRATOR_PROVIDER_ROOT="$ORCHESTRATOR_ROOT" \
PYTHONPATH=backend/src \
  .venv/bin/python -m pytest -p no:cacheprovider \
    backend/tests/test_goal_contract_real_provider.py -q

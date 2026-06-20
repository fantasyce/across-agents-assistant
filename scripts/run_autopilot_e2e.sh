#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTOPILOT_SOURCE="${ACROSS_AUTOPILOT_SOURCE:-$(cd "$ROOT/../across-autopilot" && pwd)}"

if [[ ! -f "$AUTOPILOT_SOURCE/src/cli.js" ]]; then
  echo "Across Autopilot source checkout not found: $AUTOPILOT_SOURCE" >&2
  exit 2
fi

export ACROSS_AUTOPILOT_SOURCE="$AUTOPILOT_SOURCE"

cd "$ROOT/backend"
PYTHONPATH=src .venv/bin/python -m pytest tests/e2e/test_autopilot_plugin_e2e.py -q


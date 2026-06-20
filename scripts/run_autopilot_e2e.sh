#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_AUTOPILOT_SOURCE="${ACROSS_AUTOPILOT_SOURCE:-$ROOT/../across-autopilot}"

if [[ ! -d "$RAW_AUTOPILOT_SOURCE" ]]; then
  echo "Across Autopilot source checkout not found: $RAW_AUTOPILOT_SOURCE" >&2
  exit 2
fi

AUTOPILOT_SOURCE="$(cd "$RAW_AUTOPILOT_SOURCE" && pwd)"

if [[ ! -f "$AUTOPILOT_SOURCE/src/cli.js" ]]; then
  echo "Across Autopilot CLI not found under source checkout: $AUTOPILOT_SOURCE" >&2
  exit 2
fi

export ACROSS_AUTOPILOT_SOURCE="$AUTOPILOT_SOURCE"

cd "$ROOT/backend"
PYTHONPATH=src .venv/bin/python -m pytest tests/e2e/test_autopilot_plugin_e2e.py -q

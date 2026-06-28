#!/usr/bin/env bash
set -euo pipefail

GATE_ID="${1:?usage: write_pre_release_gate_evidence.sh <gate-id> [status] [source] [summary]}"
STATUS="${2:-passed}"
SOURCE="${3:-local_script}"
SUMMARY="${4:-${GATE_ID} ${STATUS}}"

PYTHON_BIN="${PYTHON:-python3}"
EVIDENCE_PATH="${ACROSS_AGENTS_PRE_RELEASE_GATE_EVIDENCE_PATH:-$HOME/.across/data/across-agents-assistant/release-reports/${GATE_ID}-gate-evidence.json}"
TIER="${ACROSS_AGENTS_PRE_RELEASE_GATE_TIER:-all}"
STARTED_AT="${ACROSS_AGENTS_PRE_RELEASE_GATE_STARTED_AT:-}"
COMPLETED_AT="${ACROSS_AGENTS_PRE_RELEASE_GATE_COMPLETED_AT:-$(date -u +"%Y-%m-%dT%H:%M:%SZ")}"
DURATION_SECONDS="${ACROSS_AGENTS_PRE_RELEASE_GATE_DURATION_SECONDS:-0}"
RUN_URL="${ACROSS_AGENTS_PRE_RELEASE_GATE_RUN_URL:-}"
WORKFLOW_RUN_URL="${ACROSS_AGENTS_PRE_RELEASE_GATE_WORKFLOW_RUN_URL:-}"
COMMIT_SHA="${ACROSS_AGENTS_PRE_RELEASE_GATE_COMMIT_SHA:-$(git rev-parse --verify HEAD 2>/dev/null || true)}"
RUNNER="${ACROSS_AGENTS_PRE_RELEASE_GATE_RUNNER:-}"
ORCHESTRATOR_COMMAND="${ACROSS_AGENTS_PRE_RELEASE_GATE_ORCHESTRATOR_COMMAND:-}"
WORKSPACE_DIRTY="${ACROSS_AGENTS_PRE_RELEASE_GATE_WORKSPACE_DIRTY:-}"
if [[ -z "$WORKSPACE_DIRTY" ]]; then
  if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
    WORKSPACE_DIRTY="true"
  else
    WORKSPACE_DIRTY="false"
  fi
fi

mkdir -p "$(dirname "$EVIDENCE_PATH")"

GATE_ID="$GATE_ID" \
STATUS="$STATUS" \
SOURCE="$SOURCE" \
SUMMARY="$SUMMARY" \
EVIDENCE_PATH="$EVIDENCE_PATH" \
TIER="$TIER" \
STARTED_AT="$STARTED_AT" \
COMPLETED_AT="$COMPLETED_AT" \
DURATION_SECONDS="$DURATION_SECONDS" \
RUN_URL="$RUN_URL" \
WORKFLOW_RUN_URL="$WORKFLOW_RUN_URL" \
COMMIT_SHA="$COMMIT_SHA" \
RUNNER="$RUNNER" \
ORCHESTRATOR_COMMAND="$ORCHESTRATOR_COMMAND" \
WORKSPACE_DIRTY="$WORKSPACE_DIRTY" \
"$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path


def optional_env(name: str):
    value = os.environ.get(name)
    return value if value not in (None, "") else None


duration_raw = os.environ.get("DURATION_SECONDS") or "0"
try:
    duration_seconds = int(duration_raw)
except ValueError:
    duration_seconds = 0

payload = {
    "schema_version": "1.0",
    "gate_id": os.environ["GATE_ID"],
    "status": os.environ["STATUS"],
    "source": os.environ["SOURCE"],
    "summary": os.environ["SUMMARY"],
    "tier": optional_env("TIER"),
    "started_at": optional_env("STARTED_AT"),
    "completed_at": optional_env("COMPLETED_AT"),
    "duration_seconds": duration_seconds,
    "run_url": optional_env("RUN_URL"),
    "workflow_run_url": optional_env("WORKFLOW_RUN_URL"),
    "commit_sha": optional_env("COMMIT_SHA"),
    "runner": optional_env("RUNNER"),
    "orchestrator_command": optional_env("ORCHESTRATOR_COMMAND"),
    "workspace_dirty": os.environ.get("WORKSPACE_DIRTY") == "true",
}
payload = {key: value for key, value in payload.items() if value not in (None, "")}
path = Path(os.environ["EVIDENCE_PATH"])
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"Pre-release gate evidence written to {path}")
PY

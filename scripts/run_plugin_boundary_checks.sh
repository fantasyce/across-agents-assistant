#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_ROOT="${ACROSS_ORCHESTRATOR_SOURCE:-$ROOT_DIR/../across-orchestrator}"
CONTEXT_ROOT="${ACROSS_CONTEXT_SOURCE:-$ROOT_DIR/../across-context}"
AUTOPILOT_ROOT="${ACROSS_AUTOPILOT_SOURCE:-$ROOT_DIR/../across-autopilot}"
ORCHESTRATOR_COMMAND="${ACROSS_ORCHESTRATOR_STANDALONE_COMMAND:-$ORCHESTRATOR_ROOT/.venv/bin/across-orchestrator}"
TMP_DIR="$(mktemp -d /tmp/across-plugin-boundary.XXXXXX)"

cleanup() {
  local status="$?"
  rm -rf "$TMP_DIR"
  exit "$status"
}
trap cleanup EXIT

for path in "$CONTEXT_ROOT/src/cli.js" "$AUTOPILOT_ROOT/src/cli.js"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing standalone producer runtime: $path" >&2
    exit 2
  fi
done
if [[ ! -x "$ORCHESTRATOR_COMMAND" ]]; then
  echo "Missing executable standalone producer runtime: $ORCHESTRATOR_COMMAND" >&2
  exit 2
fi

mkdir -p "$TMP_DIR/project"
cat > "$TMP_DIR/project/package.json" <<'JSON'
{
  "name": "across-plugin-boundary-fixture",
  "version": "1.0.0",
  "license": "MIT"
}
JSON

ACROSS_HOME="$TMP_DIR/context-home" \
  node "$CONTEXT_ROOT/src/cli.js" health --json > "$TMP_DIR/context.json"

ACROSS_HOME="$TMP_DIR/orchestrator-home" \
  "$ORCHESTRATOR_COMMAND" health --json > "$TMP_DIR/orchestrator.json"

ACROSS_HOME="$TMP_DIR/autopilot-home" \
ACROSS_CONTEXT_COMMAND="$TMP_DIR/missing-context" \
ACROSS_ORCHESTRATOR_COMMAND="$TMP_DIR/missing-orchestrator" \
  node "$AUTOPILOT_ROOT/src/cli.js" health --json > "$TMP_DIR/autopilot.json"

GOAL_CONTRACT_JSON="$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), separators=(",", ":")))' "$ROOT_DIR/fixtures/goal-contract/simple.json")"
ACROSS_HOME="$TMP_DIR/context-home" \
  node "$CONTEXT_ROOT/src/cli.js" goal-contract --contract-json "$GOAL_CONTRACT_JSON" --json > "$TMP_DIR/context-goal.json"
ACROSS_HOME="$TMP_DIR/orchestrator-home" \
  "$ORCHESTRATOR_COMMAND" goal-contract --contract-json "$GOAL_CONTRACT_JSON" --json > "$TMP_DIR/orchestrator-goal.json"
ACROSS_HOME="$TMP_DIR/autopilot-home" \
  node "$AUTOPILOT_ROOT/src/cli.js" goal-contract --contract-json "$GOAL_CONTRACT_JSON" --json > "$TMP_DIR/autopilot-goal.json"

(
  cd "$TMP_DIR/project"
  ACROSS_HOME="$TMP_DIR/autopilot-home" \
  ACROSS_CONTEXT_COMMAND="$TMP_DIR/missing-context" \
  ACROSS_ORCHESTRATOR_COMMAND="$TMP_DIR/missing-orchestrator" \
    node "$AUTOPILOT_ROOT/src/cli.js" loop run --spec repo-quality-copilot --json \
      > "$TMP_DIR/autopilot-standalone-run.json"
)

ACROSS_HOME="$TMP_DIR/autopilot-home" \
ACROSS_CONTEXT_COMMAND="$TMP_DIR/missing-context" \
ACROSS_ORCHESTRATOR_COMMAND="$TMP_DIR/missing-orchestrator" \
  node "$AUTOPILOT_ROOT/src/cli.js" loop dry-run --spec aaa-release-readiness-gate --json \
    > "$TMP_DIR/required-plugin-preflight.json"

TMP_DIR="$TMP_DIR" python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path


root = Path(os.environ["TMP_DIR"])


def load(name: str):
    return json.loads((root / name).read_text(encoding="utf-8"))


for name in ("context.json", "orchestrator.json", "autopilot.json"):
    payload = load(name)
    if payload.get("status") not in {"ok", "healthy"}:
        raise SystemExit(f"Standalone health failed: {name}")

goal_results = [load(name) for name in ("context-goal.json", "orchestrator-goal.json", "autopilot-goal.json")]
if any(item != goal_results[0] for item in goal_results[1:]):
    raise SystemExit("Standalone plugin Goal Contract probes do not match.")

standalone = load("autopilot-standalone-run.json")
if standalone.get("run", {}).get("status") != "completed":
    raise SystemExit("Autopilot's local workflow did not complete without AAA or sibling plugins.")
memory_actions = [
    action for action in standalone.get("evidence", {}).get("actions", [])
    if action.get("adapter") == "memory_write_candidate"
]
if len(memory_actions) != 1:
    raise SystemExit("Standalone workflow did not produce one bounded optional-memory result.")
memory_result = memory_actions[0].get("result", {}).get("memory", {})
if memory_actions[0].get("status") != "attention" or memory_result.get("mode") != "optional-context-unavailable":
    raise SystemExit("Optional Context absence was not represented as a non-fatal attention state.")

required = load("required-plugin-preflight.json").get("capability_preflight", {})
missing = set(required.get("missing_capabilities", []))
if required.get("status") != "failed" or not {
    "action.orchestrator_task_dispatch",
    "memory.pending_summary",
}.issubset(missing):
    raise SystemExit("A workflow with required sibling plugins did not fail capability preflight early.")

print(json.dumps({
    "status": "passed",
    "zero_host": "passed",
    "standalone_context": "passed",
    "standalone_orchestrator": "passed",
    "standalone_autopilot": "passed",
    "optional_context_degradation": "passed",
    "required_plugin_preflight": "passed",
    "goal_contract_cli_parity": "passed",
}, indent=2, sort_keys=True))
PY

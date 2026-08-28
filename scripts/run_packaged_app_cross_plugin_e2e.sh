#!/usr/bin/env bash
set -euo pipefail

APP_PATH="${ACROSS_PACKAGED_APP_PATH:-/Applications/Across Agents Assistant.app}"
BACKEND_PATH="$APP_PATH/Contents/Resources/backend"
if [[ -d "$BACKEND_PATH" ]]; then
  BACKEND_PATH="$BACKEND_PATH/backend"
fi
TMP_DIR="$(mktemp -d /tmp/across-packaged-cross-plugin.XXXXXX)"
ACROSS_HOME="$TMP_DIR/across"
ACROSS_AGENTS_HOME="$TMP_DIR/aaa"
SOCKET_PATH="$ACROSS_AGENTS_HOME/run/across-agents.sock"
BACKEND_PID=""

cleanup() {
  local status="$?"
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ "$status" -ne 0 && -f "$TMP_DIR/backend.log" ]]; then
    echo "Packaged backend tail:" >&2
    tail -80 "$TMP_DIR/backend.log" >&2 || true
  fi
  rm -rf "$TMP_DIR"
  exit "$status"
}
trap cleanup EXIT

if [[ ! -x "$BACKEND_PATH" ]]; then
  echo "Packaged AAA backend is missing: $BACKEND_PATH" >&2
  exit 2
fi

mkdir -p "$TMP_DIR/project" "$TMP_DIR/tmp"
cat > "$TMP_DIR/project/package.json" <<'JSON'
{
  "name": "across-packaged-cross-plugin-fixture",
  "version": "1.0.0",
  "license": "MIT"
}
JSON

(
  cd "$TMP_DIR/project"
  ACROSS_HOME="$ACROSS_HOME" \
  ACROSS_AGENTS_HOME="$ACROSS_AGENTS_HOME" \
  TMPDIR="$TMP_DIR/tmp" \
  ACROSS_AAA_CANDIDATE_RETENTION=0 \
    "$BACKEND_PATH" > "$TMP_DIR/backend.log" 2>&1
) &
BACKEND_PID="$!"

for _ in $(seq 1 120); do
  if [[ -S "$SOCKET_PATH" ]] && /usr/bin/curl \
    --fail --silent --show-error --max-time 2 \
    --unix-socket "$SOCKET_PATH" \
    http://localhost/api/health > "$TMP_DIR/health.json"; then
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Packaged backend exited before becoming healthy." >&2
    exit 1
  fi
  sleep 0.25
done
if [[ ! -s "$TMP_DIR/health.json" ]]; then
  echo "Isolated packaged backend did not become healthy." >&2
  exit 1
fi

request() {
  local method="$1"
  local endpoint="$2"
  local output="$3"
  local body="${4:-}"
  local arguments=(
    --fail --silent --show-error --max-time 600
    --unix-socket "$SOCKET_PATH"
    -X "$method"
  )
  if [[ -n "$body" ]]; then
    arguments+=( -H 'Content-Type: application/json' --data "$body" )
  fi
  /usr/bin/curl "${arguments[@]}" "http://localhost$endpoint" > "$output"
}

for plugin_id in across-context across-orchestrator across-autopilot; do
  request POST "/api/plugins/$plugin_id/actions" "$TMP_DIR/$plugin_id-install.json" '{"action":"install"}'
done
for action in repair upgrade; do
  for plugin_id in across-context across-orchestrator across-autopilot; do
    request POST "/api/plugins/$plugin_id/actions" "$TMP_DIR/$plugin_id-$action.json" "{\"action\":\"$action\"}"
  done
done
for plugin_id in across-context across-orchestrator across-autopilot; do
  request POST "/api/plugins/$plugin_id/actions" "$TMP_DIR/$plugin_id-uninstall.json" '{"action":"uninstall"}'
  request POST "/api/plugins/$plugin_id/actions" "$TMP_DIR/$plugin_id-reinstall.json" '{"action":"install"}'
done
request GET '/api/plugins?probe=true' "$TMP_DIR/plugins.json"
cat > "$TMP_DIR/goal-probe-request.json" <<'JSON'
{
  "contract": {
    "schema_version": "across-goal-contract/1.0",
    "goal_id": "goal-packaged-cross-plugin",
    "revision": 1,
    "task_id": "task-packaged-cross-plugin",
    "statement": "Verify the installed managed-plugin Goal Contract boundary.",
    "success_outcome": "Every installed plugin returns the same Goal binding and evidence hash.",
    "scope": {"includes": ["installed plugin verification"], "excludes": ["release", "promotion"]},
    "acceptance_criteria": [
      {
        "criterion_id": "criterion-packaged-cross-plugin",
        "description": "Installed plugin probes return an identical binding.",
        "required": true,
        "validator_kind": "installed_contract_probe",
        "review_policy": "automatic",
        "source": "user_confirmed"
      }
    ],
    "dependencies": [],
    "execution_profile": "orchestrated",
    "source": "user",
    "confirmed_by": "human:user",
    "confirmed_at": "2026-08-28T00:00:00Z",
    "created_at": "2026-08-28T00:00:00Z"
  },
  "allow_missing": false
}
JSON
GOAL_PROBE_BODY="$(tr -d '\n' < "$TMP_DIR/goal-probe-request.json")"
request POST '/api/goal-contract/plugin-probe' "$TMP_DIR/goal-probe.json" "$GOAL_PROBE_BODY"
request POST '/api/autopilot/runs' "$TMP_DIR/run.json" '{"spec":"aaa-release-readiness-gate","trigger":"packaged-cross-plugin-e2e"}'

TMP_DIR="$TMP_DIR" python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path


root = Path(os.environ["TMP_DIR"])
plugins = {
    item.get("plugin_id"): item
    for item in json.loads((root / "plugins.json").read_text(encoding="utf-8")).get("plugins", [])
}
for plugin_id in ("across-context", "across-orchestrator", "across-autopilot"):
    plugin = plugins.get(plugin_id, {})
    if not all(plugin.get(key) is True for key in ("installed", "available", "integrity_ok", "probe")):
        raise SystemExit(f"{plugin_id} did not converge through install, integrity, and probe.")

payload = json.loads((root / "run.json").read_text(encoding="utf-8"))
goal_probe = json.loads((root / "goal-probe.json").read_text(encoding="utf-8"))
if goal_probe.get("status") != "passed" or set(goal_probe.get("plugins", {})) != {
    "across-context", "across-orchestrator", "across-autopilot"
}:
    raise SystemExit("Installed managed plugins did not return a complete Goal Contract probe matrix.")
bindings = [goal_probe.get("goal_contract", {}), *goal_probe.get("plugins", {}).values()]
if any(binding != bindings[0] for binding in bindings[1:]):
    raise SystemExit("Installed managed plugins returned mismatched Goal Contract bindings.")
run = payload.get("run", {})
evidence = payload.get("evidence", {})
if run.get("status") != "completed" or evidence.get("status") != "completed":
    raise SystemExit("The packaged Autopilot -> Orchestrator -> Context workflow did not complete.")
if not run.get("orchestrator_tasks"):
    raise SystemExit("The packaged workflow did not produce an Orchestrator task.")
if not run.get("memory_ids"):
    raise SystemExit("The packaged workflow did not produce a pending Context memory record.")
actions = {item.get("adapter"): item for item in evidence.get("actions", [])}
for action_id in ("orchestrator_task_dispatch", "memory_write_candidate"):
    if actions.get(action_id, {}).get("status") != "passed":
        raise SystemExit(f"Packaged cross-plugin action failed: {action_id}")

print(json.dumps({
    "status": "passed",
    "runtime": "formal-packaged-backend-isolated-profile",
    "plugin_convergence": "passed",
    "plugin_lifecycle_install_repair_upgrade_uninstall_reinstall": "passed",
    "goal_contract_probe": "passed",
    "autopilot_to_orchestrator": "passed",
    "orchestrator_to_context": "passed",
    "cleanup": "trap-enforced",
}, indent=2, sort_keys=True))
PY

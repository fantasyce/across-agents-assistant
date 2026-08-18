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
request GET '/api/plugins?probe=true' "$TMP_DIR/plugins.json"
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
    "autopilot_to_orchestrator": "passed",
    "orchestrator_to_context": "passed",
    "cleanup": "trap-enforced",
}, indent=2, sort_keys=True))
PY

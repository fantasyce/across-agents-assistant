#!/usr/bin/env bash
set -euo pipefail

APP_PATH="${ACROSS_PACKAGED_APP_PATH:-/Applications/Across Agents Assistant.app}"
SOCKET_PATH="${ACROSS_AGENTS_SOCKET:-$HOME/.across/run/across-agents-assistant/across-agents.sock}"
PAYLOAD_MANIFEST="$APP_PATH/Contents/Resources/plugin-payloads/manifest.json"
TMP_DIR="$(mktemp -d /tmp/across-packaged-vnext.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ ! -f "$PAYLOAD_MANIFEST" ]]; then
  echo "Packaged plugin payload manifest is missing." >&2
  exit 1
fi

for _ in $(seq 1 80); do
  if [[ -S "$SOCKET_PATH" ]] && /usr/bin/curl \
    --fail --silent --show-error --max-time 2 \
    --unix-socket "$SOCKET_PATH" \
    http://localhost/api/health > "$TMP_DIR/health.json"; then
    break
  fi
  sleep 0.25
done
if [[ ! -s "$TMP_DIR/health.json" ]]; then
  echo "Packaged AAA backend did not become healthy." >&2
  exit 1
fi

request() {
  local method="$1"
  local endpoint="$2"
  local output="$3"
  local body="${4:-}"
  local arguments=(
    --fail --silent --show-error --max-time 120
    --unix-socket "$SOCKET_PATH"
    -X "$method"
  )
  if [[ -n "$body" ]]; then
    arguments+=( -H 'Content-Type: application/json' --data "$body" )
  fi
  /usr/bin/curl "${arguments[@]}" "http://localhost$endpoint" > "$output"
}

# This is a local acceptance candidate, not a release. Exercise the same
# explicit one-click lifecycle action the settings UI exposes so the runtime
# under ~/.across cannot silently remain older than the newly installed app.
for plugin_id in across-context across-orchestrator across-autopilot; do
  request \
    POST \
    "/api/plugins/$plugin_id/actions" \
    "$TMP_DIR/$plugin_id-upgrade.json" \
    '{"action":"upgrade"}'
done

request GET '/api/plugins?probe=true' "$TMP_DIR/plugins.json"
request GET '/api/autopilot/no-key-demo?pattern_id=first-verified-task' "$TMP_DIR/no-key.json"
request \
  POST \
  '/api/orchestrator/contracts/execution-policy' \
  "$TMP_DIR/policy.json" \
  '{"run_id":"packaged-vnext-smoke","role":"reviewer","actions":["inspect"],"budget":{"max_model_calls":0}}'
request \
  POST \
  '/api/orchestrator/runs/replay-plan' \
  "$TMP_DIR/replay.json" \
  '{"source":{"run_id":"packaged-vnext-smoke","status":"completed","verdict":"passed","checks":{"packaged_runtime":"passed"}}}'
request GET '/api/approval-receipts/verify' "$TMP_DIR/receipts.json"

TMP_DIR="$TMP_DIR" PAYLOAD_MANIFEST="$PAYLOAD_MANIFEST" python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path


root = Path(os.environ["TMP_DIR"])
payload = json.loads(Path(os.environ["PAYLOAD_MANIFEST"]).read_text(encoding="utf-8"))
expected = {
    plugin_id: str(descriptor.get("version") or "")
    for plugin_id, descriptor in payload.get("plugins", {}).items()
}
plugins_payload = json.loads((root / "plugins.json").read_text(encoding="utf-8"))
plugins = {item.get("plugin_id"): item for item in plugins_payload.get("plugins", [])}
required = {"across-context", "across-orchestrator", "across-autopilot"}
if not required.issubset(plugins):
    raise SystemExit("Packaged plugin registry is incomplete.")
for plugin_id in sorted(required):
    item = plugins[plugin_id]
    if str(item.get("version") or "") != expected.get(plugin_id):
        raise SystemExit(f"{plugin_id} runtime version does not match its bundled payload.")
    if not all(item.get(key) is True for key in ("installed", "available", "integrity_ok")):
        raise SystemExit(f"{plugin_id} runtime is not installed, available, and verified.")
    if item.get("integrity_issues"):
        raise SystemExit(f"{plugin_id} runtime has integrity issues.")

no_key = json.loads((root / "no-key.json").read_text(encoding="utf-8"))
if no_key.get("schema_version") != "across-no-key-demo/1.0":
    raise SystemExit("Packaged Autopilot no-key contract is unavailable.")
policy = json.loads((root / "policy.json").read_text(encoding="utf-8"))
if policy.get("schema_version") != "across-execution-policy/1.0":
    raise SystemExit("Packaged execution policy contract is unavailable.")
if policy.get("model_policy", {}).get("credentials_included") is not False:
    raise SystemExit("Packaged execution policy exposed model credentials.")
replay = json.loads((root / "replay.json").read_text(encoding="utf-8"))
if replay.get("schema_version") != "across-replay-plan/1.0":
    raise SystemExit("Packaged replay plan contract is unavailable.")
execution = replay.get("execution", {})
if execution.get("performed") is not False or execution.get("side_effects_repeated") is not False:
    raise SystemExit("Packaged replay plan performed an action.")
receipts = json.loads((root / "receipts.json").read_text(encoding="utf-8"))
if receipts.get("integrity_status") != "verified":
    raise SystemExit("Packaged approval receipt chain failed verification.")

print(json.dumps({
    "app_runtime": "healthy",
    "plugins": {plugin_id: expected[plugin_id] for plugin_id in sorted(required)},
    "no_key_demo": "available",
    "execution_policy": "available",
    "safe_replay": "non_executing",
    "approval_receipts": "verified",
}, ensure_ascii=False, sort_keys=True))
PY

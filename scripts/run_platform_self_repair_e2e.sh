#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_ROOT="${ACROSS_ORCHESTRATOR_SOURCE:-"$ROOT_DIR/../across-orchestrator"}"
CONTEXT_ROOT="${ACROSS_CONTEXT_SOURCE:-"$ROOT_DIR/../across-context"}"
AUTOPILOT_ROOT="${ACROSS_AUTOPILOT_SOURCE:-"$ROOT_DIR/../across-autopilot"}"
UV_BIN="${UV_BIN:-}"
HOST_CREDENTIALS_FILE="${ACROSS_AGENTS_CREDENTIALS_FILE:-"$HOME/.across/data/across-agents-assistant/credentials.json"}"
RUN_REPAIR="${PLATFORM_SELF_REPAIR_E2E_RUN_REPAIR:-1}"
REQUEST_TIMEOUT_SECONDS="${PLATFORM_SELF_REPAIR_E2E_TIMEOUT_SECONDS:-1800}"

if [[ -z "$UV_BIN" ]]; then
  if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
  elif [[ -x /opt/homebrew/bin/uv ]]; then
    UV_BIN="/opt/homebrew/bin/uv"
  else
    echo "uv is required for the Platform Self-Repair E2E." >&2
    exit 1
  fi
fi

for dir in "$ORCHESTRATOR_ROOT" "$CONTEXT_ROOT" "$AUTOPILOT_ROOT"; do
  if [[ ! -d "$dir" ]]; then
    echo "Missing required Across product checkout: $dir" >&2
    exit 1
  fi
done

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/across-platform-self-repair-e2e.XXXXXX")"
cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  if [[ "${KEEP_PLATFORM_SELF_REPAIR_E2E_HOME:-0}" != "1" ]]; then
    rm -rf "$TMP_ROOT"
  else
    echo "Preserved E2E home: $TMP_ROOT"
  fi
}
trap cleanup EXIT

ACROSS_HOME="$TMP_ROOT/across"
mkdir -p "$ACROSS_HOME"

echo "== Preparing source mirrors =="
ACROSS_HOME="$ACROSS_HOME" \
ACROSS_LOOP_SOURCE_ROOT="$(cd "$ROOT_DIR/.." && pwd)" \
bash "$ROOT_DIR/scripts/prepare_loop_engineering_sources.sh" \
  > "$TMP_ROOT/source-mirrors.log"

echo "== Installing managed plugin runtimes =="
node "$CONTEXT_ROOT/src/cli.js" install host-plugin --across-home "$ACROSS_HOME" --json > "$TMP_ROOT/context-install.json"
node "$AUTOPILOT_ROOT/src/cli.js" install host-plugin --across-home "$ACROSS_HOME" --json > "$TMP_ROOT/autopilot-install.json"

PORT="$(
  python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"
BASE_URL="http://127.0.0.1:$PORT"
ORCHESTRATOR_COMMAND_JSON="$(
  python3 - "$UV_BIN" "$ORCHESTRATOR_ROOT" <<'PY'
import json
import sys
uv, root = sys.argv[1], sys.argv[2]
print(json.dumps([uv, "run", "--project", root, "--python", "3.12", "python", "-m", "across_orchestrator.cli"]))
PY
)"

SELF_REPAIR_CASE_SPEC="$TMP_ROOT/platform-self-repair-router-case.loop.json"
python3 - "$SELF_REPAIR_CASE_SPEC" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
spec = {
    "schema_version": "across-loop-spec/1.0",
    "id": "aaa-platform-self-repair-router-case",
    "name": "AAA Platform Self Repair Router Case",
    "description": "A minimized E2E fixture that fails inside loop-engineering supervision and must enqueue aaa-platform-self-repair.",
    "owner": {"type": "local_user", "id": "e2e"},
    "compatibility": {
        "min_autopilot_version": ">=0.2.9",
        "required_orchestrator": ">=0.7.0",
        "required_context": ">=0.8.0",
        "required_host": ">=0.9.0",
    },
    "required_capabilities": [
        "source.manual_input",
        "action.host_code_iteration",
        "output.json_artifact",
        "memory.pending_summary",
        "runtime.platform_self_repair",
    ],
    "trigger": {"type": "daemon"},
    "scope": {"project_id": "across", "workspace": "."},
    "autonomy": {"level": 3, "requires_human_approval_above": 3},
    "sources": [
        {
            "id": "self-repair-router-case",
            "type": "manual_input",
            "adapter": "manual_input",
            "title": "Self-repair router case",
            "content": "This fixture intentionally runs host_code_iteration before candidate_ecosystem_acquire so the supervisor records a failed platform case and must enqueue aaa-platform-self-repair.",
        }
    ],
    "actions": {
        "allowed": ["host_code_iteration", "report_generation", "write_pending_memory"],
        "blocked": ["merge_pr", "release_publish", "sign_artifact", "write_secret"],
    },
    "execute": {"engine": "across-orchestrator", "mode": "task"},
    "outputs": [{"type": "json_artifact", "to": "run://platform-self-repair-router-case/evidence.json", "policy": "overwrite"}],
    "gates": [],
    "memory": {"provider": "across-context", "recall": False, "remember": False, "write_status": "pending"},
    "failure_policy": {
        "max_retries": 0,
        "retry_backoff": "linear",
        "continue_on_gate_failure": False,
        "dead_letter": "context_memory",
        "platform_self_repair": {
            "enabled": True,
            "repair_spec": "aaa-platform-self-repair",
            "promotion_only": True,
        },
    },
    "sandbox": {"filesystem": "run_scoped", "network": "adapter_scoped", "env": "minimal"},
    "runtime_policy": {
        "risk_profile": "high",
        "timeouts": {"total_run_timeout_ms": 600000, "adapter_timeout_ms": 120000, "model_timeout_ms": 120000},
        "budget": {"max_model_calls": 2, "max_candidate_repairs": 1, "max_usd": 0},
        "network_policy": {"mode": "adapter_scoped", "allowlist": []},
        "filesystem_policy": {"mode": "run_scoped", "allowlist_roots": []},
        "promotion": {"human_approval_required": True, "merge_release_signing_blocked": True},
    },
    "evidence_contract": {
        "schema_version": "across-loop-evidence/1.0",
        "required_sections": ["sources", "actions", "gates", "outputs", "memory", "audit"],
    },
    "used_adapters": {
        "sources": ["manual_input"],
        "actions": ["host_code_iteration"],
        "outputs": ["json_artifact"],
    },
    "pack_config": {
        "target_repo": "across-autopilot",
        "platform_self_repair": {"enabled": True, "repair_spec": "aaa-platform-self-repair", "promotion_only": True},
        "model_policy": {"required": True, "provider": "minimax", "model": "MiniMax-M3", "direct_patches": True},
    },
    "model_policy": {"required": True, "provider": "minimax", "model": "MiniMax-M3", "direct_patches": True},
}
path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "== Starting AAA backend =="
env \
  "PYTHONPATH=$ROOT_DIR/backend/src" \
  "ACROSS_HOME=$ACROSS_HOME" \
  "ACROSS_AUTOPILOT_SOURCE_MIRRORS_DIR=$ACROSS_HOME/data/across-autopilot/source-mirrors" \
  "ACROSS_AGENTS_CREDENTIALS_FILE=$HOST_CREDENTIALS_FILE" \
  "ACROSS_AAA_HOST_HTTP_URL=$BASE_URL" \
  "ACROSS_CONTEXT_COMMAND=$ACROSS_HOME/bin/across-context" \
  "ACROSS_ORCHESTRATOR_COMMAND=$ORCHESTRATOR_COMMAND_JSON" \
  "$UV_BIN" run \
  --with-requirements "$ROOT_DIR/backend/requirements_no_pyobjc.txt" \
  --python 3.12 \
  python -m uvicorn across_agents_assistant.api_server:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  > "$TMP_ROOT/aaa-backend.log" 2>&1 &
SERVER_PID="$!"

echo "== Waiting for AAA backend =="
python3 - "$BASE_URL" <<'PY'
import sys
import time
import urllib.request

base = sys.argv[1]
deadline = time.time() + 60
last = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(f"{base}/api/plugins", timeout=2) as response:
            if 200 <= response.status < 300:
                sys.exit(0)
    except Exception as exc:
        last = exc
        time.sleep(0.5)
raise SystemExit(f"AAA backend did not become ready: {last}")
PY

echo "== Running platform self-repair E2E through AAA API =="
python3 - "$BASE_URL" "$SELF_REPAIR_CASE_SPEC" "$TMP_ROOT/e2e-summary.json" "$RUN_REPAIR" "$REQUEST_TIMEOUT_SECONDS" <<'PY'
import json
import pathlib
import sys
import urllib.error
import urllib.request

base = sys.argv[1].rstrip("/")
spec_path = pathlib.Path(sys.argv[2])
summary_path = pathlib.Path(sys.argv[3])
run_repair = sys.argv[4] not in {"0", "false", "False", "no"}
timeout = float(sys.argv[5])

def request(method, path, payload=None, request_timeout=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=request_timeout or timeout) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc

plugins = request("GET", "/api/plugins?probe=true", request_timeout=60)["plugins"]
autopilot = next(item for item in plugins if item["plugin_id"] == "across-autopilot")
assert autopilot["available"] is True, autopilot

registry = request("GET", "/api/autopilot/registry", request_timeout=60)
built_in_ids = {item["id"] for item in registry["built_in"]}
assert "aaa-platform-self-repair" in built_in_ids, built_in_ids

validation = request("POST", "/api/autopilot/specs/validate", {"spec": str(spec_path)}, request_timeout=60)
assert validation["valid"] is True, validation

trigger = request("POST", "/api/autopilot/triggers", {
    "spec": str(spec_path),
    "type": "daemon",
    "source": "platform-self-repair-e2e",
    "actor": "e2e",
    "idempotency_key": "platform-self-repair-e2e-router-case",
    "payload": {
        "auto_platform_self_repair": True,
        "platform_self_repair_case": {
            "category": "supervisor_gap",
            "goal": "A failed loop-engineering supervisor case must enqueue aaa-platform-self-repair and expose replay evidence.",
            "expected_after_repair": "failed trigger includes platform_self_repair evidence and a queued repair run",
        },
    },
}, request_timeout=60)
assert trigger["status"] == "pending", trigger

dispatch = request("POST", "/api/autopilot/triggers/run", {"trigger_id": trigger["trigger_id"]}, request_timeout=timeout)
assert dispatch["status"] == "failed", dispatch
diagnosis = dispatch["trigger"]["platform_self_repair"]["diagnosis"]
assert diagnosis["eligible"] is True, diagnosis
assert diagnosis["category"] == "supervisor_gap", diagnosis
assert diagnosis["target_id"] == "autopilot-self-repair-replay-fixture", diagnosis
assert "src/platform-self-repair.js" not in diagnosis["allowed_patch_paths"], diagnosis
assert "src/supervisor.js" not in diagnosis["allowed_patch_paths"], diagnosis
assert "src/candidate-ecosystem.js" not in diagnosis["allowed_patch_paths"], diagnosis
repair_trigger = dispatch["trigger"]["platform_self_repair"]["trigger"]
assert repair_trigger["spec_id"] == "aaa-platform-self-repair", repair_trigger
assert repair_trigger["status"] in {"pending", "claimed", "running"}, repair_trigger
assert repair_trigger["trigger_event"]["payload"]["target_id"] == "autopilot-self-repair-replay-fixture", repair_trigger

self_plan = request("GET", "/api/autopilot/self-iteration-plan", request_timeout=60)
assert self_plan["platform_self_repair"]["spec"] == "aaa-platform-self-repair", self_plan
assert self_plan["platform_self_repair"]["queued_count"] >= 1, self_plan

summary = {
    "schema_version": "across-platform-self-repair-e2e/1.0",
    "status": "router_passed",
    "failed_trigger_id": trigger["trigger_id"],
    "failed_run_id": dispatch["run"]["run_id"],
    "repair_trigger_id": repair_trigger["trigger_id"],
    "diagnosis": diagnosis,
}

if run_repair:
    repair_dispatch = request("POST", "/api/autopilot/triggers/run", {"trigger_id": repair_trigger["trigger_id"]}, request_timeout=timeout)
    assert repair_dispatch["status"] == "completed", repair_dispatch
    repair_run = repair_dispatch["run"]
    repair_evidence = repair_dispatch["evidence"]
    assert repair_run["status"] == "completed", repair_run
    assert repair_evidence["spec_id"] == "aaa-platform-self-repair", repair_evidence
    assert all(gate["status"] == "passed" for gate in repair_evidence["gates"] if gate.get("required")), repair_evidence["gates"]
    strategy_action = next(action for action in repair_evidence["actions"] if action["adapter"] == "product_iteration_strategy")
    selected = strategy_action["result"]["selected_iteration"]
    assert selected["target_id"] == "autopilot-self-repair-replay-fixture", selected
    assert selected["target_repo"] == "across-autopilot", selected
    candidate = repair_evidence["candidate"]
    assert candidate["changed_file_count"] > 0, candidate
    allowed = {f"across-autopilot/{path}" for path in selected["allowed_patch_paths"]}
    changed = set(candidate["changed_files"])
    assert changed.issubset(allowed), {"changed": sorted(changed), "allowed": sorted(allowed)}
    assert "across-autopilot/src/platform-self-repair.js" not in changed, sorted(changed)
    assert "across-autopilot/tests/platform-self-repair.test.js" in changed, sorted(changed)
    assert candidate["promotion_package"]["human_approval_required"] is True, candidate["promotion_package"]
    promotion = request("GET", f"/api/autopilot/runs/{repair_run['run_id']}/promotion-review", request_timeout=60)
    assert promotion["promotion_attestation"]["merge_release_signing_blocked"] is True, promotion
    summary.update({
        "status": "passed",
        "repair_run_id": repair_run["run_id"],
        "repair_candidate_id": candidate["candidate_id"],
        "repair_changed_file_count": candidate["changed_file_count"],
        "promotion_review_status": promotion["status"],
    })

summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))
PY

echo "== Platform self-repair E2E summary =="
cat "$TMP_ROOT/e2e-summary.json"

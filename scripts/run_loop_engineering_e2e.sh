#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_ROOT="${ACROSS_ORCHESTRATOR_SOURCE:-"$ROOT_DIR/../across-orchestrator"}"
CONTEXT_ROOT="${ACROSS_CONTEXT_SOURCE:-"$ROOT_DIR/../across-context"}"
AUTOPILOT_ROOT="${ACROSS_AUTOPILOT_SOURCE:-"$ROOT_DIR/../across-autopilot"}"
UV_BIN="${UV_BIN:-}"
HOST_CREDENTIALS_FILE="${ACROSS_AGENTS_CREDENTIALS_FILE:-"$HOME/.across/data/across-agents-assistant/credentials.json"}"
LOOP_ENGINEERING_SPEC_ID="${LOOP_ENGINEERING_SPEC_ID:-aaa-autonomous-self-iteration}"
LOOP_ENGINEERING_EXPECTED_CHANGED_FILES="${LOOP_ENGINEERING_EXPECTED_CHANGED_FILES:-any}"
LOOP_ENGINEERING_VERIFY_CANDIDATE_APP="${LOOP_ENGINEERING_VERIFY_CANDIDATE_APP:-0}"
LOOP_ENGINEERING_RUN_TIMEOUT_SECONDS="${LOOP_ENGINEERING_RUN_TIMEOUT_SECONDS:-1200}"

if [[ -z "$UV_BIN" ]]; then
  if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
  elif [[ -x /opt/homebrew/bin/uv ]]; then
    UV_BIN="/opt/homebrew/bin/uv"
  else
    echo "uv is required for the Loop Engineering E2E." >&2
    exit 1
  fi
fi

for dir in "$ORCHESTRATOR_ROOT" "$CONTEXT_ROOT" "$AUTOPILOT_ROOT"; do
  if [[ ! -d "$dir" ]]; then
    echo "Missing required Across product checkout: $dir" >&2
    exit 1
  fi
done

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/across-loop-engineering-e2e.XXXXXX")"
cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  if [[ "${KEEP_LOOP_ENGINEERING_E2E_HOME:-0}" != "1" ]]; then
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

echo "== Starting AAA backend =="
SOURCE_ENV=("ACROSS_AUTOPILOT_SOURCE_MIRRORS_DIR=$ACROSS_HOME/data/across-autopilot/source-mirrors")
if [[ "${ACROSS_LOOP_E2E_USE_SOURCE_CHECKOUT:-0}" == "1" ]]; then
  SOURCE_ENV+=(
    "ACROSS_AGENTS_ASSISTANT_SOURCE=$ROOT_DIR"
    "ACROSS_ORCHESTRATOR_SOURCE=$ORCHESTRATOR_ROOT"
    "ACROSS_CONTEXT_SOURCE=$CONTEXT_ROOT"
    "ACROSS_AUTOPILOT_SOURCE=$AUTOPILOT_ROOT"
  )
fi
env \
  "PYTHONPATH=$ROOT_DIR/backend/src" \
  "ACROSS_HOME=$ACROSS_HOME" \
  "${SOURCE_ENV[@]}" \
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

echo "== Running user-level Loop Engineering workflow through AAA API =="
python3 - "$BASE_URL" "$TMP_ROOT/e2e-summary.json" "$LOOP_ENGINEERING_SPEC_ID" "$LOOP_ENGINEERING_EXPECTED_CHANGED_FILES" "$LOOP_ENGINEERING_RUN_TIMEOUT_SECONDS" <<'PY'
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

base = sys.argv[1].rstrip("/")
summary_path = pathlib.Path(sys.argv[2])
spec_id = sys.argv[3]
expected_raw = sys.argv[4].strip()
request_timeout = float(sys.argv[5])
expected_changed_files = [] if expected_raw in {"*", "any"} else [item.strip() for item in expected_raw.split(",") if item.strip()]

def request(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=request_timeout) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc

plugins = request("GET", "/api/plugins?probe=true")["plugins"]
plugin_ids = {item["plugin_id"] for item in plugins}
assert {"across-context", "across-orchestrator", "across-autopilot"}.issubset(plugin_ids), plugin_ids
autopilot = next(item for item in plugins if item["plugin_id"] == "across-autopilot")
assert autopilot["available"] is True, autopilot

registry = request("GET", "/api/autopilot/registry")
built_in_ids = {item["id"] for item in registry["built_in"]}
assert {"daily-news-brief", spec_id}.issubset(built_in_ids), built_in_ids

capability_pack = request("GET", "/api/autopilot/capability-packs")
ready_capabilities = {item["id"] for item in capability_pack["ready"]}
assert capability_pack["ready_count"] >= 41, capability_pack
assert {
    "trigger_management_api",
    "trigger_registry_api",
    "cron_scheduler_tick",
    "continuous_self_iteration_plan",
    "webhook_receiver",
    "daemon_file_watcher",
    "runtime_policy_contract",
    "capability_preflight",
    "runtime_budget_enforcement",
    "source_research_digest",
    "repo_quality_inspection",
    "dependency_security_review",
    "license_policy_scan",
    "model_generated_fallback_plan",
    "multi_candidate_comparison",
    "candidate_quality_gate_expansion",
    "distinct_model_acceptance",
    "promotion_source_ref_pinning",
    "promotion_review_packet",
    "promotion_human_review",
    "promotion_attestation",
    "ops_dashboard",
    "unified_capability_registry",
    "registry_health_compatibility",
    "cleanup_retention",
    "solidified_e2e_gate",
    "loop_capability_audit_skill",
    "e2e_failure_triage_skill",
}.issubset(ready_capabilities), capability_pack

unified_registry = request("GET", "/api/capability-registry")
assert unified_registry["schema_version"] == "across-unified-capability-registry/1.0", unified_registry
assert unified_registry["security"]["secrets_included"] is False, unified_registry["security"]
assert unified_registry["security"]["credential_fields_redacted"] is True, unified_registry["security"]
assert unified_registry["security"]["execution_boundaries_preserved"] is True, unified_registry["security"]
assert unified_registry["integration_policy"]["frontend_pages_can_remain_separate"] is True, unified_registry["integration_policy"]
unified_provider_ids = {provider["id"] for provider in unified_registry["providers"]}
assert {"across-agents-assistant", "across-autopilot"}.issubset(unified_provider_ids), unified_provider_ids
unified_capabilities = {item["id"]: item for item in unified_registry["capabilities"]}
fallback_pack = unified_capabilities["autopilot.tool_pack.model_generated_fallback_plan"]
assert fallback_pack["executor"] == "across-autopilot", fallback_pack
assert fallback_pack["provider"] == "across-autopilot", fallback_pack
assert fallback_pack["loop_callable"] is True, fallback_pack
assert fallback_pack["user_callable"] is False, fallback_pack
assert any(
    item["kind"] == "tool" and item["provider"] == "across-agents-assistant"
    for item in unified_registry["capabilities"]
), unified_registry["capabilities"]
assert any(
    item["provider"] == "minimax" and item["model"] == "MiniMax-M3"
    for item in unified_registry["models"]
), unified_registry["models"]
registry_health = request("GET", "/api/capability-registry/health")
assert registry_health["status"] == "passed", registry_health
assert registry_health["compatibility"]["schema_family"] == "across-unified-capability-registry", registry_health

self_iteration_initial = request("GET", "/api/autopilot/self-iteration-plan")
assert self_iteration_initial["schema_version"] == "across-aaa-self-iteration-plan/1.0", self_iteration_initial
self_iteration_plan = request("POST", "/api/autopilot/self-iteration-plan/ensure", {
    "spec": spec_id,
    "interval_seconds": 3600,
    "enabled": True,
    "actor": "e2e",
    "source": "aaa-loop-e2e",
})
assert self_iteration_plan["status"] == "active", self_iteration_plan
assert self_iteration_plan["ready"] is True, self_iteration_plan
assert self_iteration_plan["trigger"]["spec"] == spec_id, self_iteration_plan

validation = request("POST", "/api/autopilot/specs/validate", {"spec": spec_id})
assert validation["valid"] is True, validation

dry_run = request("POST", "/api/autopilot/specs/dry-run", {"spec": spec_id})
assert dry_run["valid"] is True, dry_run
assert dry_run["capability_preflight"]["status"] == "passed", dry_run["capability_preflight"]
assert dry_run["runtime_policy"]["promotion"]["human_approval_required"] is True, dry_run["runtime_policy"]
assert "source_digest" in dry_run["used_adapters"]["actions"], dry_run
assert "host_code_iteration" in dry_run["used_adapters"]["actions"], dry_run
assert "candidate_self_hosting_probe" in dry_run["used_adapters"]["actions"], dry_run
assert "semantic_alignment_review" in dry_run["used_adapters"]["actions"], dry_run

cron_config = request("POST", "/api/autopilot/trigger-configs", {
    "spec": spec_id,
    "type": "cron",
    "payload": {"reason": "solidified-e2e-cron"},
    "schedule": {"interval_seconds": 3600},
    "source": "aaa-e2e",
    "actor": "e2e",
})
assert cron_config["type"] == "cron", cron_config
trigger_tick = request("POST", "/api/autopilot/trigger-configs/tick")
assert trigger_tick["status"] in {"enqueued", "idle"}, trigger_tick
trigger_configs = request("GET", "/api/autopilot/trigger-configs")
assert any(item["trigger_id"] == cron_config["trigger_id"] for item in trigger_configs["triggers"]), trigger_configs

webhook_config = request("POST", "/api/autopilot/trigger-configs", {
    "spec": spec_id,
    "type": "webhook",
    "payload": {"reason": "solidified-e2e-webhook"},
    "source": "aaa-e2e-webhook",
    "actor": "e2e",
})
webhook_receipt = request("POST", f"/api/autopilot/webhooks/{urllib.parse.quote(webhook_config['trigger_id'])}", {
    "event": "solidified-e2e",
    "spec": spec_id,
})
assert webhook_receipt["status"] == "accepted", webhook_receipt

run_payload = request("POST", "/api/autopilot/runs", {
    "spec": spec_id,
    "trigger": "user-e2e",
    "model_policy_overrides": {
        "builder": {"agent_id": "codex", "provider": "local-agent", "model": "codex"},
        "reviewer": {"agent_id": "codex", "provider": "local-agent", "model": "codex", "require_distinct_from_builder": False},
    },
})
run = run_payload["run"]
evidence = run_payload["evidence"]
run_id = run["run_id"]

assert run["status"] == "completed", run
assert evidence["schema_version"] == "across-loop-evidence/1.0", evidence
assert evidence["status"] == "completed", evidence
assert evidence["runtime_budget"]["status"] == "passed", evidence["runtime_budget"]
assert evidence["runtime_budget"]["enforcement"] == "hard", evidence["runtime_budget"]
assert evidence["gates"] and all(gate["status"] == "passed" for gate in evidence["gates"] if gate.get("required")), evidence["gates"]
gate_ids = {gate["id"] for gate in evidence["gates"]}
if spec_id == "aaa-autonomous-self-iteration":
    assert {"dynamic_backlog_ready", "independent_reviewer_passed", "distinct_reviewer_model_passed"}.issubset(gate_ids), evidence["gates"]
candidate = evidence["candidate"]
assert candidate["four_repo_manifest"] is True, candidate
assert candidate["changed_file_count"] >= 2, candidate
assert candidate["model"]["backed"] is True, candidate
assert candidate["model"]["name"], candidate
if spec_id == "aaa-autonomous-self-iteration":
    strategy = candidate.get("research_strategy") or {}
    reviewer = candidate.get("independent_reviewer") or {}
    assert strategy.get("autonomous") is True, strategy
    assert strategy.get("dynamic_backlog_count", 0) >= 2, strategy
    assert strategy.get("tool_packs"), strategy
    assert reviewer.get("independent") is True, reviewer
    assert reviewer.get("model_backed") is True, reviewer
    separation = reviewer.get("model_separation") or {}
    assert separation.get("required") is False, separation
    assert separation.get("status") == "not_required", separation
    builder_model = (candidate["model"].get("provider"), candidate["model"].get("name"))
    reviewer_model = (reviewer.get("provider"), reviewer.get("model"))
    assert all(builder_model) and all(reviewer_model), {"builder": builder_model, "reviewer": reviewer_model}
    assert builder_model == ("local-agent", "codex"), {"builder": builder_model}
    assert reviewer_model == ("local-agent", "codex"), {"reviewer": reviewer_model}
assert candidate["self_hosting_probe"]["required"] is True, candidate
assert candidate["self_hosting_probe"]["status"] == "passed", candidate
candidate_app_lifecycle = candidate.get("candidate_app_lifecycle") or {}
assert candidate_app_lifecycle.get("status") == "passed", candidate_app_lifecycle
candidate_llm_status = candidate_app_lifecycle.get("llm_status") or {}
assert candidate_llm_status.get("available") is True, candidate_llm_status
assert candidate_llm_status.get("availability_source") == "candidate_model_lease", candidate_llm_status
candidate_lease_status = candidate_llm_status.get("candidate_model_lease") or {}
assert candidate_lease_status.get("secrets_included") is False, candidate_lease_status
assert candidate_lease_status.get("raw_credentials_allowed") is False, candidate_lease_status
assert candidate["semantic_alignment_status"] == "passed", candidate
assert candidate["promotion_ready"] is True, candidate
for expected in expected_changed_files:
    assert expected in candidate["changed_files"], candidate
manifest_path = pathlib.Path(candidate["manifest_path"])
assert ".across" in str(manifest_path) or "across-loop-engineering-e2e" in str(manifest_path), manifest_path
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
source_paths = [repo["source"] for repo in manifest["repos"]]
assert source_paths and all("/source-mirrors/" in path for path in source_paths), source_paths
assert evidence["memory"]["written"][0]["status"] == "accepted_pending", evidence["memory"]
output_ids = {output["id"] for output in evidence["outputs"]}
assert {"markdown_report", "json_artifact"}.issubset(output_ids), output_ids
for output in evidence["outputs"]:
    path = output.get("path")
    if path:
        assert pathlib.Path(path).is_file(), path

status = request("GET", f"/api/autopilot/runs/{urllib.parse.quote(run_id)}")
assert status["status"] == "completed", status

evidence_again = request("GET", f"/api/autopilot/runs/{urllib.parse.quote(run_id)}/evidence")
assert evidence_again["run_id"] == run_id, evidence_again
promotion_review = request("GET", f"/api/autopilot/runs/{urllib.parse.quote(run_id)}/promotion-review")
assert promotion_review["schema_version"] == "across-autopilot-promotion-review/1.0", promotion_review
assert promotion_review["human_approval_required"] is True, promotion_review
assert promotion_review["source_ref_pins"]["status"] == "passed", promotion_review
assert len(promotion_review["source_ref_pins"]["repos"]) >= 4, promotion_review
assert any(item["id"] == "source_refs_pinned" and item["status"] == "passed" for item in promotion_review["checklist"]), promotion_review
assert promotion_review["promotion_attestation"]["digest_status"] == "passed", promotion_review
assert promotion_review["promotion_attestation"]["merge_release_signing_blocked"] is True, promotion_review
assert any(item["id"] == "promotion_attestation_present" and item["status"] == "passed" for item in promotion_review["checklist"]), promotion_review
assert promotion_review["allowed_actions"]["merge"] is False, promotion_review
assert promotion_review["allowed_actions"]["release"] is False, promotion_review

events = request("GET", f"/api/autopilot/runs/{urllib.parse.quote(run_id)}/events")
assert isinstance(events, list) and len(events) >= 10, events
assert (events[-1].get("event") or events[-1].get("type")) == "run_completed", events[-1]

runs = request("GET", "/api/autopilot/runs")
assert any(item["run_id"] == run_id for item in runs["runs"]), runs

telemetry = request("GET", "/api/autopilot/telemetry")
assert telemetry["run_count"] >= 1, telemetry
assert telemetry["by_status"]["completed"] >= 1, telemetry

ops_dashboard = request("GET", "/api/autopilot/ops-dashboard")
assert ops_dashboard["schema_version"] == "across-aaa-loop-engineering-ops-dashboard/1.0", ops_dashboard
assert ops_dashboard["summary"]["capability_ready_count"] >= 41, ops_dashboard
assert ops_dashboard["triggers"]["total"] >= 3, ops_dashboard
assert ops_dashboard["self_iteration_plan"]["status"] == "active", ops_dashboard

summary = {
    "base_url": base,
    "run_id": run_id,
    "spec_id": run["spec_id"],
    "candidate_id": candidate["candidate_id"],
    "candidate_manifest_path": candidate["manifest_path"],
    "candidate_runtime_home": candidate.get("runtime_home"),
    "candidate_app_home": candidate.get("app_home"),
    "candidate_app_dir": candidate.get("app_dir"),
    "candidate_runtime_preflight": candidate.get("runtime_preflight"),
    "events": len(events),
    "outputs": sorted(output_ids),
    "candidate_changed_files": candidate["changed_files"],
    "candidate_model": candidate["model"],
    "aaa_capability_pack_ready_count": capability_pack["ready_count"],
    "aaa_capability_pack_ready_ids": sorted(ready_capabilities),
    "unified_capability_registry": {
        "provider_count": unified_registry["summary"]["provider_count"],
        "capability_count": unified_registry["summary"]["capability_count"],
        "model_count": unified_registry["summary"]["model_count"],
        "frontend_pages_can_remain_separate": unified_registry["integration_policy"]["frontend_pages_can_remain_separate"],
        "autopilot_fallback_executor": fallback_pack["executor"],
        "health_status": registry_health["status"],
    },
    "promotion_review": {
        "status": promotion_review["status"],
        "open_review_pr": promotion_review["allowed_actions"]["open_review_pr"],
        "merge": promotion_review["allowed_actions"]["merge"],
        "release": promotion_review["allowed_actions"]["release"],
        "source_ref_pin_status": promotion_review["source_ref_pins"]["status"],
        "source_ref_pin_count": len(promotion_review["source_ref_pins"]["repos"]),
        "attestation_status": promotion_review["promotion_attestation"]["digest_status"],
        "attestation_signing_status": promotion_review["promotion_attestation"]["signing_status"],
    },
    "runtime_budget": evidence["runtime_budget"],
    "self_iteration_plan": {
        "status": self_iteration_plan["status"],
        "trigger_id": self_iteration_plan["default_trigger_id"],
        "ready": self_iteration_plan["ready"],
    },
    "ops_dashboard": {
        "status": ops_dashboard["status"],
        "trigger_count": ops_dashboard["triggers"]["total"],
        "capability_ready_count": ops_dashboard["summary"]["capability_ready_count"],
        "self_iteration_status": ops_dashboard["self_iteration_plan"]["status"],
    },
    "candidate_research_strategy": candidate.get("research_strategy"),
    "candidate_independent_reviewer": candidate.get("independent_reviewer"),
    "semantic_alignment_status": candidate["semantic_alignment_status"],
    "source_paths": source_paths,
    "self_hosting_probe": candidate["self_hosting_probe"],
    "candidate_app_lifecycle": candidate_app_lifecycle,
    "candidate_llm_status": candidate_llm_status,
    "memory_status": evidence["memory"]["written"][0]["status"],
    "telemetry_run_count": telemetry["run_count"],
}
summary["candidate_repo_path"] = next(
    repo["target"] for repo in manifest["repos"] if repo["id"] == "across-agents-assistant"
)
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))
PY

if [[ "$LOOP_ENGINEERING_VERIFY_CANDIDATE_APP" == "1" ]]; then
  echo "== Verifying Candidate App lifecycle =="
  CANDIDATE_REPO="$(
    python3 - "$TMP_ROOT/e2e-summary.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1]))["candidate_repo_path"])
PY
  )"
  CANDIDATE_ID="$(
    python3 - "$TMP_ROOT/e2e-summary.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1]))["candidate_id"])
PY
  )"
  CANDIDATE_RUNTIME_HOME="$(
    python3 - "$TMP_ROOT/e2e-summary.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1]))["candidate_runtime_home"])
PY
  )"
  CANDIDATE_APP_HOME="$(
    python3 - "$TMP_ROOT/e2e-summary.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1]))["candidate_app_home"])
PY
  )"
  ACROSS_CONTEXT_SOURCE="$CONTEXT_ROOT" \
  ACROSS_AUTOPILOT_SOURCE="$AUTOPILOT_ROOT" \
  bash "$ROOT_DIR/scripts/candidate_app_lifecycle.sh" verify \
    --candidate-repo "$CANDIDATE_REPO" \
    --candidate-id "$CANDIDATE_ID" \
    --runtime-home "$CANDIDATE_RUNTIME_HOME" \
    --app-home "$CANDIDATE_APP_HOME" \
    --output "$TMP_ROOT/candidate-app-lifecycle.json"
fi

echo "Loop Engineering E2E passed. Summary: $TMP_ROOT/e2e-summary.json"

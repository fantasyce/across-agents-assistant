#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND="${1:-verify}"
shift || true

CANDIDATE_REPO=""
CANDIDATE_ID=""
RUNTIME_HOME=""
APP_HOME=""
OUTPUT_PATH=""
ACROSS_HOME="${ACROSS_HOME:-"$HOME/.across"}"
APP_PATH=""
MAX_SOCKET_BYTES="${MAX_SOCKET_BYTES:-100}"
KEEP_RUNNING="${KEEP_CANDIDATE_APP_RUNNING:-0}"
CONTEXT_ROOT="${ACROSS_CONTEXT_SOURCE:-"$ROOT_DIR/../across-context"}"
AUTOPILOT_ROOT="${ACROSS_AUTOPILOT_SOURCE:-"$ROOT_DIR/../across-autopilot"}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --candidate-repo)
      CANDIDATE_REPO="$2"
      shift 2
      ;;
    --candidate-id)
      CANDIDATE_ID="$2"
      shift 2
      ;;
    --runtime-home)
      RUNTIME_HOME="$2"
      shift 2
      ;;
    --app-home)
      APP_HOME="$2"
      shift 2
      ;;
    --app-path)
      APP_PATH="$2"
      shift 2
      ;;
    --output)
      OUTPUT_PATH="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

safe_bundle_suffix() {
  /usr/bin/python3 - "$1" <<'PY'
import re
import sys
value = re.sub(r"[^A-Za-z0-9.-]+", "-", sys.argv[1]).strip(".-").lower()
print(value or "candidate")
PY
}

bundle_id() {
  printf 'app.acrossagents.assistant.candidate.%s\n' "$(safe_bundle_suffix "$CANDIDATE_ID")"
}

default_app_path() {
  printf '%s/data/across-autopilot/candidate-apps/%s/Across Agents Assistant Candidate.app\n' "$ACROSS_HOME" "$(safe_bundle_suffix "$CANDIDATE_ID")"
}

require_candidate_context() {
  if [[ -z "$CANDIDATE_REPO" || ! -d "$CANDIDATE_REPO" ]]; then
    echo "--candidate-repo is required and must exist." >&2
    exit 2
  fi
  if [[ -z "$CANDIDATE_ID" ]]; then
    CANDIDATE_ID="$(basename "$(cd "$CANDIDATE_REPO/.." && pwd)")"
  fi
  if [[ -z "$RUNTIME_HOME" ]]; then
    RUNTIME_HOME="$ACROSS_HOME/c/$(safe_bundle_suffix "$CANDIDATE_ID")"
  fi
  if [[ -z "$APP_HOME" ]]; then
    APP_HOME="$RUNTIME_HOME/aaa"
  fi
  if [[ -z "$APP_PATH" ]]; then
    APP_PATH="$(default_app_path)"
  fi
}

plist_set_or_add() {
  local plist="$1"
  local key="$2"
  local type="$3"
  local value="$4"
  if /usr/libexec/PlistBuddy -c "Print :$key" "$plist" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :$key $value" "$plist"
  else
    /usr/libexec/PlistBuddy -c "Add :$key $type $value" "$plist"
  fi
}

socket_path() {
  printf '%s/run/across-agents.sock\n' "$APP_HOME"
}

socket_path_bytes() {
  /usr/bin/python3 - "$1" <<'PY'
import sys
print(len(sys.argv[1].encode("utf-8")))
PY
}

extract_json_object() {
  /usr/bin/python3 -c '
import json
import sys

text = sys.stdin.read()
decoder = json.JSONDecoder()
for index, character in enumerate(text):
    if character not in "[{":
        continue
    try:
        value, _ = decoder.raw_decode(text[index:])
    except json.JSONDecodeError:
        continue
    print(json.dumps(value, separators=(",", ":")))
    raise SystemExit(0)
print("{}")
raise SystemExit(1)
'
}

json_or_default() {
  local default_json="$1"
  local parsed_json
  if parsed_json="$(extract_json_object)"; then
    printf '%s\n' "$parsed_json"
  else
    printf '%s\n' "$default_json"
  fi
}

preflight_runtime() {
  local socket bytes
  socket="$(socket_path)"
  bytes="$(socket_path_bytes "$socket")"
  if (( bytes > MAX_SOCKET_BYTES )); then
    echo "Candidate socket path is too long: $bytes > $MAX_SOCKET_BYTES: $socket" >&2
    exit 1
  fi
}

candidate_pids() {
  /bin/ps -axo pid=,command= | /usr/bin/awk -v app="$APP_PATH" '
    index($0, app "/Contents/MacOS/AcrossAgentsAssistant") > 0 { print $1 }
    index($0, app "/Contents/Resources/backend/backend") > 0 { print $1 }
  '
}

cleanup_candidate_processes() {
  local pids
  pids="$(candidate_pids || true)"
  if [[ -n "$pids" ]]; then
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && kill "$pid" >/dev/null 2>&1 || true
    done <<< "$pids"
    sleep 1
  fi
  pids="$(candidate_pids || true)"
  if [[ -n "$pids" ]]; then
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && kill -9 "$pid" >/dev/null 2>&1 || true
    done <<< "$pids"
  fi
}

crash_reports_json() {
  local marker="$1"
  local bid="$2"
  /usr/bin/python3 - "$marker" "$bid" <<'PY'
import json
import pathlib
import sys

marker = pathlib.Path(sys.argv[1])
bundle_id = sys.argv[2]
marker_time = marker.stat().st_mtime if marker.exists() else 0
reports = []
root = pathlib.Path.home() / "Library" / "Logs" / "DiagnosticReports"
for path in sorted(root.glob("AcrossAgentsAssistant-*.ips")):
    try:
        if path.stat().st_mtime <= marker_time:
            continue
        text = path.read_text(errors="replace")
    except OSError:
        continue
    if f'"bundleID":"{bundle_id}"' in text or f'"bundleID" : "{bundle_id}"' in text:
        reports.append(str(path))
print(json.dumps(reports))
PY
}

prepare_app_bundle() {
  local source_app="$CANDIDATE_REPO/build/Across Agents Assistant.app"
  if [[ "${CANDIDATE_APP_REBUILD:-0}" == "1" || ! -d "$source_app" ]]; then
    (cd "$CANDIDATE_REPO" && /usr/bin/env -u PYTHONPATH -u PYTHONHOME BACKEND_BUNDLE_MODE="${BACKEND_BUNDLE_MODE:-onedir}" SIGNING_IDENTITY="${SIGNING_IDENTITY:--}" /bin/bash ./build_app.sh)
  fi
  if [[ ! -d "$source_app" ]]; then
    echo "Candidate app bundle was not produced: $source_app" >&2
    exit 1
  fi

  mkdir -p "$(dirname "$APP_PATH")"
  rm -rf "$APP_PATH"
  /usr/bin/ditto "$source_app" "$APP_PATH"
  plist_set_or_add "$APP_PATH/Contents/Info.plist" CFBundleIdentifier string "$(bundle_id)"
  plist_set_or_add "$APP_PATH/Contents/Info.plist" CFBundleName string "Across Agents Assistant Candidate"
  plist_set_or_add "$APP_PATH/Contents/Info.plist" CFBundleDisplayName string "Across Agents Assistant Candidate"
  xattr -cr "$APP_PATH" || true
  codesign --force --deep --sign - "$APP_PATH" >/dev/null
  codesign --verify --deep --strict "$APP_PATH"
}

install_candidate_plugins() {
  mkdir -p "$APP_HOME"
  local install_env=(
    /usr/bin/env
    "ACROSS_HOME=$RUNTIME_HOME"
    "ACROSS_AGENTS_HOME=$APP_HOME"
    "ACROSS_BIN_HOME=$RUNTIME_HOME/bin"
    "ACROSS_PLUGIN_HOME=$RUNTIME_HOME/plugins"
    "ACROSS_CONTEXT_HOME=$RUNTIME_HOME/data/across-context"
    "ACROSS_AUTOPILOT_HOME=$RUNTIME_HOME/data/across-autopilot"
  )
  if [[ -d "$CONTEXT_ROOT" ]]; then
    "${install_env[@]}" node "$CONTEXT_ROOT/src/cli.js" install host-plugin --across-home "$RUNTIME_HOME" --json >/dev/null || \
      "${install_env[@]}" node "$CONTEXT_ROOT/src/cli.js" install host-plugin --across-home "$RUNTIME_HOME" >/dev/null
  fi
  if [[ -d "$AUTOPILOT_ROOT" ]]; then
    "${install_env[@]}" node "$AUTOPILOT_ROOT/src/cli.js" install host-plugin --across-home "$RUNTIME_HOME" --json >/dev/null
  fi
}

launch_and_probe() {
  local marker="$1"
  local socket="$2"
  local health_output="$3"
  local llm_status_output="$4"
  local log_dir="$RUNTIME_HOME/logs"
  local model_lease="$RUNTIME_HOME/candidate-model-lease.json"
  local raw_health raw_llm_status
  mkdir -p "$log_dir"
  rm -f "$socket"
  touch "$marker"
  local open_args=(
    -n
    -F
    "$APP_PATH"
    --stdout "$log_dir/candidate-app.stdout.log"
    --stderr "$log_dir/candidate-app.stderr.log"
    --env "ACROSS_HOME=$RUNTIME_HOME"
    --env "ACROSS_AGENTS_HOME=$APP_HOME"
    --env "ACROSS_BIN_HOME=$RUNTIME_HOME/bin"
    --env "ACROSS_PLUGIN_HOME=$RUNTIME_HOME/plugins"
  )
  if [[ -f "$model_lease" ]]; then
    open_args+=(--env "ACROSS_AAA_CANDIDATE_MODEL_LEASE=$model_lease")
  fi
  /usr/bin/open "${open_args[@]}" >/dev/null

  for _ in $(seq 1 120); do
    if [[ -S "$socket" ]]; then
      raw_health="$(/usr/bin/curl --silent --show-error --unix-socket "$socket" http://localhost/api/health)"
      printf '%s' "$raw_health" | extract_json_object > "$health_output"
      if [[ -f "$model_lease" ]]; then
        raw_llm_status="$(/usr/bin/curl --silent --show-error --unix-socket "$socket" http://localhost/api/llm/status)"
        printf '%s' "$raw_llm_status" | extract_json_object > "$llm_status_output"
        /usr/bin/python3 - "$llm_status_output" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
if payload.get("available") is not True:
    raise SystemExit("candidate model lease is not available")
if payload.get("availability_source") != "candidate_model_lease":
    raise SystemExit("candidate model lease is not the active availability source")
lease = payload.get("candidate_model_lease") or {}
if lease.get("secrets_included") is not False or lease.get("raw_credentials_allowed") is not False:
    raise SystemExit("candidate model lease status is not credential-safe")
PY
      fi
      return 0
    fi
    sleep 0.5
  done
  echo "Candidate app socket did not become ready: $socket" >&2
  return 1
}

write_result() {
  local status="$1"
  local marker="$2"
  local health_json="${3:-{}}"
  local llm_status_json="${4:-{}}"
  local cleaned_up="$5"
  local crashes
  crashes="$(crash_reports_json "$marker" "$(bundle_id)" | json_or_default '[]')"
  health_json="$(printf '%s' "$health_json" | json_or_default '{}')"
  llm_status_json="$(printf '%s' "$llm_status_json" | json_or_default '{}')"
  if [[ -n "$OUTPUT_PATH" ]]; then
    mkdir -p "$(dirname "$OUTPUT_PATH")"
    /usr/bin/python3 - "$OUTPUT_PATH" "$status" "$CANDIDATE_ID" "$(bundle_id)" "$APP_PATH" "$RUNTIME_HOME" "$APP_HOME" "$(socket_path)" "$cleaned_up" "$crashes" "$health_json" "$llm_status_json" <<'PY'
import json
import pathlib
import sys

out, status, candidate_id, bundle_id, app_path, runtime_home, app_home, socket_path, cleaned_up, crashes, health, llm_status = sys.argv[1:]
payload = {
    "schema_version": "across-candidate-app-lifecycle/1.0",
    "status": status,
    "candidate_id": candidate_id,
    "bundle_id": bundle_id,
    "app_path": app_path,
    "runtime_home": runtime_home,
    "app_home": app_home,
    "socket_path": socket_path,
    "socket_path_bytes": len(socket_path.encode("utf-8")),
    "cleaned_up": cleaned_up == "true",
    "crash_reports": json.loads(crashes),
    "health": json.loads(health),
    "llm_status": json.loads(llm_status),
}
pathlib.Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  fi
  if [[ "$crashes" != "[]" ]]; then
    echo "Candidate app produced crash report(s): $crashes" >&2
    return 1
  fi
}

if [[ "$COMMAND" == "extract-json-object" ]]; then
  extract_json_object
  exit $?
fi

if [[ "$COMMAND" == "cleanup" ]]; then
  require_candidate_context
  cleanup_candidate_processes
  exit 0
fi

if [[ "$COMMAND" != "verify" ]]; then
  echo "Usage: scripts/candidate_app_lifecycle.sh verify --candidate-repo PATH --candidate-id ID [--runtime-home PATH] [--output PATH]" >&2
  exit 2
fi

require_candidate_context
preflight_runtime
cleanup_candidate_processes
MARKER="$(mktemp "${TMPDIR:-/tmp}/across-candidate-crash-marker.XXXXXX")"
HEALTH_FILE="$(mktemp "${TMPDIR:-/tmp}/across-candidate-health.XXXXXX")"
LLM_STATUS_FILE="$(mktemp "${TMPDIR:-/tmp}/across-candidate-llm-status.XXXXXX")"
HEALTH_JSON="{}"
LLM_STATUS_JSON="{}"
CLEANED_UP="false"
cleanup() {
  if [[ "$KEEP_RUNNING" != "1" ]]; then
    cleanup_candidate_processes
    CLEANED_UP="true"
  fi
  rm -f "$MARKER" "$HEALTH_FILE" "$LLM_STATUS_FILE"
}
trap cleanup EXIT

prepare_app_bundle
install_candidate_plugins
if launch_and_probe "$MARKER" "$(socket_path)" "$HEALTH_FILE" "$LLM_STATUS_FILE"; then
  HEALTH_JSON="$(cat "$HEALTH_FILE")"
  LLM_STATUS_JSON="$(cat "$LLM_STATUS_FILE" 2>/dev/null || printf '{}')"
  if [[ "$KEEP_RUNNING" != "1" ]]; then
    cleanup_candidate_processes
    CLEANED_UP="true"
  fi
  sleep 1
  write_result "passed" "$MARKER" "$HEALTH_JSON" "$LLM_STATUS_JSON" "$CLEANED_UP"
else
  if [[ "$KEEP_RUNNING" != "1" ]]; then
    cleanup_candidate_processes
    CLEANED_UP="true"
  fi
  sleep 1
  write_result "failed" "$MARKER" "$HEALTH_JSON" "$LLM_STATUS_JSON" "$CLEANED_UP"
  exit 1
fi

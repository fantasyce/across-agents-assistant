#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${LOOP_ENGINEERING_SOLIDIFIED_OUTPUT_DIR:-}"
RUN_E2E="1"

usage() {
  cat <<'USAGE'
Usage: scripts/run_loop_engineering_solidified_e2e.sh [--output-dir path] [--skip-e2e]

Run the fixed Loop Engineering skill/tool matrix audit, then run the full
non-GUI Loop Engineering E2E through AAA.

Options:
  --output-dir path  Directory for matrix outputs, logs, and copied E2E summary.
  --skip-e2e         Run only the matrix audit and script syntax checks.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="${2:-}"
      if [[ -z "$OUTPUT_DIR" ]]; then
        echo "--output-dir requires a path" >&2
        exit 2
      fi
      shift
      ;;
    --skip-e2e)
      RUN_E2E="0"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/across-loop-engineering-solidified-e2e.XXXXXX")"
else
  mkdir -p "$OUTPUT_DIR"
fi

MATRIX_JSON="$OUTPUT_DIR/skill-tool-matrix.json"
MATRIX_MD="$OUTPUT_DIR/skill-tool-matrix.md"
CAPABILITY_JSON="$OUTPUT_DIR/aaa-loop-engineering-capabilities.json"
E2E_LOG="$OUTPUT_DIR/loop-engineering-e2e.log"
SUMMARY_JSON="$OUTPUT_DIR/solidified-e2e-summary.json"

echo "== Auditing solidified skill/tool matrix =="
bash "$ROOT_DIR/scripts/loop_engineering_skill_tool_matrix.sh" --json --strict > "$MATRIX_JSON"
bash "$ROOT_DIR/scripts/loop_engineering_skill_tool_matrix.sh" --markdown --strict > "$MATRIX_MD"
python3 -m json.tool "$MATRIX_JSON" >/dev/null

echo "== Checking AAA-hosted capability pack =="
PYTHONPATH="$ROOT_DIR/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
python3 -m across_agents_assistant.cli loop-engineering-capabilities > "$CAPABILITY_JSON"
python3 -m json.tool "$CAPABILITY_JSON" >/dev/null
python3 - "$CAPABILITY_JSON" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
ids = {item.get("id") for item in payload.get("ready", [])}
required = {
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
    "independent_review",
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
}
missing = sorted(required - ids)
if payload.get("ready_count", 0) < 41 or missing:
    raise SystemExit(f"AAA capability pack is incomplete: ready_count={payload.get('ready_count')} missing={missing}")
PY

echo "== Checking fixed script syntax =="
bash -n "$ROOT_DIR/scripts/loop_engineering_skill_tool_matrix.sh"
bash -n "$ROOT_DIR/scripts/loop_engineering_cleanup_retention.sh"
bash -n "$ROOT_DIR/scripts/check_computer_use_attach_readiness.sh"
bash -n "$ROOT_DIR/scripts/run_loop_engineering_e2e.sh"
bash -n "$ROOT_DIR/scripts/run_loop_engineering_solidified_e2e.sh"

echo "== Checking retention dry-run contract =="
"$ROOT_DIR/scripts/loop_engineering_cleanup_retention.sh" \
  --across-home "$OUTPUT_DIR/empty-across-home" \
  --runtime-home-root "$OUTPUT_DIR/empty-runtime-homes" \
  --include-source-mirrors \
  --max-age-days 1 \
  --keep-latest 1 > "$OUTPUT_DIR/retention-dry-run.json"
python3 -m json.tool "$OUTPUT_DIR/retention-dry-run.json" >/dev/null

echo "== Checking AAA patch whitespace =="
git -C "$ROOT_DIR" diff --check

if [[ "$RUN_E2E" != "1" ]]; then
  python3 - "$SUMMARY_JSON" "$OUTPUT_DIR" "$MATRIX_JSON" "$CAPABILITY_JSON" <<'PY'
import json
import pathlib
import sys

summary_path = pathlib.Path(sys.argv[1])
output_dir = pathlib.Path(sys.argv[2])
matrix_path = pathlib.Path(sys.argv[3])
capability_path = pathlib.Path(sys.argv[4])
summary_path.write_text(json.dumps({
    "schema_version": "across-loop-engineering-solidified-e2e/1.0",
    "status": "matrix_only",
    "output_dir": str(output_dir),
    "matrix_json": str(matrix_path),
    "capability_json": str(capability_path),
    "e2e_ran": False,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  echo "Solidified matrix audit passed. Summary: $SUMMARY_JSON"
  exit 0
fi

echo "== Running full Loop Engineering E2E after solidified audit =="
set +e
KEEP_LOOP_ENGINEERING_E2E_HOME="${KEEP_LOOP_ENGINEERING_E2E_HOME:-1}" \
bash "$ROOT_DIR/scripts/run_loop_engineering_e2e.sh" 2>&1 | tee "$E2E_LOG"
status="${PIPESTATUS[0]}"
set -e

summary_source="$(sed -n 's/^Loop Engineering E2E passed\. Summary: //p' "$E2E_LOG" | tail -1)"

if [[ "$status" -ne 0 ]]; then
  python3 - "$SUMMARY_JSON" "$OUTPUT_DIR" "$MATRIX_JSON" "$CAPABILITY_JSON" "$E2E_LOG" "$status" <<'PY'
import json
import pathlib
import sys

summary_path = pathlib.Path(sys.argv[1])
output_dir = pathlib.Path(sys.argv[2])
matrix_path = pathlib.Path(sys.argv[3])
capability_path = pathlib.Path(sys.argv[4])
log_path = pathlib.Path(sys.argv[5])
status = int(sys.argv[6])
summary_path.write_text(json.dumps({
    "schema_version": "across-loop-engineering-solidified-e2e/1.0",
    "status": "failed",
    "output_dir": str(output_dir),
    "matrix_json": str(matrix_path),
    "capability_json": str(capability_path),
    "e2e_log": str(log_path),
    "e2e_exit_code": status,
    "e2e_ran": True,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  echo "Solidified E2E failed. Summary: $SUMMARY_JSON" >&2
  exit "$status"
fi

copied_e2e_summary=""
if [[ -n "$summary_source" && -f "$summary_source" ]]; then
  copied_e2e_summary="$OUTPUT_DIR/e2e-summary.json"
  cp "$summary_source" "$copied_e2e_summary"
fi

python3 - "$SUMMARY_JSON" "$OUTPUT_DIR" "$MATRIX_JSON" "$MATRIX_MD" "$CAPABILITY_JSON" "$E2E_LOG" "$summary_source" "$copied_e2e_summary" <<'PY'
import json
import pathlib
import sys

summary_path = pathlib.Path(sys.argv[1])
output_dir = pathlib.Path(sys.argv[2])
matrix_path = pathlib.Path(sys.argv[3])
matrix_md_path = pathlib.Path(sys.argv[4])
capability_path = pathlib.Path(sys.argv[5])
log_path = pathlib.Path(sys.argv[6])
summary_source = sys.argv[7] or None
copied_e2e_summary = sys.argv[8] or None

payload = {
    "schema_version": "across-loop-engineering-solidified-e2e/1.0",
    "status": "passed",
    "output_dir": str(output_dir),
    "matrix_json": str(matrix_path),
    "matrix_markdown": str(matrix_md_path),
    "capability_json": str(capability_path),
    "e2e_log": str(log_path),
    "e2e_summary_source": summary_source,
    "e2e_summary": copied_e2e_summary,
    "e2e_ran": True,
}
if copied_e2e_summary:
    e2e = json.loads(pathlib.Path(copied_e2e_summary).read_text(encoding="utf-8"))
    payload.update({
        "run_id": e2e.get("run_id"),
        "spec_id": e2e.get("spec_id"),
        "candidate_id": e2e.get("candidate_id"),
        "semantic_alignment_status": e2e.get("semantic_alignment_status"),
        "self_hosting_probe_status": (e2e.get("self_hosting_probe") or {}).get("status"),
        "telemetry_run_count": e2e.get("telemetry_run_count"),
        "unified_capability_registry": e2e.get("unified_capability_registry"),
        "promotion_review": e2e.get("promotion_review"),
    })

summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "Solidified Loop Engineering E2E passed. Summary: $SUMMARY_JSON"

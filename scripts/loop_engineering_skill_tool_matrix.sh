#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTOPILOT_ROOT="${ACROSS_AUTOPILOT_SOURCE:-"$ROOT_DIR/../across-autopilot"}"
FORMAT="markdown"
STRICT="0"

usage() {
  cat <<'USAGE'
Usage: scripts/loop_engineering_skill_tool_matrix.sh [--markdown|--json] [--strict]

Print the fixed Loop Engineering skill/tool extraction matrix.

Options:
  --markdown   Print a human-readable Markdown matrix. Default.
  --json       Print machine-readable JSON.
  --strict     Exit non-zero if a core implemented tool/script entrypoint is missing.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --markdown)
      FORMAT="markdown"
      ;;
    --json)
      FORMAT="json"
      ;;
    --strict)
      STRICT="1"
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

export ROOT_DIR AUTOPILOT_ROOT FORMAT STRICT

python3 - <<'PY'
import json
import os
import pathlib
import shutil
import subprocess
import sys

root = pathlib.Path(os.environ["ROOT_DIR"]).resolve()
autopilot = pathlib.Path(os.environ["AUTOPILOT_ROOT"]).resolve()
fmt = os.environ["FORMAT"]
strict = os.environ["STRICT"] == "1"


def rel(path):
    try:
        return str(path.relative_to(root))
    except ValueError:
        try:
            return str(path.relative_to(autopilot.parent))
        except ValueError:
            return str(path)


def existing(paths):
    return [str(path) for path in paths if path.exists()]


def missing(paths):
    return [str(path) for path in paths if not path.exists()]


def node_bin():
    found = shutil.which("node")
    if found:
        return found
    fallback = pathlib.Path("/opt/homebrew/bin/node")
    return str(fallback) if fallback.exists() else None


def load_tool_packs():
    command = node_bin()
    if not command or not (autopilot / "src/tool-packs.js").exists():
        return [], "unavailable"
    proc = subprocess.run(
        [
            command,
            "--input-type=module",
            "-e",
            "import { listToolPacks } from './src/tool-packs.js'; "
            "console.log(JSON.stringify(listToolPacks().map((pack) => pack.id).sort()));",
        ],
        cwd=autopilot,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return [], proc.stderr.strip() or "node import failed"
    return json.loads(proc.stdout or "[]"), "loaded"


tool_packs, tool_pack_status = load_tool_packs()
tool_pack_set = set(tool_packs)


def p(repo, path):
    base = root if repo == "aaa" else autopilot
    return base / path


steps = [
    {
        "id": "trigger_ingestion",
        "layer": "Trigger",
        "solidify_as": "Tool Pack + CLI/MCP tool",
        "current_entrypoint": "across-autopilot loop enqueue-trigger / run-trigger; MCP enqueue_loop_trigger / run_next_loop_trigger",
        "required_tool_packs": ["trigger_ingestion"],
        "required_files": [p("autopilot", "src/trigger-queue.js"), p("autopilot", "src/cli.js"), p("autopilot", "src/mcp-server.js")],
        "next_step": "Keep trigger ingestion routed through the durable queue and visible through AAA API/ops controls.",
        "strict_required": True,
    },
    {
        "id": "trigger_management_api",
        "layer": "Trigger",
        "solidify_as": "AAA API",
        "current_entrypoint": "/api/autopilot/triggers",
        "required_tool_packs": ["trigger_ingestion"],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "backend/src/across_agents_assistant/autopilot_client.py"),
            p("aaa", "backend/tests/test_api_autopilot.py"),
        ],
        "next_step": "Keep trigger run controls separate from direct Autopilot internals.",
        "strict_required": True,
    },
    {
        "id": "trigger_productionization",
        "layer": "Trigger",
        "solidify_as": "AAA trigger registry API",
        "current_entrypoint": "/api/autopilot/trigger-configs, /tick, /webhooks/{trigger_id}",
        "required_tool_packs": ["trigger_ingestion"],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/autopilot_trigger_manager.py"),
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "backend/tests/test_api_autopilot.py"),
        ],
        "next_step": "Run cron/webhook/daemon wakeups through the same durable trigger queue before execution.",
        "strict_required": True,
    },
    {
        "id": "continuous_self_iteration_plan",
        "layer": "Trigger",
        "solidify_as": "AAA self-iteration plan API",
        "current_entrypoint": "/api/autopilot/self-iteration-plan and /ensure",
        "required_tool_packs": ["trigger_ingestion"],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/loop_engineering_self_iteration.py"),
            p("aaa", "backend/src/across_agents_assistant/autopilot_trigger_manager.py"),
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "backend/tests/test_api_autopilot.py"),
        ],
        "next_step": "Keep the default AAA self-iteration cron trigger idempotent and visible in ops.",
        "strict_required": True,
    },
    {
        "id": "loop_contract_validation",
        "layer": "Contract",
        "solidify_as": "CLI/MCP tool",
        "current_entrypoint": "across-autopilot loop validate / dry-run; MCP validate_loop_spec / dry_run_loop",
        "required_tool_packs": [],
        "required_files": [p("autopilot", "src/loop-spec.js"), p("autopilot", "src/cli.js"), p("autopilot", "src/mcp-server.js")],
        "next_step": "Keep schema migration tests strict whenever LoopSpec fields change.",
        "strict_required": True,
    },
    {
        "id": "runtime_policy_contract",
        "layer": "Contract",
        "solidify_as": "LoopSpec runtime policy",
        "current_entrypoint": "LoopSpec.runtime_policy and dry-run capability_preflight",
        "required_tool_packs": ["capability_preflight"],
        "required_files": [p("autopilot", "src/loop-spec.js"), p("autopilot", "src/supervisor.js"), p("autopilot", "tests/loop-platform.test.js")],
        "next_step": "Keep runtime timeouts, network/filesystem policy, budget, and human promotion policy validated before runs.",
        "strict_required": True,
    },
    {
        "id": "runtime_budget_enforcement",
        "layer": "Contract",
        "solidify_as": "Autopilot runtime hard gate",
        "current_entrypoint": "AutopilotSupervisor runtime_budget evidence and hard failure",
        "required_tool_packs": ["capability_preflight"],
        "required_files": [
            p("autopilot", "src/supervisor.js"),
            p("autopilot", "src/evidence.js"),
            p("autopilot", "src/failures.js"),
            p("autopilot", "tests/loop-platform.test.js"),
        ],
        "next_step": "Keep model-call, repair, and timeout limits enforced during continuous self-iteration.",
        "strict_required": True,
    },
    {
        "id": "source_mirror_preparation",
        "layer": "Memory and State",
        "solidify_as": "Fixed script",
        "current_entrypoint": "scripts/prepare_loop_engineering_sources.sh",
        "required_tool_packs": [],
        "required_files": [p("aaa", "scripts/prepare_loop_engineering_sources.sh")],
        "next_step": "Keep this as the canonical four-repo source snapshot entrypoint for E2E.",
        "strict_required": True,
    },
    {
        "id": "git_repo_inspection",
        "layer": "Tool",
        "solidify_as": "Tool Pack",
        "current_entrypoint": "git_repo_inspection",
        "required_tool_packs": ["git_repo_inspection"],
        "required_files": [p("autopilot", "src/tool-packs.js"), p("autopilot", "src/adapter-registry.js")],
        "next_step": "Extend manifest/dependency/license inspection without asking models to invent shell checks.",
        "strict_required": True,
    },
    {
        "id": "repo_dependency_license_review",
        "layer": "Tool",
        "solidify_as": "Tool Packs",
        "current_entrypoint": "repo_quality_inspection / dependency_security_review / license_policy_scan",
        "required_tool_packs": ["repo_quality_inspection", "dependency_security_review", "license_policy_scan"],
        "required_files": [p("autopilot", "src/tool-packs.js"), p("autopilot", "src/adapter-registry.js"), p("autopilot", "tests/loop-platform.test.js")],
        "next_step": "Keep dependency, license, manifest, and repo inspection deterministic before model interpretation.",
        "strict_required": True,
    },
    {
        "id": "source_research_digest",
        "layer": "Tool",
        "solidify_as": "Tool Pack",
        "current_entrypoint": "source_research_digest",
        "required_tool_packs": ["source_research_digest"],
        "required_files": [p("autopilot", "src/tool-packs.js"), p("autopilot", "src/candidate-ecosystem.js")],
        "next_step": "Add provider-specific fetch adapters only behind bounded source records.",
        "strict_required": True,
    },
    {
        "id": "candidate_workspace",
        "layer": "Agent Orchestration",
        "solidify_as": "Tool Pack",
        "current_entrypoint": "candidate_workspace",
        "required_tool_packs": ["candidate_workspace"],
        "required_files": [p("autopilot", "src/candidate-ecosystem.js")],
        "next_step": "Keep mutation scoped to B candidate workspaces and preserve short runtime paths.",
        "strict_required": True,
    },
    {
        "id": "candidate_model_lease",
        "layer": "Agent Orchestration",
        "solidify_as": "Host model capability boundary",
        "current_entrypoint": "candidate-model-lease.json / ACROSS_AAA_CANDIDATE_MODEL_LEASE",
        "required_tool_packs": ["candidate_workspace", "independent_review"],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/autopilot_client.py"),
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "scripts/candidate_app_lifecycle.sh"),
            p("autopilot", "src/model-lease.js"),
            p("autopilot", "src/candidate-ecosystem.js"),
        ],
        "next_step": "Keep candidate model access lease-based and non-secret; never copy or symlink host credentials into B.",
        "strict_required": True,
    },
    {
        "id": "model_target_admission",
        "layer": "Agent Orchestration",
        "solidify_as": "Deterministic tool helper",
        "current_entrypoint": "product_iteration_strategy admission inside src/candidate-ecosystem.js",
        "required_tool_packs": [],
        "required_files": [p("autopilot", "src/candidate-ecosystem.js"), p("autopilot", "tests/loop-platform.test.js")],
        "next_step": "Promote admission metadata into a named Tool Pack if other LoopSpecs need it.",
        "strict_required": True,
    },
    {
        "id": "model_generated_fallback_plan",
        "layer": "Agent Orchestration",
        "solidify_as": "Tool Pack + deterministic admission helper",
        "current_entrypoint": "model_generated_fallback_plan / product_iteration_strategy target_generation",
        "required_tool_packs": ["model_generated_fallback_plan"],
        "required_files": [p("autopilot", "src/tool-packs.js"), p("autopilot", "src/candidate-ecosystem.js"), p("autopilot", "src/loop-state.js")],
        "next_step": "Keep fallback plans bounded by repo/path admission, validation harnesses, and distinct-model review.",
        "strict_required": True,
    },
    {
        "id": "multi_candidate_comparison",
        "layer": "Agent Orchestration",
        "solidify_as": "Strategy evidence artifact",
        "current_entrypoint": "product_iteration_strategy.candidate_comparison",
        "required_tool_packs": ["model_generated_fallback_plan"],
        "required_files": [p("autopilot", "src/candidate-ecosystem.js"), p("autopilot", "tests/loop-platform.test.js")],
        "next_step": "Keep model-generated candidate selection explainable with scores, risks, and validation command counts.",
        "strict_required": True,
    },
    {
        "id": "validation_harness",
        "layer": "Verification and Promotion",
        "solidify_as": "Tool Pack",
        "current_entrypoint": "validation_harness",
        "required_tool_packs": ["validation_harness"],
        "required_files": [p("autopilot", "src/candidate-ecosystem.js")],
        "next_step": "Keep command allowlists and Python -c compile checks deterministic.",
        "strict_required": True,
    },
    {
        "id": "candidate_diff_quality",
        "layer": "Verification and Promotion",
        "solidify_as": "Tool Pack",
        "current_entrypoint": "candidate_diff_quality",
        "required_tool_packs": ["candidate_diff_quality"],
        "required_files": [p("autopilot", "src/tool-packs.js"), p("autopilot", "src/candidate-ecosystem.js")],
        "next_step": "Add broader complexity and formatting checks as deterministic findings.",
        "strict_required": True,
    },
    {
        "id": "candidate_quality_gate_expansion",
        "layer": "Verification and Promotion",
        "solidify_as": "Tool Pack static rules",
        "current_entrypoint": "candidate_diff_quality static source findings",
        "required_tool_packs": ["candidate_diff_quality"],
        "required_files": [p("autopilot", "src/candidate-ecosystem.js"), p("autopilot", "tests/loop-platform.test.js")],
        "next_step": "Continue adding low-noise deterministic findings for reviewability, dependency risk, and complexity.",
        "strict_required": True,
    },
    {
        "id": "independent_review",
        "layer": "Verification and Promotion",
        "solidify_as": "Tool Pack + reviewer role evidence",
        "current_entrypoint": "independent_review / semantic_alignment_review",
        "required_tool_packs": ["independent_review"],
        "required_files": [p("autopilot", "src/candidate-ecosystem.js"), p("autopilot", "src/evidence.js")],
        "next_step": "Keep reviewer independent from builder and return merge recommendation plus scores.",
        "strict_required": True,
    },
    {
        "id": "distinct_model_acceptance",
        "layer": "Verification and Promotion",
        "solidify_as": "AAA host model gate",
        "current_entrypoint": "autopilot-review-decision -> semantic_alignment_review distinct_reviewer_model_passed",
        "required_tool_packs": ["independent_review"],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "backend/src/across_agents_assistant/autopilot_review_decision_cli.py"),
            p("aaa", "backend/src/across_agents_assistant/loop_engineering_capability_pack.py"),
            p("autopilot", "src/candidate-ecosystem.js"),
            p("autopilot", "src/evidence.js"),
            p("autopilot", "examples/aaa-autonomous-self-iteration.loop.json"),
        ],
        "next_step": "Reuse this host gate for any LoopSpec that needs acceptance by a different model than the builder.",
        "strict_required": True,
    },
    {
        "id": "promotion_package",
        "layer": "Verification and Promotion",
        "solidify_as": "Promotion tool output",
        "current_entrypoint": "candidate evidence promotion_package",
        "required_tool_packs": ["candidate_diff_quality"],
        "required_files": [p("autopilot", "src/candidate-ecosystem.js"), p("autopilot", "src/evidence.js")],
        "next_step": "Keep optional signing separate from unattended execution and require human review for promotion.",
        "strict_required": True,
    },
    {
        "id": "promotion_source_ref_pinning",
        "layer": "Verification and Promotion",
        "solidify_as": "Promotion output gate",
        "current_entrypoint": "candidate.promotion_package.source_ref_pins",
        "required_tool_packs": ["candidate_diff_quality"],
        "required_files": [
            p("autopilot", "src/candidate-ecosystem.js"),
            p("autopilot", "tests/loop-platform.test.js"),
            p("aaa", "backend/src/across_agents_assistant/autopilot_promotion_review.py"),
            p("aaa", "scripts/run_loop_engineering_e2e.sh"),
        ],
        "next_step": "Use source pins in every promotion-review packet before opening a protected PR.",
        "strict_required": True,
    },
    {
        "id": "promotion_review_packet",
        "layer": "Verification and Promotion",
        "solidify_as": "AAA review API",
        "current_entrypoint": "/api/autopilot/runs/{run_id}/promotion-review",
        "required_tool_packs": ["candidate_diff_quality", "independent_review"],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/autopilot_promotion_review.py"),
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "backend/tests/test_api_autopilot.py"),
        ],
        "next_step": "Keep promotion review packets available through the AAA API while merge/release stays disabled by default.",
        "strict_required": True,
    },
    {
        "id": "promotion_attestation",
        "layer": "Verification and Promotion",
        "solidify_as": "Promotion provenance artifact",
        "current_entrypoint": "promotion_review.promotion_attestation",
        "required_tool_packs": ["promotion_attestation"],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/autopilot_promotion_review.py"),
            p("aaa", "backend/tests/test_api_autopilot.py"),
            p("aaa", "scripts/run_loop_engineering_e2e.sh"),
        ],
        "next_step": "Require provenance digest in review packets and keep signing separate from unattended execution.",
        "strict_required": True,
    },
    {
        "id": "evidence_integrity",
        "layer": "Memory and State",
        "solidify_as": "Tool Pack",
        "current_entrypoint": "evidence_integrity",
        "required_tool_packs": ["evidence_integrity"],
        "required_files": [p("autopilot", "src/evidence.js"), p("autopilot", "src/audit-log.js"), p("autopilot", "src/roles.js")],
        "next_step": "Use section hashes and audit-chain tips in every promotion review.",
        "strict_required": True,
    },
    {
        "id": "telemetry_rollup",
        "layer": "Memory and State",
        "solidify_as": "CLI/MCP tool",
        "current_entrypoint": "across-autopilot loop telemetry; MCP get_loop_telemetry",
        "required_tool_packs": [],
        "required_files": [p("autopilot", "src/telemetry.js"), p("autopilot", "src/cli.js"), p("autopilot", "src/mcp-server.js")],
        "next_step": "Keep cross-run trends bounded and free of raw source content in API/ops surfaces.",
        "strict_required": True,
    },
    {
        "id": "ops_dashboard",
        "layer": "Memory and State",
        "solidify_as": "AAA ops API",
        "current_entrypoint": "/api/autopilot/ops-dashboard",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/loop_engineering_ops.py"),
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "backend/tests/test_api_autopilot.py"),
        ],
        "next_step": "Keep ops dashboard data available through the AAA API without taking over frontend page ownership.",
        "strict_required": True,
    },
    {
        "id": "unified_capability_registry",
        "layer": "Tool",
        "solidify_as": "AAA registry API",
        "current_entrypoint": "/api/capability-registry",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/unified_capability_registry.py"),
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "backend/tests/test_api_autopilot.py"),
            p("aaa", "scripts/run_loop_engineering_e2e.sh"),
        ],
        "next_step": "Use this as the shared discovery layer while keeping AAA, Autopilot, MCP, Plugins, Models, and Tools execution boundaries separate.",
        "strict_required": True,
    },
    {
        "id": "registry_health_compatibility",
        "layer": "Tool",
        "solidify_as": "AAA registry health API",
        "current_entrypoint": "/api/capability-registry/health",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/unified_capability_registry.py"),
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "backend/tests/test_api_autopilot.py"),
        ],
        "next_step": "Use this health contract before external loop chains consume unified capability data.",
        "strict_required": True,
    },
    {
        "id": "cleanup_retention",
        "layer": "Memory and State",
        "solidify_as": "Fixed script",
        "current_entrypoint": "scripts/loop_engineering_cleanup_retention.sh",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "scripts/loop_engineering_cleanup_retention.sh"),
            p("aaa", "backend/src/across_agents_assistant/loop_engineering_retention.py"),
            p("aaa", "backend/tests/test_loop_engineering_retention.py"),
        ],
        "next_step": "Wire this into scheduled maintenance after retention defaults are validated in real usage.",
        "strict_required": True,
    },
    {
        "id": "candidate_app_lifecycle",
        "layer": "Verification and Promotion",
        "solidify_as": "Fixed script + validation harness probe",
        "current_entrypoint": "scripts/candidate_app_lifecycle.sh",
        "required_tool_packs": ["validation_harness"],
        "required_files": [p("aaa", "scripts/candidate_app_lifecycle.sh"), p("autopilot", "src/candidate-ecosystem.js")],
        "next_step": "Keep cleanup and crash-report checks mandatory for packaged runtime changes.",
        "strict_required": True,
    },
    {
        "id": "full_user_level_e2e",
        "layer": "Verification and Promotion",
        "solidify_as": "Fixed script",
        "current_entrypoint": "scripts/run_loop_engineering_e2e.sh",
        "required_tool_packs": [],
        "required_files": [p("aaa", "scripts/run_loop_engineering_e2e.sh"), p("aaa", "scripts/prepare_loop_engineering_sources.sh")],
        "next_step": "Use this as the default non-GUI release confidence script.",
        "strict_required": True,
    },
    {
        "id": "solidified_e2e_gate",
        "layer": "Cross-layer",
        "solidify_as": "Fixed script",
        "current_entrypoint": "scripts/run_loop_engineering_solidified_e2e.sh",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "scripts/loop_engineering_skill_tool_matrix.sh"),
            p("aaa", "scripts/run_loop_engineering_e2e.sh"),
            p("aaa", "scripts/run_loop_engineering_solidified_e2e.sh"),
        ],
        "next_step": "Run this wrapper when validation must prove the solidified skill/tool contract before E2E.",
        "strict_required": True,
    },
    {
        "id": "solidified_loop_skills",
        "layer": "Cross-layer",
        "solidify_as": "Skill artifacts",
        "current_entrypoint": "loop-engineering-skills/*/SKILL.md",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "loop-engineering-skills/loop-capability-audit/SKILL.md"),
            p("aaa", "loop-engineering-skills/e2e-failure-triage/SKILL.md"),
        ],
        "next_step": "Reuse these skill artifacts across future loop engineering chains through AAA capability discovery.",
        "strict_required": True,
    },
    {
        "id": "loop_engineering_capability_audit",
        "layer": "Cross-layer",
        "solidify_as": "Skill artifact",
        "current_entrypoint": "loop-engineering-skills/loop-capability-audit/SKILL.md",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "loop-engineering-skills/loop-capability-audit/SKILL.md"),
            p("aaa", "scripts/loop_engineering_skill_tool_matrix.sh"),
            p("aaa", "LOOP_ENGINEERING_REMAINING_WORK.md"),
        ],
        "next_step": "Keep capability ownership audits grounded in the machine-readable matrix.",
        "strict_required": True,
    },
    {
        "id": "e2e_failure_triage",
        "layer": "Cross-layer",
        "solidify_as": "Skill artifact",
        "current_entrypoint": "loop-engineering-skills/e2e-failure-triage/SKILL.md",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "loop-engineering-skills/e2e-failure-triage/SKILL.md"),
            p("aaa", "scripts/run_loop_engineering_solidified_e2e.sh"),
            p("aaa", "LOOP_ENGINEERING_FINAL_TEST_REPORT.md"),
        ],
        "next_step": "Use this skill only after reading the failed summary JSON and log.",
        "strict_required": True,
    },
    {
        "id": "promotion_human_review",
        "layer": "Verification and Promotion",
        "solidify_as": "AAA review API",
        "current_entrypoint": "/api/autopilot/runs/{run_id}/promotion-review",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "backend/src/across_agents_assistant/autopilot_promotion_review.py"),
            p("aaa", "backend/src/across_agents_assistant/api_server.py"),
            p("aaa", "backend/tests/test_api_autopilot.py"),
        ],
        "next_step": "Keep merge/release actions disabled by default and expose review packets for human review.",
        "strict_required": True,
    },
    {
        "id": "frontend_gui_click_validation",
        "layer": "Validation-only",
        "solidify_as": "Computer Use frontend E2E",
        "current_entrypoint": "separate Computer Use专项; no product UI change in this branch",
        "required_tool_packs": [],
        "required_files": [
            p("aaa", "LOOP_ENGINEERING_REMAINING_WORK.md"),
            p("aaa", "LOOP_ENGINEERING_FINAL_TEST_REPORT.md"),
        ],
        "next_step": "Resolve Computer Use window attach/click validation separately without changing the current product UI.",
        "strict_required": False,
        "forced_status": "blocked_validation_only",
    },
    {
        "id": "computer_use_attach_diagnostic",
        "layer": "Validation-only",
        "solidify_as": "Fixed diagnostic script",
        "current_entrypoint": "scripts/check_computer_use_attach_readiness.sh",
        "required_tool_packs": [],
        "required_files": [p("aaa", "scripts/check_computer_use_attach_readiness.sh")],
        "next_step": "Use only to diagnose GUI attach readiness; do not treat failure as product-capability failure.",
        "strict_required": True,
    },
]


def evaluate(step):
    required_files = step.get("required_files", [])
    required_packs = step.get("required_tool_packs", [])
    missing_files = missing(required_files)
    missing_packs = [pack for pack in required_packs if pack not in tool_pack_set]
    if step.get("forced_status"):
        status = step["forced_status"]
    elif missing_files or missing_packs:
        status = "missing"
    elif step["solidify_as"].startswith("Agent skill candidate") or "candidate" in step["solidify_as"]:
        status = "candidate"
    else:
        status = "ready"
    return {
        **{key: value for key, value in step.items() if key not in {"required_files", "strict_required"}},
        "status": status,
        "required_files": [rel(path) for path in required_files],
        "present_files": [rel(pathlib.Path(path)) for path in existing(required_files)],
        "missing_files": [rel(pathlib.Path(path)) for path in missing_files],
        "missing_tool_packs": missing_packs,
    }


evaluated = [evaluate(step) for step in steps]
payload = {
    "schema_version": "across-loop-engineering-skill-tool-matrix/1.0",
    "aaa_root": str(root),
    "autopilot_root": str(autopilot),
    "tool_pack_registry": {
        "status": tool_pack_status,
        "packs": tool_packs,
    },
    "steps": evaluated,
}

strict_failures = [
    step for step, raw in zip(evaluated, steps)
    if raw.get("strict_required") and step["status"] != "ready"
]

if fmt == "json":
    print(json.dumps(payload, indent=2, sort_keys=True))
else:
    print("# Loop Engineering Skill/Tool Matrix")
    print()
    print("- AAA root: resolved from this repository at runtime")
    print("- Autopilot root: resolved from `ACROSS_AUTOPILOT_SOURCE` or `../across-autopilot` at runtime")
    print(f"- Tool Pack registry: `{tool_pack_status}` ({len(tool_packs)} pack(s))")
    print()
    print("| Step | Layer | 固化形态 | 当前入口 | 状态 | 下一步 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for step in evaluated:
        def cell(value):
            return str(value).replace("|", "\\|").replace("\n", " ")
        print(
            "| "
            + " | ".join(
                [
                    f"`{cell(step['id'])}`",
                    cell(step["layer"]),
                    cell(step["solidify_as"]),
                    cell(step["current_entrypoint"]),
                    f"`{cell(step['status'])}`",
                    cell(step["next_step"]),
                ]
            )
            + " |"
        )
    print()
    print("## Status")
    print()
    print("- `ready`: already has a deterministic Tool Pack, CLI/MCP tool, or fixed script entrypoint.")
    print("- `candidate`: useful to promote into a Codex/agent skill or future tool after the pattern repeats.")
    print("- `validation_only`: frontend or external-driver validation coverage, not a product runtime capability.")
    print("- `blocked_validation_only`: validation coverage that is currently blocked, not a product capability blocker.")
    if strict_failures:
        print()
        print("## Strict Failures")
        print()
        for step in strict_failures:
            details = []
            if step["missing_tool_packs"]:
                details.append("missing Tool Packs: " + ", ".join(step["missing_tool_packs"]))
            if step["missing_files"]:
                details.append("missing files: " + ", ".join(step["missing_files"]))
            print(f"- `{step['id']}`: {'; '.join(details)}")

if strict_failures and strict:
    sys.exit(1)
PY

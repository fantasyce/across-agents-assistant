from __future__ import annotations

from typing import Any

from .autopilot_source_signal_synthesizer import attach_ai_ready_context


READY_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "id": "trigger_ingestion",
        "layer": "Trigger",
        "form": "tool_pack_cli_mcp",
        "entrypoint": "across-autopilot loop enqueue-trigger / run-trigger",
        "reusable_by": ["loop_engineering", "scheduled_research", "webhook_loops"],
    },
    {
        "id": "trigger_management_api",
        "layer": "Trigger",
        "form": "aaa_api",
        "entrypoint": "/api/autopilot/triggers",
        "reusable_by": ["workbench", "scheduled_research", "webhook_loops"],
    },
    {
        "id": "trigger_registry_api",
        "layer": "Trigger",
        "form": "aaa_api",
        "entrypoint": "/api/autopilot/trigger-configs",
        "reusable_by": ["workbench", "scheduled_research", "webhook_loops", "daemon_loops"],
    },
    {
        "id": "cron_scheduler_tick",
        "layer": "Trigger",
        "form": "aaa_api_scheduler",
        "entrypoint": "/api/autopilot/trigger-configs/tick",
        "reusable_by": ["scheduled_research", "maintenance_loops", "ops_review"],
    },
    {
        "id": "continuous_self_iteration_plan",
        "layer": "Trigger",
        "form": "aaa_api_plan",
        "entrypoint": "/api/autopilot/self-iteration-plan",
        "reusable_by": ["loop_engineering", "scheduled_research", "ops_review", "workbench"],
    },
    {
        "id": "webhook_receiver",
        "layer": "Trigger",
        "form": "aaa_api",
        "entrypoint": "/api/autopilot/webhooks/{trigger_id}",
        "reusable_by": ["github_events", "external_monitoring", "webhook_loops"],
    },
    {
        "id": "daemon_file_watcher",
        "layer": "Trigger",
        "form": "aaa_api_daemon_policy",
        "entrypoint": "daemon trigger config watch_path",
        "reusable_by": ["local_file_change_loops", "ops_review"],
    },
    {
        "id": "loop_contract_validation",
        "layer": "Contract",
        "form": "cli_mcp_tool",
        "entrypoint": "across-autopilot loop validate / dry-run",
        "reusable_by": ["all_loop_specs"],
    },
    {
        "id": "runtime_policy_contract",
        "layer": "Contract",
        "form": "loop_spec_policy",
        "entrypoint": "LoopSpec.runtime_policy",
        "reusable_by": ["all_loop_specs", "safety_review", "ops_review"],
    },
    {
        "id": "capability_preflight",
        "layer": "Contract",
        "form": "tool_pack_pre_run_gate",
        "entrypoint": "AutopilotSupervisor.capabilityPreflight",
        "reusable_by": ["all_loop_specs", "fallback_planning", "ops_review"],
    },
    {
        "id": "runtime_budget_enforcement",
        "layer": "Contract",
        "form": "runtime_policy_hard_gate",
        "entrypoint": "AutopilotSupervisor runtime_budget",
        "reusable_by": ["all_loop_specs", "scheduled_research", "continuous_self_iteration"],
    },
    {
        "id": "source_mirror_preparation",
        "layer": "Memory and State",
        "form": "fixed_script",
        "entrypoint": "scripts/prepare_loop_engineering_sources.sh",
        "reusable_by": ["e2e", "release_readiness"],
    },
    {
        "id": "git_repo_inspection",
        "layer": "Tool",
        "form": "tool_pack",
        "entrypoint": "git_repo_inspection",
        "reusable_by": ["research_loops", "candidate_review"],
    },
    {
        "id": "repo_quality_inspection",
        "layer": "Tool",
        "form": "tool_pack",
        "entrypoint": "repo_quality_inspection",
        "reusable_by": ["research_loops", "candidate_review", "dependency_review"],
    },
    {
        "id": "dependency_security_review",
        "layer": "Tool",
        "form": "tool_pack",
        "entrypoint": "dependency_security_review",
        "reusable_by": ["candidate_review", "release_readiness", "repair_loops"],
    },
    {
        "id": "license_policy_scan",
        "layer": "Tool",
        "form": "tool_pack",
        "entrypoint": "license_policy_scan",
        "reusable_by": ["candidate_review", "open_source_review", "release_readiness"],
    },
    {
        "id": "source_research_digest",
        "layer": "Tool",
        "form": "tool_pack",
        "entrypoint": "source_research_digest",
        "reusable_by": ["ecosystem_research", "news_digest", "technology_radar"],
    },
    {
        "id": "source_signal_synthesizer",
        "layer": "Memory and State",
        "form": "bounded_ai_ready_context",
        "entrypoint": "autopilot_source_signal_synthesizer.synthesize_ai_ready_context",
        "reusable_by": ["loop_engineering", "candidate_selection", "human_review"],
    },
    {
        "id": "candidate_workspace",
        "layer": "Agent Orchestration",
        "form": "tool_pack",
        "entrypoint": "candidate_workspace",
        "reusable_by": ["b_candidate_mutation"],
    },
    {
        "id": "candidate_model_lease",
        "layer": "Agent Orchestration",
        "form": "host_model_capability_boundary",
        "entrypoint": "ACROSS_AAA_CANDIDATE_MODEL_LEASE / candidate-model-lease.json",
        "reusable_by": ["b_candidate_self_iteration", "candidate_app_validation", "independent_review"],
    },
    {
        "id": "model_target_admission",
        "layer": "Agent Orchestration",
        "form": "deterministic_helper",
        "entrypoint": "product_iteration_strategy admission",
        "reusable_by": ["model_generated_targets"],
    },
    {
        "id": "model_generated_fallback_plan",
        "layer": "Agent Orchestration",
        "form": "host_model_admitted_fallback",
        "entrypoint": "product_iteration_strategy target_generation",
        "reusable_by": ["missing_tool_fallback", "open_backlog_loops"],
    },
    {
        "id": "multi_candidate_comparison",
        "layer": "Agent Orchestration",
        "form": "deterministic_strategy_artifact",
        "entrypoint": "product_iteration_strategy.candidate_comparison",
        "reusable_by": ["model_generated_targets", "candidate_selection", "human_review"],
    },
    {
        "id": "validation_harness",
        "layer": "Verification and Promotion",
        "form": "tool_pack",
        "entrypoint": "validation_harness",
        "reusable_by": ["candidate_validation", "repair_loops"],
    },
    {
        "id": "candidate_diff_quality",
        "layer": "Verification and Promotion",
        "form": "tool_pack",
        "entrypoint": "candidate_diff_quality",
        "reusable_by": ["candidate_review", "promotion_package"],
    },
    {
        "id": "candidate_quality_gate_expansion",
        "layer": "Verification and Promotion",
        "form": "tool_pack_static_rules",
        "entrypoint": "candidate_diff_quality static source findings",
        "reusable_by": ["candidate_review", "promotion_package", "repair_loops"],
    },
    {
        "id": "independent_review",
        "layer": "Verification and Promotion",
        "form": "tool_pack_reviewer_role",
        "entrypoint": "independent_review / semantic_alignment_review",
        "reusable_by": ["promotion_review"],
    },
    {
        "id": "distinct_model_acceptance",
        "layer": "Verification and Promotion",
        "form": "host_model_gate",
        "entrypoint": "autopilot-review-decision",
        "reusable_by": ["promotion_review", "acceptance_gates"],
    },
    {
        "id": "promotion_package",
        "layer": "Verification and Promotion",
        "form": "promotion_output",
        "entrypoint": "candidate.promotion_package",
        "reusable_by": ["human_review", "draft_pr"],
    },
    {
        "id": "promotion_source_ref_pinning",
        "layer": "Verification and Promotion",
        "form": "promotion_output_gate",
        "entrypoint": "candidate.promotion_package.source_ref_pins",
        "reusable_by": ["human_review", "draft_pr", "release_readiness"],
    },
    {
        "id": "promotion_review_packet",
        "layer": "Verification and Promotion",
        "form": "aaa_api",
        "entrypoint": "/api/autopilot/runs/{run_id}/promotion-review",
        "reusable_by": ["human_review", "draft_pr", "workbench"],
    },
    {
        "id": "promotion_human_review",
        "layer": "Verification and Promotion",
        "form": "workbench_ui",
        "entrypoint": "PluginLifecycleView promotion-review section",
        "reusable_by": ["human_review", "draft_pr", "workbench"],
    },
    {
        "id": "promotion_attestation",
        "layer": "Verification and Promotion",
        "form": "promotion_output_gate",
        "entrypoint": "promotion_review.promotion_attestation",
        "reusable_by": ["human_review", "draft_pr", "release_readiness"],
    },
    {
        "id": "evidence_integrity",
        "layer": "Memory and State",
        "form": "tool_pack",
        "entrypoint": "evidence_integrity",
        "reusable_by": ["audit", "promotion_review"],
    },
    {
        "id": "telemetry_rollup",
        "layer": "Memory and State",
        "form": "cli_mcp_tool",
        "entrypoint": "across-autopilot loop telemetry",
        "reusable_by": ["workbench", "ops_review"],
    },
    {
        "id": "ops_dashboard",
        "layer": "Memory and State",
        "form": "aaa_api",
        "entrypoint": "/api/autopilot/ops-dashboard",
        "reusable_by": ["workbench", "ops_review", "release_readiness"],
    },
    {
        "id": "unified_capability_registry",
        "layer": "Tool",
        "form": "api_registry",
        "entrypoint": "/api/capability-registry",
        "reusable_by": ["loop_engineering", "agent_routing", "workbench", "plugin_interop"],
    },
    {
        "id": "registry_health_compatibility",
        "layer": "Tool",
        "form": "aaa_api",
        "entrypoint": "/api/capability-registry/health",
        "reusable_by": ["loop_engineering", "agent_routing", "workbench", "plugin_interop"],
    },
    {
        "id": "cleanup_retention",
        "layer": "Memory and State",
        "form": "fixed_script",
        "entrypoint": "scripts/loop_engineering_cleanup_retention.sh",
        "reusable_by": ["release_readiness", "scheduled_maintenance", "ops_review"],
    },
    {
        "id": "candidate_app_lifecycle",
        "layer": "Verification and Promotion",
        "form": "fixed_script_probe",
        "entrypoint": "scripts/candidate_app_lifecycle.sh",
        "reusable_by": ["packaged_runtime_validation"],
    },
    {
        "id": "full_user_level_e2e",
        "layer": "Verification and Promotion",
        "form": "fixed_script",
        "entrypoint": "scripts/run_loop_engineering_e2e.sh",
        "reusable_by": ["release_readiness"],
    },
    {
        "id": "solidified_e2e_gate",
        "layer": "Cross-layer",
        "form": "fixed_script",
        "entrypoint": "scripts/run_loop_engineering_solidified_e2e.sh",
        "reusable_by": ["release_readiness", "capability_contract_validation"],
    },
    {
        "id": "loop_capability_audit_skill",
        "layer": "Cross-layer",
        "form": "skill_artifact",
        "entrypoint": "loop-engineering-skills/loop-capability-audit/SKILL.md",
        "reusable_by": ["loop_engineering", "capability_contract_validation"],
    },
    {
        "id": "e2e_failure_triage_skill",
        "layer": "Cross-layer",
        "form": "skill_artifact",
        "entrypoint": "loop-engineering-skills/e2e-failure-triage/SKILL.md",
        "reusable_by": ["loop_engineering", "release_readiness", "ops_review"],
    },
)


SKILL_CANDIDATES: tuple[dict[str, Any], ...] = (
)


VALIDATION_ONLY: tuple[dict[str, Any], ...] = (
    {
        "id": "frontend_gui_click_validation",
        "why": "Computer Use frontend attach/click coverage is a separate validation专项, not a Loop Engineering runtime capability.",
        "blocking_product_capability": False,
    },
    {
        "id": "computer_use_attach_diagnostic",
        "why": "scripts/check_computer_use_attach_readiness.sh diagnoses GUI attach readiness as validation-only evidence.",
        "blocking_product_capability": False,
    },
)


def loop_engineering_capability_pack(source_signals: Any = None) -> dict[str, Any]:
    pack = {
        "schema_version": "across-aaa-loop-engineering-capability-pack/1.0",
        "owner": "across-agents-assistant",
        "ready_count": len(READY_CAPABILITIES),
        "skill_candidate_count": len(SKILL_CANDIDATES),
        "validation_only_count": len(VALIDATION_ONLY),
        "ready": [dict(item) for item in READY_CAPABILITIES],
        "skill_candidates": [dict(item) for item in SKILL_CANDIDATES],
        "validation_only": [dict(item) for item in VALIDATION_ONLY],
        "policy": {
            "model_scope": "models choose topics, interpret evidence, and generate B-only patches",
            "tool_scope": "scripts and Tool Packs enforce boundaries, validation, review gates, and evidence",
            "fallback": "if no fixed tool or target catalog fits, the model may prepare a bounded candidate plan that still passes deterministic admission, validation, and review gates",
            "promotion": "commit, PR, merge, tag, release, signing, and publication require human approval",
        },
    }
    attach_ai_ready_context(pack, source_signals)
    return pack

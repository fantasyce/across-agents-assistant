# Loop Engineering Skill/Tool Matrix

- AAA root: resolved from this repository at runtime
- Autopilot root: resolved from `ACROSS_AUTOPILOT_SOURCE` or `../across-autopilot` at runtime
- Tool Pack registry: `loaded` (14 pack(s))

| Step | Layer | 固化形态 | 当前入口 | 状态 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| `trigger_ingestion` | Trigger | Tool Pack + CLI/MCP tool | across-autopilot loop enqueue-trigger / run-trigger; MCP enqueue_loop_trigger / run_next_loop_trigger | `ready` | Keep trigger ingestion routed through the durable queue and visible through AAA API/ops controls. |
| `trigger_management_api` | Trigger | AAA API | /api/autopilot/triggers | `ready` | Keep trigger run controls separate from direct Autopilot internals. |
| `trigger_productionization` | Trigger | AAA trigger registry API | /api/autopilot/trigger-configs, /tick, /webhooks/{trigger_id} | `ready` | Run cron/webhook/daemon wakeups through the same durable trigger queue before execution. |
| `continuous_self_iteration_plan` | Trigger | AAA self-iteration plan API | /api/autopilot/self-iteration-plan and /ensure | `ready` | Keep the default AAA self-iteration cron trigger idempotent and visible in ops. |
| `loop_contract_validation` | Contract | CLI/MCP tool | across-autopilot loop validate / dry-run; MCP validate_loop_spec / dry_run_loop | `ready` | Keep schema migration tests strict whenever LoopSpec fields change. |
| `runtime_policy_contract` | Contract | LoopSpec runtime policy | LoopSpec.runtime_policy and dry-run capability_preflight | `ready` | Keep runtime timeouts, network/filesystem policy, budget, and human promotion policy validated before runs. |
| `runtime_budget_enforcement` | Contract | Autopilot runtime hard gate | AutopilotSupervisor runtime_budget evidence and hard failure | `ready` | Keep model-call, repair, and timeout limits enforced during continuous self-iteration. |
| `source_mirror_preparation` | Memory and State | Fixed script | scripts/prepare_loop_engineering_sources.sh | `ready` | Keep this as the canonical four-repo source snapshot entrypoint for E2E. |
| `git_repo_inspection` | Tool | Tool Pack | git_repo_inspection | `ready` | Extend manifest/dependency/license inspection without asking models to invent shell checks. |
| `repo_dependency_license_review` | Tool | Tool Packs | repo_quality_inspection / dependency_security_review / license_policy_scan | `ready` | Keep dependency, license, manifest, and repo inspection deterministic before model interpretation. |
| `source_research_digest` | Tool | Tool Pack | source_research_digest | `ready` | Add provider-specific fetch adapters only behind bounded source records. |
| `candidate_workspace` | Agent Orchestration | Tool Pack | candidate_workspace | `ready` | Keep mutation scoped to B candidate workspaces and preserve short runtime paths. |
| `candidate_model_lease` | Agent Orchestration | Host model capability boundary | candidate-model-lease.json / ACROSS_AAA_CANDIDATE_MODEL_LEASE | `ready` | Keep candidate model access lease-based and non-secret; never copy or symlink host credentials into B. |
| `model_target_admission` | Agent Orchestration | Deterministic tool helper | product_iteration_strategy admission inside src/candidate-ecosystem.js | `ready` | Promote admission metadata into a named Tool Pack if other LoopSpecs need it. |
| `model_generated_fallback_plan` | Agent Orchestration | Tool Pack + deterministic admission helper | model_generated_fallback_plan / product_iteration_strategy target_generation | `ready` | Keep fallback plans bounded by repo/path admission, validation harnesses, and distinct-model review. |
| `multi_candidate_comparison` | Agent Orchestration | Strategy evidence artifact | product_iteration_strategy.candidate_comparison | `ready` | Keep model-generated candidate selection explainable with scores, risks, and validation command counts. |
| `validation_harness` | Verification and Promotion | Tool Pack | validation_harness | `ready` | Keep command allowlists and Python -c compile checks deterministic. |
| `candidate_diff_quality` | Verification and Promotion | Tool Pack | candidate_diff_quality | `ready` | Add broader complexity and formatting checks as deterministic findings. |
| `candidate_quality_gate_expansion` | Verification and Promotion | Tool Pack static rules | candidate_diff_quality static source findings | `ready` | Continue adding low-noise deterministic findings for reviewability, dependency risk, and complexity. |
| `independent_review` | Verification and Promotion | Tool Pack + reviewer role evidence | independent_review / semantic_alignment_review | `ready` | Keep reviewer independent from builder and return merge recommendation plus scores. |
| `distinct_model_acceptance` | Verification and Promotion | AAA host model gate | autopilot-review-decision -> semantic_alignment_review distinct_reviewer_model_passed | `ready` | Reuse this host gate for any LoopSpec that needs acceptance by a different model than the builder. |
| `promotion_package` | Verification and Promotion | Promotion tool output | candidate evidence promotion_package | `ready` | Keep optional signing separate from unattended execution and require human review for promotion. |
| `promotion_source_ref_pinning` | Verification and Promotion | Promotion output gate | candidate.promotion_package.source_ref_pins | `ready` | Use source pins in every promotion-review packet before opening a protected PR. |
| `promotion_review_packet` | Verification and Promotion | AAA review API | /api/autopilot/runs/{run_id}/promotion-review | `ready` | Keep promotion review packets available through the AAA API while merge/release stays disabled by default. |
| `promotion_attestation` | Verification and Promotion | Promotion provenance artifact | promotion_review.promotion_attestation | `ready` | Require provenance digest in review packets and keep signing separate from unattended execution. |
| `evidence_integrity` | Memory and State | Tool Pack | evidence_integrity | `ready` | Use section hashes and audit-chain tips in every promotion review. |
| `telemetry_rollup` | Memory and State | CLI/MCP tool | across-autopilot loop telemetry; MCP get_loop_telemetry | `ready` | Keep cross-run trends bounded and free of raw source content in API/ops surfaces. |
| `ops_dashboard` | Memory and State | AAA ops API | /api/autopilot/ops-dashboard | `ready` | Keep ops dashboard data available through the AAA API without taking over frontend page ownership. |
| `unified_capability_registry` | Tool | AAA registry API | /api/capability-registry | `ready` | Use this as the shared discovery layer while keeping AAA, Autopilot, MCP, Plugins, Models, and Tools execution boundaries separate. |
| `registry_health_compatibility` | Tool | AAA registry health API | /api/capability-registry/health | `ready` | Use this health contract before external loop chains consume unified capability data. |
| `cleanup_retention` | Memory and State | Fixed script | scripts/loop_engineering_cleanup_retention.sh | `ready` | Wire this into scheduled maintenance after retention defaults are validated in real usage. |
| `candidate_app_lifecycle` | Verification and Promotion | Fixed script + validation harness probe | scripts/candidate_app_lifecycle.sh | `ready` | Keep cleanup and crash-report checks mandatory for packaged runtime changes. |
| `full_user_level_e2e` | Verification and Promotion | Fixed script | scripts/run_loop_engineering_e2e.sh | `ready` | Use this as the default non-GUI release confidence script. |
| `solidified_e2e_gate` | Cross-layer | Fixed script | scripts/run_loop_engineering_solidified_e2e.sh | `ready` | Run this wrapper when validation must prove the solidified skill/tool contract before E2E. |
| `solidified_loop_skills` | Cross-layer | Skill artifacts | loop-engineering-skills/*/SKILL.md | `ready` | Reuse these skill artifacts across future loop engineering chains through AAA capability discovery. |
| `loop_engineering_capability_audit` | Cross-layer | Skill artifact | loop-engineering-skills/loop-capability-audit/SKILL.md | `ready` | Keep capability ownership audits grounded in the machine-readable matrix. |
| `e2e_failure_triage` | Cross-layer | Skill artifact | loop-engineering-skills/e2e-failure-triage/SKILL.md | `ready` | Use this skill only after reading the failed summary JSON and log. |
| `promotion_human_review` | Verification and Promotion | AAA review API | /api/autopilot/runs/{run_id}/promotion-review | `ready` | Keep merge/release actions disabled by default and expose review packets for human review. |
| `frontend_gui_click_validation` | Validation-only | Computer Use frontend E2E | separate Computer Use专项; no product UI change in this branch | `blocked_validation_only` | Resolve Computer Use window attach/click validation separately without changing the current product UI. |
| `computer_use_attach_diagnostic` | Validation-only | Fixed diagnostic script | scripts/check_computer_use_attach_readiness.sh | `ready` | Use only to diagnose GUI attach readiness; do not treat failure as product-capability failure. |

## Status

- `ready`: already has a deterministic Tool Pack, CLI/MCP tool, or fixed script entrypoint.
- `candidate`: useful to promote into a Codex/agent skill or future tool after the pattern repeats.
- `validation_only`: frontend or external-driver validation coverage, not a product runtime capability.
- `blocked_validation_only`: validation coverage that is currently blocked, not a product capability blocker.

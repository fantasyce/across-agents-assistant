# Loop Engineering Remaining Work

Date: 2026-06-22

Status: the A/B/C Loop Engineering runtime is review-ready on the backend/API
and plugin boundary. AAA frontend changes from the previous Workbench attempt
have been reverted; Computer Use GUI-click validation is now a separate专项 and
is not claimed as current product UI coverage. The items below track runtime
hardening plus that separate frontend-validation blocker.

## 2026-06-22 Long-Task Closure

The latest self-contained hardening pass completed the remaining product
architecture gaps that were previously listed as P1 productization work:

- Trigger productionization is now host-addressable through
  `/api/autopilot/trigger-configs`, `/api/autopilot/trigger-configs/tick`, and
  `/api/autopilot/webhooks/{trigger_id}`. Cron, webhook, and daemon/file-watch
  wakeups all enqueue into the same durable Autopilot trigger queue.
- Continuous AAA self-iteration is now host-addressable through
  `/api/autopilot/self-iteration-plan` and
  `/api/autopilot/self-iteration-plan/ensure`. The default plan registers an
  idempotent `aaa-continuous-self-iteration-daily` cron trigger for the fuzzy
  architecture-research/product-improvement LoopSpec.
- LoopSpec runtime policy is explicit and validated. Dry-run and run evidence
  include `runtime_policy` and `capability_preflight`; missing required
  capabilities fail before source discovery or mutation.
- Runtime budgets are enforced as hard gates during execution. Evidence now
  includes `runtime_budget` with model-call, candidate-repair, and timeout
  limits. AAA's host-side Autopilot run timeout defaults to 1800 seconds and is
  configurable through `ACROSS_AAA_AUTOPILOT_RUN_TIMEOUT_SECONDS`, so legitimate
  semantic-repair loops are not cut off by the host before the LoopSpec budget.
- Git/repo, dependency/security, and license review are fixed Tool Pack
  surfaces: `repo_quality_inspection`, `dependency_security_review`, and
  `license_policy_scan`.
- Candidate quality gates now include hardcoded secret literals and remote
  install scripts in addition to the earlier shell/network/placeholder/size
  checks. Mechanical formatting issues with low false-positive risk, including
  excessive blank-line runs and trailing whitespace, are blocking quality
  findings instead of review-only warnings.
- Model-generated research output now carries `candidate_comparison` evidence
  so multi-candidate B selection is explainable.
- Promotion review now includes `promotion_attestation` with a provenance digest.
  If `ACROSS_PROMOTION_SIGNING_KEY` is configured it emits an HMAC signature;
  otherwise it is explicitly `unsigned_review_only`. Merge, release, tag, and
  signing remain blocked without human approval.
- AAA exposes `/api/autopilot/ops-dashboard` for operations review across
  telemetry, triggers, capability pack state, and unified registry health.
- Two reusable skill artifacts now live in AAA:
  `loop-engineering-skills/loop-capability-audit/SKILL.md` and
  `loop-engineering-skills/e2e-failure-triage/SKILL.md`.
- Computer Use attach diagnostics are fixed as validation-only via
  `scripts/check_computer_use_attach_readiness.sh`. Product UI changes are not
  used to solve Computer Use in this branch; GUI-click validation stays in its
  own专项.
- Builder model fallback is supported for host code iteration through
  `builder_model_policy.fallback_models`, preserving model-backed development
  while avoiding a full-chain failure on one provider read timeout. Reviewer
  model separation remains enforced by `distinct_reviewer_model_passed`.

Latest solidified E2E:

```text
run_id: run-20260622T161711Z-aaa-autonomous-self-iteration
candidate_id: 20260622T161711Z-aaa-autonomous-self-iteration
selected_target_id: aaa-autopilot-research-digest-20260622t161711z
builder_model: minimax / MiniMax-M3
reviewer_model: minimax / MiniMax-M2.5
model_separation_status: passed
aaa_capability_pack_ready_count: 42
unified_capability_registry: provider_count=20 capability_count=183 model_count=59
unified_capability_registry_health_status: passed
tool_pack_evidence_count: 13
candidate_comparison_count: 3
runtime_budget_status: passed
runtime_budget_enforcement: hard
runtime_budget_usage: model_calls=5 candidate_repairs=1
self_iteration_plan_status: active
ops_dashboard_status: passed
ops_dashboard_trigger_count: 3
promotion_review: ready_for_human_review
promotion_review_open_review_pr: true
promotion_review_merge: false
promotion_review_release: false
promotion_attestation_status: passed
promotion_attestation_signing_status: unsigned_review_only
promotion_review_source_ref_pin_status: passed
promotion_review_source_ref_pin_count: 4
candidate_app_lifecycle: passed
candidate_app_path: $HOME/Applications/Across Agents Assistant Candidate.app
candidate_app_socket_path_bytes: 76
candidate_app_cleaned_up: true
candidate_app_crash_reports: []
B changed:
  across-agents-assistant/backend/src/across_agents_assistant/autopilot_research_digest.py
  across-agents-assistant/backend/tests/test_autopilot_research_digest.py
semantic_alignment_status: passed
self_hosting_probe: passed
independent_reviewer: passed
```

## Current Baseline

Completed and verified:

- A runs as the stable installed AAA controller.
- B is a four-repository candidate ecosystem under `$HOME/.across`.
- C is a disposable self-hosting probe workspace under B.
- The production `aaa-autonomous-self-iteration` LoopSpec is model-backed and
  dynamic; it is not fixed to a hard-coded file pair.
- The production self-iteration topic is now intentionally fuzzy: it asks the
  model to research current AI agent and LLM application architecture signals,
  compare them with the Across product ecosystem, and choose one bounded
  absorbable improvement for B.
- AAA host now exposes a reusable Loop Engineering capability pack through API
  and CLI-facing discovery, including deterministic scripts, Tool Packs, host
  gates, skill artifacts, and validation-only boundaries.
- AAA host exposes the continuous self-iteration plan as a separate Autopilot
  control surface, so current front-end pages can remain unchanged while a
  future dedicated Workbench consumes the same API summary.
- AAA host now also exposes `/api/capability-registry` as a unified discovery
  layer for AAA tools, agent skills/profiles, model options, managed plugins,
  and Autopilot Tool Packs while preserving each provider's executor boundary.
- AAA host exposes `/api/capability-registry/health` for compatibility and
  boundary checks, including provider presence, fallback ownership, secret
  redaction, and separate frontend-page ownership.
- AAA host exposes Autopilot trigger management through `/api/autopilot/triggers`
  and `/api/autopilot/triggers/run`, using the same durable Autopilot queue as
  the CLI/MCP path.
- AAA host exposes `/api/autopilot/runs/{run_id}/promotion-review` as a
  human-review packet over existing promotion evidence. The packet can allow
  opening a review PR, but it never grants merge, tag, release, or signing
  authority.
- `scripts/loop_engineering_cleanup_retention.sh` is now the fixed dry-run/apply
  retention entrypoint for old B/C workspaces, candidate apps, run logs, runtime
  homes, optional completed trigger records, and explicit opt-in source mirror
  cleanup.
- Promotion packages now include `source_ref_pins` for the four Across source
  repositories, and promotion review fails readiness if required source refs are
  missing or source A changed after acquisition.
- If no fixed tool or target catalog fits a user run, the host model can prepare
  a bounded fallback candidate plan, but Autopilot still applies deterministic
  repo/path admission, validation, independent review, and distinct-model
  acceptance before promotion evidence can pass.
- Acceptance review now requires a reviewer model that is different from the
  builder model when the LoopSpec declares the distinct-model gate.
- API/CLI run requests can carry user-selected builder and reviewer model
  policies from the AAA agent/model list.
- The previous GUI-triggered installed-app run completed as a historical
  backend/control-plane signal, but it is no longer used as current frontend
  acceptance after the UI changes were reverted:

```text
run_id: run-20260622T151913Z-aaa-self-iteration-product
model: minimax / MiniMax-M3
trigger: historical Computer Use GUI click
B changed:
  across-agents-assistant/backend/src/across_agents_assistant/autopilot_candidate_quality.py
  across-agents-assistant/backend/tests/test_autopilot_candidate_quality.py
semantic_alignment_status: passed
self_hosting_probe: passed
independent_reviewer: passed
promotion_ready: true
candidate_app_artifact: not produced by that historical run
```

- A previous solidified non-GUI E2E completed successfully after the fuzzy
  ecosystem topic, AAA-hosted capability pack, model-generated fallback plan,
  AAA API model overrides, distinct reviewer model gate, trigger API,
  promotion-review packet, registry-health compatibility check, cleanup
  retention script, and expanded candidate quality gates were added. It is kept
  here as historical evidence; the 42-capability E2E above is the current
  baseline:

```text
run_id: run-20260622T083122Z-aaa-autonomous-self-iteration
candidate_id: 20260622T083122Z-aaa-autonomous-self-iteration
selected_target_id: aaa-autopilot-candidate-quality-gate
builder_model: minimax / MiniMax-M3
reviewer_model: minimax / MiniMax-M2.5
model_separation_status: passed
aaa_capability_pack_ready_count: 25
unified_capability_registry: provider_count=20 capability_count=168 model_count=59
unified_capability_registry_health_status: passed
unified_registry_autopilot_fallback_executor: across-autopilot
unified_registry_frontend_pages_can_remain_separate: true
tool_pack_evidence_count: 8
model_generated_fallback_plan: passed
promotion_review: ready_for_human_review
promotion_review_open_review_pr: true
promotion_review_merge: false
promotion_review_release: false
promotion_review_source_ref_pin_status: passed
promotion_review_source_ref_pin_count: 4
B changed:
  across-agents-assistant/backend/src/across_agents_assistant/autopilot_candidate_quality_gate.py
  across-agents-assistant/backend/tests/test_autopilot_candidate_quality_gate.py
semantic_alignment_status: passed
self_hosting_probe: passed
independent_reviewer: passed
```

Validation-only frontend coverage:

- Computer Use GUI-click E2E is blocked/deferred as a separate专项. The current
  Loop Engineering branch must not change the product UI to make Computer Use
  attach. Backend socket/API E2E remains the deterministic acceptance path until
  the Computer Use专项 is fixed.

## Validation-Only: Computer Use Frontend E2E

Goal: eventually run a packaged AAA frontend click E2E with Computer Use without
changing current product UI. This validates the user-facing path separately from
the Loop Engineering runtime, while backend socket/API E2E remains the
deterministic CI-style path for the same local control plane.

Current evidence:

```text
Installed app: $HOME/Applications/Across Agents Assistant.app
Computer Use GUI-click status: separate专项 / not current acceptance evidence
last historical GUI-triggered run_id: run-20260622T151913Z-aaa-self-iteration-product
last historical B changed_files:
  across-agents-assistant/backend/src/across_agents_assistant/autopilot_candidate_quality.py
  across-agents-assistant/backend/tests/test_autopilot_candidate_quality.py
last historical candidate app artifact: not produced
current product-runtime path: backend socket/API E2E plus candidate_app_lifecycle gate
```

Repeatable local check:

- `scripts/check_computer_use_attach_readiness.sh` reports attach prerequisites
  as validation-only evidence.
- Final GUI-click validation should be addressed in the Computer Use专项. It must
  not require product UI rewrites in this branch.

Acceptance criteria:

- A clean run starts with no stale AAA or Candidate processes.
- Exactly one installed AAA frontend/backend instance remains active.
- Computer Use starts the loop from the visible app UI once the separate专项 is
  fixed.
- The resulting run completes with B diff, semantic review, self-hosting probe,
  and independent reviewer gates passed.
- Candidate app/process cleanup leaves no candidate process behind.

## P1: B Output Quality Gates

Goal: B should not only pass tests; it should produce code that is worth human
review.

Implemented in the current hardening pass:

- Candidate diff quality now flags generated-code issues before promotion:
  pytest-dependent candidate tests, excessive blank lines, placeholder branches,
  constant false branches, unsafe shell execution, unbounded network calls,
  trailing whitespace, tab indentation, long source lines, large functions,
  large generated helpers, test-only candidates, and destructive documentation
  rewrites.
- Independent reviewer evidence now includes:
  product-value score, maintainability score, risk score, merge recommendation,
  and human-review notes.
- Promotion readiness now requires no blocking code-quality finding in addition
  to B diff, validation, self-hosting probe, and semantic review.

Optional future extension:

- Expand code-quality gate coverage only where new real failures justify it:
  - language-specific formatting checks where available,
  - richer complexity scoring beyond the current large-function warning.
- Keep this gate read-only against A. It may inspect B and write evidence, but
  it must not patch B.

Acceptance criteria:

- A B candidate with syntactically valid but low-value code is rejected or marked
  `review_required`.
- A B candidate with useful low-risk helper code passes and carries reviewer
  scoring in evidence.

## P1: Tool Pack Productization

Goal: repeated mechanics should be deterministic tools, not recreated by the
model on every run.

Already present:

- trigger ingestion,
- trigger management API,
- source research digest,
- candidate workspace,
- validation harness,
- independent review,
- candidate diff quality,
- evidence integrity,
- role evidence,
- model-generated fallback plan with deterministic admission,
- distinct model acceptance through the AAA host reviewer gate,
- promotion review packet,
- promotion source-ref pinning,
- registry health and compatibility check,
- cleanup retention script,
- AAA-hosted reusable Loop Engineering capability pack.

Implemented in the latest hardening pass:

- Repository quality inspection has a fixed Tool Pack surface.
- Dependency/security review flags missing lockfiles, unpinned dependencies, and
  risky install scripts.
- License policy scan enforces the LoopSpec license allowlist.
- Candidate diff quality now includes generated-runtime filtering, code/test/doc
  reviewability, source-hygiene findings, hardcoded secret detection, and remote
  install script detection.

Optional future extension:

- Add external security-advisory lookups behind a bounded source adapter.
- Add language-specific formatters only when the candidate repo declares them.

Acceptance criteria:

- Model prompts reference stable Tool Pack outputs instead of asking the model to
  invent repository-inspection or dependency-scanning steps.
- Tool Pack outputs are JSON-schema-shaped and appear in evidence.

## P1: Promotion Package And Review Flow

Goal: B should produce a clean review package, but merge/release must remain
human-approved.

Implemented in the current hardening pass:

- Promotion evidence now contains a `promotion_package` with:
  candidate manifest path, B diff summary, changed files, model decision hash,
  validation command results, reviewer scores, known risks, recommended draft PR
  title/body, source-A-unchanged signal, and explicit human approval requirement.
- Promotion evidence now also contains `source_ref_pins`, which pins the four
  source repository refs/status hashes used to produce B and blocks promotion
  readiness if a required source pin is missing.
- AAA now exposes a review packet for one run through
  `/api/autopilot/runs/{run_id}/promotion-review`, including checklist status
  and conservative allowed actions.

Remaining work:

- Add optional signing to promotion packages.
- Add Workbench UI wiring for inspecting one promotion package through the
  existing review-packet endpoint.
- Keep commit, PR, merge, tag, and release outside autonomous execution unless a
  separate human approval gate explicitly allows them.

Acceptance criteria:

- Human reviewer can inspect one promotion package and decide whether to open a
  PR.
- Promotion package proves A source checkout was not mutated.

## P2: Trigger Productionization

Goal: manual, cron, webhook, and daemon triggers should all feed the same
LoopSpec contract.

Already present:

- durable trigger queue,
- idempotency key,
- queued trigger claim/complete state,
- replayable trigger payload evidence,
- AAA trigger management API for enqueue/list/run operations.

Remaining work:

- AAA UI controls for trigger registration and pause/resume.
- Cron scheduler service with clear local-only lifecycle.
- Webhook receiver contract, including signature verification and replay
  protection.
- Daemon watcher policy for long-running background triggers.

Acceptance criteria:

- Trigger type changes do not change LoopSpec behavior.
- Trigger payloads are persisted and visible in evidence.

## P2: Observability And Operations

Goal: long-running autonomous loops need operational visibility beyond one run.

Required work:

- Cross-run telemetry:
  - duration: present,
  - failure taxonomy: present for adapters/gates,
  - repair counts: present,
  - selected target distribution: present,
  - validation failure distribution: present,
  - reviewer recommendation distribution: present,
  - promotion-ready counts by spec: present,
  - candidate quality finding distribution: present,
  - unresolved risk distribution: present.
- Retention and cleanup script: present for run evidence, B/C workspaces,
  candidate apps, temporary runtime homes, completed trigger records, and
  opt-in source mirror cleanup. Remaining work is scheduling and dashboard
  visibility.
- UI summary for recent autonomous runs and unresolved risk trends.

Acceptance criteria:

- AAA can show whether autonomous loops are improving or repeatedly failing in
  the same place.
- Cleanup can be run without touching A source checkouts.

## P2: Trust And Security Hardening

Goal: evidence and candidate outputs should be trustworthy enough to support
release review.

Required work:

- Evidence trust chain:
  - section hashes are already present,
  - add optional signing for promotion packages,
  - record exact plugin versions used for A/B/C.
- Network and filesystem policy:
  - explicit allowlists per Tool Pack,
  - no ambient write access outside candidate/runtime roots,
  - clear redaction policy for model prompts and evidence.
- Dependency execution policy:
  - candidate validation must not download or execute untrusted code unless a
    Tool Pack explicitly declares that risk.

Acceptance criteria:

- A promotion package can be traced to exact inputs, tool versions, model
  decisions, and validation outputs.
- Secrets and raw sensitive data do not appear in evidence.

## Not Blocking Current Review

These items are not blockers for reviewing the current branch:

- Additional Tool Packs, because the core registry, schema boundary, and
  candidate diff quality pack already exist.
- Promotion automation, because autonomous merge/release is intentionally out of
  scope until human approval gates are designed.

## Fixed Skill/Tool Matrix Script

Use this script as the fixed audit entrypoint for deciding whether a Loop
Engineering step should stay a script, become a deterministic Tool Pack/CLI/MCP
tool, or graduate into an agent/Codex skill:

```bash
scripts/loop_engineering_skill_tool_matrix.sh --markdown --strict
```

Use this wrapper when the E2E must prove the solidified contract before running
the product workflow:

```bash
scripts/run_loop_engineering_solidified_e2e.sh
```

Detailed policy and step categories are tracked in
[`LOOP_ENGINEERING_SKILL_TOOL_MATRIX.md`](LOOP_ENGINEERING_SKILL_TOOL_MATRIX.md).

Current matrix result:

- 38 steps are `ready` as Tool Packs, CLI/MCP tools, deterministic
  helpers, or fixed scripts.
- 1 step is `blocked_validation_only`: Computer Use GUI-click validation.
- 0 steps remain in `candidate`.

No matrix item currently blocks the Loop Engineering runtime/API review claim.
Computer Use GUI-click validation remains a separate frontend-validation
专项. Future hardening candidates that should remain explicit but non-blocking:

- B output quality gates should continue expanding toward formatting and
  complexity checks before unattended daily operation.
- Trigger productionization can be polished into richer user-facing
  scheduler/webhook/daemon configuration forms.
- Promotion review can add optional signing UX; merge/release/signing must still
  remain human-approved.

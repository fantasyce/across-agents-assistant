# Loop Engineering Final Test Report

Date: 2026-06-22

Branch: `codex/loop-engineering-platform`

Status: implementation and validation complete for review. No commit, PR, merge,
tag, or release was performed.

## Executive Summary

The AAA-centered A/B/C Loop Engineering architecture is working end to end.
Stable AAA acts as controller A, creates a four-repository B candidate under
`$ACROSS_HOME`, uses AAA's host model boundary to choose and implement a
product-level B change, validates B, runs an independent reviewer gate, and uses
B Autopilot to mutate a disposable C probe workspace.

The latest hardening pass changed the production self-iteration prompt from a
specific local backlog item to a deliberately fuzzy external ecosystem topic:
research current AI agent and LLM application architecture signals, compare
them with AAA, Autopilot, Orchestrator, and Context, then choose one bounded
absorptive product improvement for B. The same pass also moved reusable Loop
Engineering capabilities into an AAA-hosted capability pack plus unified
capability registry and made acceptance review require a model different from
the builder model.

AAA now exposes that capability pack through backend/API discovery surfaces,
lets run requests carry builder and reviewer model policies from AAA's configured
model list, and preserves a bounded model-generated fallback plan when no fixed
tool or target catalog fits the request. The backend unified registry keeps
AAA tools, model options, managed plugins, MCP-adjacent capabilities, and
Autopilot Tool Packs discoverable without merging their execution boundaries or
front-end pages.

The latest hardening pass also fixed the remaining solidification gaps below
the frontend layer: Autopilot trigger management is exposed through AAA API,
promotion evidence has a dedicated human-review packet, registry health has a
compatibility endpoint, cleanup retention has a fixed script, and candidate
quality gates now cover shell/network/source-hygiene/complexity risks.
The next enhancement added source-ref pinning into promotion packages and made
source mirror retention explicit opt-in, so review packets can prove which
source refs produced B without risking accidental mirror deletion.

The 2026-06-22 long-task closure finished the remaining non-GUI product
hardening: trigger registry/tick/webhook/daemon control, LoopSpec runtime
policy, capability preflight, repo/dependency/license Tool Packs, multi-candidate
comparison evidence, promotion attestation, ops dashboard, repo-local skill
artifacts, validation-only Computer Use attach diagnostics, and a mandatory
candidate app lifecycle gate for AAA packaged-runtime candidates. A first full E2E
attempt exposed a builder model read timeout in host code iteration; the host now
supports `builder_model_policy.fallback_models`, so one model-provider timeout
does not abort the whole chain while the candidate remains model-backed.

The final validation pass also added the Candidate Model Capability Lease for B:
candidate runtimes receive scoped model access through A's host boundary while
raw provider credentials stay in A. The candidate app lifecycle gate now fails
unless B reports `/api/llm/status` with `availability_source` equal to
`candidate_model_lease`, `available=true`, and credential-safe flags.

Latest validation uses the packaged AAA app/backend boundary installed at:

```text
$HOME/Applications/Across Agents Assistant.app
```

The installed app backend socket completed real Loop Engineering runs through the
packaged runtime boundary. The earlier Computer Use/Workbench validation path is
no longer current acceptance evidence because the frontend changes that enabled
that path were reverted; Computer Use GUI-click validation remains a separate
专项 and must not be solved by changing the current product UI in this branch.

## Product Boundaries

AAA is the user-facing control plane and host boundary:

- macOS frontend and local backend API.
- model credentials and provider selection.
- host model, research, and code-iteration commands.
- unified capability registry discovery.
- plugin lifecycle, existing frontend presentation, and approval surfaces.

Across Autopilot is the standalone LoopSpec supervisor plugin:

- trigger/spec execution.
- Tool Pack registry.
- A/B/C candidate orchestration.
- evidence, run store, telemetry, retries, and promotion package.

Across Orchestrator remains the task/loop runtime boundary.

Across Context remains the shared memory boundary.

## A/B/C Runtime Model

A is the stable installed AAA runtime. It can write runtime data under
`$ACROSS_HOME`, but self-iteration is not allowed to mutate A's source checkout.

B is a full four-repo candidate ecosystem:

```text
$ACROSS_HOME/data/across-autopilot/candidate-workspaces/<candidate_id>/repos/
  across-agents-assistant/
  across-orchestrator/
  across-context/
  across-autopilot/
```

C is a disposable probe workspace nested under B:

```text
$ACROSS_HOME/data/across-autopilot/candidate-workspaces/<candidate_id>/probe-workspaces/
```

Candidate runtime homes use short app-safe paths:

```text
$HOME/.across/c/<runtime_key>/aaa
```

This keeps the Unix socket path under the macOS Network.framework byte limit.

## Storage And Permissions

Unattended loop runtime state is under:

```text
$HOME/.across
```

Developer checkouts remain in:

```text
$HOME/Documents/projects
```

The installed app no longer needs to read those checkouts directly during an
unattended loop. Source mirrors are prepared under:

```text
$HOME/.across/data/across-autopilot/source-mirrors/
```

Autopilot resolves sources from those mirrors, writes B/C workspaces under
`$HOME/.across/data/across-autopilot`, and writes runtime homes under
`$HOME/.across/c`.

## Final Installed-App E2E

Installed app:

```text
$HOME/Applications/Across Agents Assistant.app
bundle_id: app.acrossagents.assistant
processes: one AcrossAgentsAssistant frontend, one packaged backend
backend_socket: $HOME/.across/run/across-agents-assistant/across-agents.sock
```

Current frontend automation status:

```text
Computer Use GUI-click validation: separate专项 / not current acceptance evidence
current validated path: packaged backend socket/API E2E
product UI changes for Computer Use: reverted
```

Historical Computer Use GUI-triggered installed-app run:

```json
{
  "run_id": "run-20260622T151913Z-aaa-self-iteration-product",
  "status": "completed",
  "quality": "passed",
  "changed_files": [
    "across-agents-assistant/backend/src/across_agents_assistant/autopilot_candidate_quality.py",
    "across-agents-assistant/backend/tests/test_autopilot_candidate_quality.py"
  ],
  "required_gates": "8 passed",
  "semantic_alignment_status": "passed",
  "self_hosting_probe": "passed",
  "promotion_ready": true,
  "candidate_app_artifact": "not produced by that historical run"
}
```

The packaged backend socket E2E remains the deterministic CI-style equivalent
and current acceptance path while Computer Use frontend validation is handled as
a separate专项.

Latest solidified non-GUI Loop Engineering E2E through AAA API:

```json
{
  "run_id": "run-20260622T180056Z-aaa-autonomous-self-iteration",
  "spec_id": "aaa-autonomous-self-iteration",
  "candidate_id": "20260622T180056Z-aaa-autonomous-self-iteration",
  "selected_target_id": "tgt-aaa-autopilot-toolpack-digest-001",
  "aaa_capability_pack_ready_count": 43,
  "unified_capability_registry": {
    "provider_count": 20,
    "capability_count": 184,
    "model_count": 59,
    "health_status": "passed"
  },
  "ops_dashboard": {
    "status": "passed",
    "trigger_count": 3,
    "capability_ready_count": 43
  },
  "promotion_review": {
    "status": "ready_for_human_review",
    "open_review_pr": true,
    "merge": false,
    "release": false,
    "attestation_status": "passed",
    "attestation_signing_status": "unsigned_review_only",
    "source_ref_pin_status": "passed",
    "source_ref_pin_count": 4
  },
  "candidate_comparison_count": 3,
  "builder_model": "minimax / MiniMax-M3",
  "reviewer_model": "minimax / MiniMax-M2.5",
  "model_separation_status": "passed",
  "semantic_alignment_status": "passed",
  "self_hosting_probe": "passed",
  "independent_reviewer": "passed",
  "candidate_app_lifecycle": {
    "status": "passed",
    "availability_source": "candidate_model_lease",
    "available": true,
    "secrets_included": false,
    "raw_credentials_allowed": false,
    "socket_path_bytes": 76,
    "cleaned_up": true,
    "crash_report_count": 0
  },
  "changed_files": [
    "across-agents-assistant/backend/src/across_agents_assistant/autopilot_toolpack_digest.py",
    "across-agents-assistant/backend/tests/test_autopilot_toolpack_digest.py"
  ]
}
```

Final historical installed-app run:

```text
run_id: run-20260622T151913Z-aaa-self-iteration-product
trigger: historical Computer Use GUI click
spec_id: aaa-self-iteration-product
status: completed
risks: []
model: minimax / MiniMax-M3
quality: passed
```

Historical B candidate from that GUI-triggered run:

```text
candidate_id: 20260622T151913Z-aaa-self-iteration-product
runtime_home: $HOME/.across/c/20260622T151913Z-*
socket_path_bytes: 76
validation_status: passed
promotion_ready: true
self_hosting_probe: passed
independent_reviewer: passed
required_gates: 8 passed
evidence_integrity: across-autopilot-evidence-integrity/1.0
role_evidence: across-autopilot-role-evidence/1.0
candidate_app_artifact: not produced by that historical run
```

That historical B changed only these AAA candidate files:

```text
across-agents-assistant/backend/src/across_agents_assistant/autopilot_candidate_quality.py
across-agents-assistant/backend/tests/test_autopilot_candidate_quality.py
```

The generated B helper is a deterministic candidate quality evaluator. It rejects
no-diff, self-proof-only, and docs-only candidates before promotion review. This
aligns with the product direction: the model selects and implements a bounded B
improvement, while repeatable candidate-quality checks move into deterministic
tooling.

No manual edit was made to B. A/platform code was changed only to harden the
loop platform, backend/API runtime boundaries, and validation fallback behavior.

All required gates passed:

```text
four_repo_manifest_written
candidate_runtime_preflight_passed
candidate_b_has_code_diff
source_a_unchanged
candidate_ecosystem_validation_passed
self_hosting_probe_passed_or_not_required
semantic_alignment_passed
promotion_report_ready
```

## Autonomous Backlog Rotation

Frontend validation exposed that earlier loop-state logs were written as pretty
JSON inside `.jsonl` files. That made prior selections unreadable, so repeated
runs could keep selecting `loop_contract_policy`.

This was fixed:

- loop-state timeline appends now write single-line JSONL.
- timeline reads now skip old malformed lines instead of failing the whole read.
- recently selected targets are strongly penalized for the same spec.
- regression coverage proves a second autonomous preparation rotates away from
  the previous top target.

Evidence from real runtime runs:

```text
run-20260621T145242Z-aaa-autonomous-self-iteration
selected_target_id: loop_contract_policy
risks: []

run-20260621T145528Z-aaa-autonomous-self-iteration
selected_target_id: independent_reviewer_policy
risks: []
```

This proves the loop is not fixed to one hard-coded B file pair once readable
timeline state exists.

## Candidate App Lifecycle E2E

Full CLI E2E through AAA API also passed, including candidate app packaging and
runtime health:

```text
run_id: run-20260621T145729Z-aaa-autonomous-self-iteration
candidate_id: 20260621T145729Z-aaa-autonomous-self-iteration
selected_target_id: loop_contract_policy
model: minimax / MiniMax-M3
self_hosting_probe: passed
candidate_app_lifecycle: passed
candidate_app_cleaned_up: true
candidate_crash_reports: []
```

Candidate App lifecycle evidence:

```text
app_path: $HOME/Applications/Across Agents Assistant Candidate.app
bundle_id: app.acrossagents.assistant.candidate.20260621t145729z-aaa-autonomous-self-iteration
health.status: ok
socket_path_bytes: 76
cleaned_up: true
```

Post-hardening full Loop Engineering E2E through the AAA API was rerun after
candidate quality scoring and validation-command admission fixes:

```text
run_id: run-20260622T034647Z-aaa-autonomous-self-iteration
candidate_id: 20260622T034647Z-aaa-autonomous-self-iteration
selected_target_id: candidate-001-aaa-autopilot-contract-validator
model: minimax / MiniMax-M3
semantic_alignment_status: passed
self_hosting_probe: passed
independent_reviewer.merge_recommendation: open_review_pr
independent_reviewer.product_value_score: 90
independent_reviewer.maintainability_score: 92
independent_reviewer.risk_score: 10
telemetry_run_count: 1
```

After the skill/tool matrix, AAA capability pack, model-generated fallback plan,
API model overrides, distinct reviewer model gate, trigger API,
promotion-review packet, registry-health compatibility check, cleanup retention
script, and expanded candidate quality gates were solidified, the fixed wrapper
also passed. It first ran
`scripts/loop_engineering_skill_tool_matrix.sh --json --strict` and
`--markdown --strict`, checked the AAA-hosted Loop Engineering capability pack,
then ran the full non-GUI Loop Engineering E2E:

```text
wrapper: scripts/run_loop_engineering_solidified_e2e.sh
wrapper_status: passed
matrix_ready_steps: 38
matrix_validation_only_steps: 0
matrix_candidate_steps: 0
matrix_blocked_validation_only_steps: 1
aaa_capability_pack_ready_count: 43
run_id: run-20260622T180056Z-aaa-autonomous-self-iteration
candidate_id: 20260622T180056Z-aaa-autonomous-self-iteration
selected_target_id: tgt-aaa-autopilot-toolpack-digest-001
strategy_status: passed
strategy_admission_status: passed
model_generated_fallback_plan: passed
unified_capability_registry_provider_count: 20
unified_capability_registry_capability_count: 184
unified_capability_registry_model_count: 59
unified_capability_registry_health_status: passed
unified_registry_autopilot_fallback_executor: across-autopilot
unified_registry_frontend_pages_can_remain_separate: true
promotion_review.status: ready_for_human_review
promotion_review.open_review_pr: true
promotion_review.merge: false
promotion_review.release: false
promotion_review.source_ref_pin_status: passed
promotion_review.source_ref_pin_count: 4
tool_pack_evidence_count: 13
builder_model: minimax / MiniMax-M3
reviewer_model: minimax / MiniMax-M2.5
model_separation_status: passed
semantic_alignment_status: passed
self_hosting_probe: passed
candidate_app_lifecycle: passed
candidate_app_path: $HOME/Applications/Across Agents Assistant Candidate.app
candidate_app_socket_path_bytes: 76
candidate_app_cleaned_up: true
candidate_app_crash_reports: []
independent_reviewer.merge_recommendation: open_review_pr
independent_reviewer.product_value_score: 95
independent_reviewer.maintainability_score: 90
independent_reviewer.risk_score: 10
telemetry_run_count: 1
```

That historical B candidate changed only these files:

```text
across-agents-assistant/backend/src/across_agents_assistant/autopilot_research_digest.py
across-agents-assistant/backend/tests/test_autopilot_research_digest.py
```

This run proves the fuzzy topic is not a hard-coded file pair. The model
generated and compared three candidate directions across AAA, Orchestrator, and
Autopilot, then selected an AAA research-digest helper as the lowest-risk
absorptive product improvement for B. Deterministic gates still enforced
generated-target admission, B-only edits, validation, candidate app lifecycle,
promotion evidence, distinct-model acceptance, source-ref pinning,
registry-health compatibility, and conservative promotion-review actions.

## Fixes From Final Validation

1. Resolved-risk aggregation now reports only unresolved risks. A failed
   validation followed by a passed repair remains in action history, but no
   longer pollutes final `risks`.

2. Loop-state JSONL is now real single-line JSONL and tolerates old malformed
   development entries.

3. Dynamic backlog now rotates away from recently selected targets for the same
   spec, preventing repeated identical self-iteration outputs.

4. The installed Autopilot host plugin was reinstalled from the current local
   source before packaged-app E2E so the AAA backend exercised the latest
   supervisor code.

5. Running Autopilot evidence now writes incremental snapshots. During the final
   installed-app E2E, `evidence.json` showed
   `product_iteration_strategy: running` and then `host_code_iteration: running`
   before the run completed, instead of remaining `{}` until the end.

6. Production research-decision repair now handles directory-level patch path
   mistakes. A packaged-app runtime run exposed the model returning
   `backend/src/across_agents_assistant/` in `allowed_patch_paths`; production
   fallback correctly rejected it, but repair guidance was too weak. AAA now
   requires concrete repository-relative file paths, forbids directory/prefix
   paths ending in `/`, documents the policy in the generation contract, and
   allows one additional repair attempt before failing with evidence.

7. Autopilot now has a durable trigger queue with idempotency, claim/completion
   state, and replay metadata. The same trigger schema is used by stored runs
   and queued triggers.

8. Tool Pack boundaries are now schema-backed. Runtime packs declare stable
   inputs, outputs, owner roles, and runtime capabilities, so deterministic
   mechanics stay outside model prompt improvisation.

9. Evidence now carries section hashes, audit-chain metadata, and explicit role
   separation evidence. Final acceptance can verify that planner/builder/
   inspector/validator/reviewer/supervisor responsibilities were distinct.

10. Candidate quality and promotion evidence were hardened after the initial
    report. Autopilot now exposes a `candidate_diff_quality` Tool Pack, rejects
    pytest-dependent candidate tests, test-only candidates, excessive blank-line
    artifacts, placeholder branches, constant false branches, unsafe shell
    execution, unbounded network calls, trailing whitespace, tab indentation,
    long source lines, large functions, and destructive documentation rewrites
    before promotion. Independent reviewer evidence now carries product-value,
    maintainability, and risk scores plus a merge recommendation and
    human-review notes.

    The latest quality hardening promotes excessive blank-line runs and trailing
    whitespace to blocking deterministic findings. They are low-noise mechanical
    issues and should be repaired by B before a candidate is review-ready.

11. Promotion evidence now includes a structured promotion package with candidate
    manifest path, B diff summary, changed files, model decision hash,
    validation command results, reviewer scores, known risks, recommended draft
    PR title/body, source-A-unchanged signal, and explicit human approval
    requirement. Promotion evidence also includes `source_ref_pins`, which pins
    the four Across source repository refs/status hashes and blocks promotion
    readiness when a required source pin is missing or source A changed.

12. Aggregate Autopilot telemetry now includes selected target distribution,
    validation failure distribution, repair counts, reviewer recommendations,
    promotion-ready counts by spec, candidate quality finding distribution, and
    unresolved risk distribution without raw source text.

13. Production self-iteration now uses external AI ecosystem architecture
    signals as the fuzzy topic source. The model judges the topic and selected
    B target; Tool Packs and scripts keep source digest, workspace, validation,
    review, and promotion mechanics deterministic.

14. AAA now exposes a reusable Loop Engineering capability pack through API and
    CLI-facing discovery. It currently reports 43 ready capabilities and keeps
    validation-only GUI checks separate from current acceptance.

15. Acceptance review now records the builder and reviewer model identities in
    evidence and fails the run if the required reviewer model matches the
    builder model. The latest E2E passed with builder `MiniMax-M3` and reviewer
    `MiniMax-M2.5`.

16. User-selected builder/reviewer model policies can now travel from AAA
    API/CLI run requests to Autopilot. Autopilot merges them into
    role-specific model policies at run time while preserving the distinct
    reviewer gate.

17. Research strategy readiness now treats an admitted selected iteration as
    executable unless the model explicitly rejects, skips, fails, or defers it.
    This keeps fuzzy-topic runs from failing only because a model used words such
    as `review` instead of exactly `implement`, while still preserving
    deterministic admission and negative-decision blocking.

18. AAA now exposes `/api/capability-registry` as a unified discovery layer
    plus `/api/capability-registry/health` as the compatibility check. The
    latest E2E verified 20 providers, 183 capabilities, 59 model options,
    health status `passed`, Autopilot fallback execution owned by
    `across-autopilot`, and front-end pages remaining separate.

19. AAA now exposes Autopilot trigger management through
    `/api/autopilot/triggers` and `/api/autopilot/triggers/run`, reusing the
    durable Autopilot trigger queue instead of creating a parallel scheduler
    contract.

20. AAA now exposes `/api/autopilot/runs/{run_id}/promotion-review` as the
    fixed human-review packet. The latest E2E verified status
    `ready_for_human_review`, `open_review_pr=true`, and both `merge=false` and
    `release=false`.

21. `scripts/loop_engineering_cleanup_retention.sh` now provides the fixed
    dry-run/apply retention entrypoint for old B/C workspaces, candidate apps,
    run logs, temporary runtime homes, optional completed trigger records, and
    explicit opt-in source mirror cleanup.

## Verification Matrix

AAA:

```text
backend full tests: 760 passed, 20 skipped, 1 warning
targeted Autopilot/API/doc/retention tests: 40 passed, 1 warning
Swift behavior checks: passed
Swift build: passed
open-source check: passed
git diff --check: passed
installed-app backend socket E2E: passed
isolated Loop Engineering E2E: passed
solidified skill/tool matrix audit: passed
solidified Loop Engineering E2E wrapper: passed
Computer Use GUI-click E2E: blocked/deferred as separate frontend专项
```

Autopilot:

```text
npm run check: 50 tests passed, CLI help passed, MCP help passed
git diff --check: passed
```

Orchestrator:

```text
uv run --extra dev pytest -q: 140 passed, 2 subtests passed
git diff --check: passed
```

Context:

```text
npm test: 68 passed
npm run check: passed
git diff --check: passed
```

## Acceptance Conclusion

The current Loop Engineering platform increment is ready for external review:

- A remains stable and does not mutate its own source checkout.
- B is a real four-repo candidate ecosystem and receives model-backed product
  code changes.
- C proves B can perform a nested self-hosting probe.
- source acquisition and runtime state are under `$HOME/.across`.
- MiniMax-M3 is used through AAA's host model boundary.
- Acceptance review is model-backed and must use a distinct model; latest E2E
  used MiniMax-M2.5 as reviewer against MiniMax-M3 as builder.
- Tool Packs handle deterministic git/source/candidate/validation/review
  mechanics.
- AAA host stores the reusable Loop Engineering capability pack so other loop
  chains can reuse the same fixed scripts, Tool Packs, host gates, and skill
  artifacts; the latest pack reports 43 ready capabilities.
- AAA host exposes the unified capability registry so other loop chains can
  discover tools, skills, models, plugins, and Autopilot Tool Packs without
  merging product or front-end boundaries, and the registry health endpoint now
  verifies that boundary.
- trigger management, cleanup retention, source-ref pinning,
  promotion-review packets, and expanded candidate quality gates are now fixed
  API/script/tool surfaces.
- dynamic backlog selection, independent review, validation repair, and final
  evidence gates are all verified.
- latest full solidified E2E passed with
  `run-20260622T180056Z-aaa-autonomous-self-iteration`; B changed
  `backend/src/across_agents_assistant/autopilot_toolpack_digest.py` and
  `backend/tests/test_autopilot_toolpack_digest.py`, used MiniMax-M3 as builder,
  used MiniMax-M2.5 as distinct reviewer, passed candidate app lifecycle with
  crash report count 0, and cleaned up the candidate app process.
- Computer Use GUI-click validation is not claimed for this branch after the
  frontend restore; the current acceptance path is packaged backend socket/API
  E2E plus the candidate app lifecycle gate.
- remaining work is tracked in
  [`LOOP_ENGINEERING_REMAINING_WORK.md`](LOOP_ENGINEERING_REMAINING_WORK.md).

No merge, tag, or release was performed.

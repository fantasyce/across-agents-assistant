# Loop Engineering Platform Acceptance Report

Date: 2026-06-20

Status: implementation complete on `codex/loop-engineering-platform`. Not
released.

Architecture note: this report validates the platform and candidate pipeline
implementation on the local branch. Fixed-target self-iteration LoopSpecs are
classified as conformance fixtures; fixed-target AAA self-iteration is not the
production autonomous loop. The production
`aaa-autonomous-self-iteration` path now follows
[`LOOP_ENGINEERING_REFERENCE_ARCHITECTURE.md`](LOOP_ENGINEERING_REFERENCE_ARCHITECTURE.md):
it lets the host model generate candidate targets from artifacts, loop
contracts, global timeline entries, source signals, Tool Pack evidence, and
recalled memory, then admits only policy-safe B changes.
Host fallback targets and host-authored code templates are accepted only for
explicit conformance fixtures.

Remaining product-completion work is tracked in
[`LOOP_ENGINEERING_REMAINING_WORK.md`](LOOP_ENGINEERING_REMAINING_WORK.md).

Latest acceptance update on 2026-06-22:

- AAA capability pack ready count is now 43.
- Trigger registry, cron tick, webhook receiver, daemon watch policy, runtime
  policy, capability preflight, repo/dependency/license Tool Packs,
  multi-candidate comparison, promotion attestation, ops dashboard, and
  repo-local skill artifacts are implemented.
- Full solidified E2E passed with
  `run-20260622T180056Z-aaa-autonomous-self-iteration`. The latest B selected
  and implemented an AAA tool-pack digest helper, validated the packaged
  candidate app lifecycle, proved B model availability through
  `candidate_model_lease`, and left no candidate app process behind.
- Computer Use remains validation-only and is currently a separate专项 after the
  frontend restore. The historical GUI-triggered
  `run-20260622T151913Z-aaa-self-iteration-product` remains backend/control-plane
  evidence, not current frontend acceptance.

Latest hardening:

- Production autonomous loops fail with evidence if model-generated targets or
  code patches cannot be repaired; validation-repair fallback is bounded to the
  model-selected B module/test pair and never mutates source A or raw secrets.
- External Tool Pack command failures preserve bounded command, stdout, stderr,
  exit code, and structured-output diagnostics in run evidence.
- Candidate diff and promotion evidence filter validation/runtime artifacts
  such as `__pycache__` and `.pyc`.
- Independent semantic review rejects large destructive documentation rewrites
  unless explicitly justified by the selected target.
- Independent semantic review rejects suspicious generated-code artifacts such
  as constant false branches and placeholder implementations.
- Semantic-review failures can trigger a bounded B-only model repair loop before
  final promotion evidence is produced.
- Autopilot writes incremental `evidence.json` snapshots while a run is still
  executing, so host UI and monitors can inspect running actions without
  scraping `audit.jsonl` directly.
- Production research-decision repair explicitly converts directory-level
  `allowed_patch_paths` into concrete file paths; autonomous runs still fail
  with evidence if model repair cannot produce admissible paths.

## Scope

This work replaces the earlier partial Autopilot control-plane drafts with a
complete four-product Loop Engineering platform:
it does not merely add an autonomous loop; it adds reusable trigger, contract,
memory, tool, orchestration, verification, and promotion boundaries.

- Across Agents Assistant: host plugin lifecycle, HTTP API, existing frontend
  control plane, local E2E runner.
- Across Autopilot: reusable LoopSpec supervisor, adapter registry, run store,
  audit log, evidence, telemetry, CLI, MCP, host-plugin runtime.
- Across Orchestrator: Autopilot metadata validation and non-secret reflection
  in loop status/evidence.
- Across Context: loop memory recall, pending memory write policy, history,
  diff, and MCP tools.

## Product Boundary

- AAA remains the user-facing control plane and does not import Autopilot,
  Orchestrator, or Context internals.
- Autopilot owns LoopSpec validation, supervision, adapter execution, evidence
  aggregation, telemetry, and governance controls.
- Orchestrator owns task execution and Agent Loop runtime. Autopilot metadata is
  accepted only through the loop metadata contract.
- Context owns memory policy and vault lifecycle. Autopilot writes pending
  summaries only.

## User-Level E2E

Command:

```bash
bash scripts/run_loop_engineering_e2e.sh
```

What it does:

1. Creates a temporary `ACROSS_HOME`.
2. Installs managed Across Context and Across Autopilot host-plugin runtimes.
3. Starts the AAA backend over HTTP.
4. Calls AAA `/api/autopilot/*` endpoints as a user-level control plane.
5. Runs the built-in `daily-news-brief` LoopSpec through Autopilot.
6. Autopilot delegates execution to Across Orchestrator and memory to Across
   Context.
7. Verifies evidence, events, telemetry, outputs, and pending memory.

Latest result:

```json
{
  "events": 27,
  "memory_status": "accepted_pending",
  "orchestrator_loop": "loop-c7c1540ef1",
  "outputs": [
    "json_artifact",
    "markdown_report",
    "media_storyboard",
    "video_draft_manifest"
  ],
  "run_id": "run-20260620T161518Z-daily-news-brief",
  "spec_id": "daily-news-brief",
  "telemetry_run_count": 1
}
```

## Packaged App E2E

Command path:

```text
$HOME/Applications/Across Agents Assistant.app
```

What it does:

1. Kills prior AAA frontend/backend/Orchestrator app processes.
2. Installs managed Context, Orchestrator, and Autopilot plugin runtimes under
   `~/.across`.
3. Builds the packaged AAA app with `build_app.sh`.
4. Copies the bundle to `$HOME/Applications/Across Agents Assistant.app`.
5. Verifies the copied bundle with `codesign --verify --deep --strict`.
6. Opens the copied app and verifies the packaged backend socket.
7. Triggers Loop Engineering runs through the installed app backend socket/API;
   Computer Use frontend click validation is a separate专项 and is not used as
   current acceptance evidence.
8. Verifies the persisted Autopilot run evidence, events, and telemetry.

Latest packaged-app validation uses the packaged backend Unix socket/API as the
deterministic acceptance path. Computer Use GUI-click validation is deferred to a
separate专项 and must not require product UI changes in this branch.

Latest solidified autonomous self-iteration result:

```json
{
  "run_id": "run-20260622T180056Z-aaa-autonomous-self-iteration",
  "spec_id": "aaa-autonomous-self-iteration",
  "candidate_id": "20260622T180056Z-aaa-autonomous-self-iteration",
  "selected_target_id": "tgt-aaa-autopilot-toolpack-digest-001",
  "model_backed": true,
  "builder": "minimax / MiniMax-M3",
  "reviewer": "minimax / MiniMax-M2.5",
  "changed_files": [
    "across-agents-assistant/backend/src/across_agents_assistant/autopilot_toolpack_digest.py",
    "across-agents-assistant/backend/tests/test_autopilot_toolpack_digest.py"
  ],
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
  "semantic_alignment_status": "passed",
  "self_hosting_probe": "passed",
  "independent_reviewer": "passed",
  "promotion_review": "ready_for_human_review"
}
```

Historical installed-app autonomous self-iteration result:

```json
{
  "run_id": "run-20260622T151913Z-aaa-self-iteration-product",
  "spec_id": "aaa-self-iteration-product",
  "status": "completed",
  "trigger": "historical Computer Use GUI click",
  "model_backed": true,
  "provider": "minimax",
  "model": "MiniMax-M3",
  "changed_files": [
    "across-agents-assistant/backend/src/across_agents_assistant/autopilot_candidate_quality.py",
    "across-agents-assistant/backend/tests/test_autopilot_candidate_quality.py"
  ],
  "semantic_alignment_status": "passed",
  "self_hosting_probe": "passed",
  "independent_reviewer": "passed"
}
```

Latest installed-app GitHub clone result:

```json
{
  "run_id": "run-20260620T171845Z-live-github-plugin-radar",
  "spec_id": "live-github-plugin-radar",
  "status": "completed",
  "events": 29,
  "source_kind": "github_repo",
  "file_count": 44,
  "package_json": true,
  "outputs": ["json_artifact", "markdown_report"],
  "memory_status": "accepted_pending",
  "metadata_reflected": true
}
```

AAA self-iteration mutation result:

```json
{
  "run_id": "run-20260620T203751Z-aaa-self-iteration-ui-model-20260620-195346",
  "spec_id": "aaa-self-iteration-ui-model-20260620-195346",
  "status": "completed",
  "trigger": "aaa-workbench-installed-app-structured-final-e2e-2",
  "model_backed": true,
  "provider": "minimax",
  "model": "MiniMax-M3",
  "decision_hash": "80ef73e26d62133976aa194fe0535340c7f1045589a53eae38ea921e74b4a24b",
  "candidate_workspace": "$ACROSS_HOME/data/across-autopilot/candidate-workspaces/<run>/across-agents-assistant",
  "source_repository": "$SOURCE_REPOSITORY",
  "mutation_policy": "candidate_workspace_only",
  "changed_files": ["LOOP_ENGINEERING_SELF_ITERATION.md"],
  "validation": ["git diff --check:passed"],
  "gates": [
    "model_decision_present:passed",
    "source_repository_not_targeted:passed",
    "candidate_has_diff:passed",
    "candidate_validation_passed:passed"
  ],
  "event_count": 29,
  "promotion_ready": true,
  "outputs": ["json_artifact", "markdown_report"],
  "memory_status": "accepted_pending",
  "metadata_reflected": true
}
```

The model-backed `aaa-self-iteration` run is triggered through the installed
packaged app backend socket. AAA supplies the model decision through the host command boundary,
Orchestrator records model-decision evidence, Autopilot applies only the
returned candidate-workspace patch, validates the diff, and leaves the source
repository outside the mutation target.

Built-in pack coverage:

- `daily-news-brief`: passed through AAA HTTP E2E.
- `github-plugin-radar`: passed through packaged AAA app E2E.
- `aaa-release-readiness-gate`: passed through installed Autopilot CLI with
  Orchestrator and Context integration.
- `live-github-plugin-radar`: registered custom LoopSpec passed through
  packaged AAA app E2E with a real GitHub clone.
- `aaa-self-iteration`: registered custom LoopSpec passed through packaged AAA
  app E2E against a copied AAA candidate workspace, producing a real
  candidate diff and promotion-ready report.

Installed-app visible/backend result:

- Backend registry shows 3 built-in specs.
- Registered custom LoopSpecs are runnable by id through the API/CLI control
  plane.
- `Live GitHub Plugin Radar` clones a real public GitHub repository through the
  `github_repo` source adapter.
- The latest accepted run completes through the installed app backend socket/API.
- The UI shows `quality passed`, `1 task(s)`, `1 memory write(s)`,
  `0 risk(s)`, Orchestrator metadata reflection, Context pending memory, and
  written outputs.
- `AAA Self Iteration Candidate Mutation` reports `candidate_workspace_only`,
  the source repository path, the candidate workspace path, changed files,
  validation commands, gate results, actions, and final promotion readiness.
- Model-backed self-iteration reports provider/model/decision hash in
  Orchestrator task evidence and stores only non-secret model provenance in
  Context pending memory.

Issues found and fixed by packaged-app/backend E2E:

- Autopilot registry returned an unstable shape (`registered` as an object and
  built-ins as nested raw specs), so AAA fell back to a single hard-coded
  `daily-news-brief` picker option. Autopilot now returns normalized summaries,
  and AAA remains backward-compatible with the legacy nested shape.
- Packaged app launches did not inherit interactive shell `PATH`, so Autopilot
  could not spawn `across-orchestrator`. Autopilot now resolves ecosystem
  commands from `$ACROSS_HOME/bin` before falling back to `PATH`.
- `github_search` fixture repositories exposed package manifests under nested
  repository files, but `manifest_inspection` only inspected top-level files.
  The adapter now inspects nested repository files.
- `github_repo` URLs did not clone repositories into the run sandbox. The
  adapter now performs shallow git clones and scans the cloned files.
- Registered LoopSpecs were visible in the host registry but not runnable by id.
  The supervisor now resolves registered ids to their stored `source_path`.
- Failed runs discarded partial actions/gates before evidence generation. The
  supervisor now preserves partial evidence for failed gate paths.
- The first self-iteration LoopSpec only performed readiness analysis. Autopilot
  now supports candidate-only patching, candidate diff summaries, candidate
  validation commands, and promotion reports so self-iteration can produce a
  reviewable repository change without mutating the source checkout.
- A first mutation attempt wrote under ignored `docs/`, so the candidate diff
  gate correctly failed. The registered LoopSpec now writes
  `LOOP_ENGINEERING_SELF_ITERATION.md`, which is visible to git status and
  promotion evidence.

## Validation

Across Autopilot:

```bash
npm run check
```

Result: 17 tests passed; CLI and MCP help checks passed.

Across Context:

```bash
npm run check
```

Result: 68 tests passed; CLI and MCP help checks passed.

Across Orchestrator:

```bash
/opt/homebrew/bin/uv run --with pytest --python 3.12 python -m pytest -p no:cacheprovider tests -q
```

Result: 139 tests passed, 2 subtests passed; npm audit found 0 high
vulnerabilities.

Across Agents Assistant backend:

```bash
PYTHONPATH=backend/src backend/.venv/bin/python -m pytest backend/tests --ignore=backend/tests/e2e -q
```

Result: 690 tests passed, 1 warning.

Across Agents Assistant Swift:

```bash
bash scripts/run_swift_behavior_checks.sh
cd macOS-Client && swift build
cd macOS-Client && swift test
```

Result: Swift behavior checks passed; SwiftPM build/test passed.

Across Agents Assistant open-source checks:

```bash
bash scripts/open_source_check.sh
```

Result: passed.

Whitespace:

```bash
git diff --check
```

Result: passed in all four repositories.

## Review Notes

- The E2E intentionally uses real product boundaries: AAA HTTP API calls the
  installed Autopilot plugin command, Autopilot calls Orchestrator and Context,
  and Context persists pending memory under the temporary `ACROSS_HOME`.
- The E2E is not a Codex-assisted demo path. Codex only runs the test command;
  the workflow itself is executed by the four Across products.
- Earlier partial branches were closed/deleted and stale remote-tracking refs
  were pruned. The retained implementation branch in each repo is
  `codex/loop-engineering-platform`.
- No release tags were created.

## 2026-06-21 Addendum

The research-driven AAA self-iteration pack was revalidated after adding a
bounded validation-repair loop.

Latest installed-app backend run:

```text
run-20260621T103300Z-aaa-research-driven-self-iteration
```

Result:

- MiniMax-M3 selected `research_signal_quality`.
- B changed only the AAA candidate copy:
  - `backend/src/across_agents_assistant/autopilot_research_signal.py`
  - `backend/tests/test_autopilot_research_signal.py`
- The first direct test execution failed with an import-path
  `ModuleNotFoundError`.
- A invoked `host_code_iteration_repair` with validation feedback.
- The repair patch fixed the generated test import path.
- The second validation passed all declared commands.
- Semantic alignment passed.
- C self-hosting probe passed.
- Promotion evidence reports `promotion_ready: true`.

Final Computer Use status:

- separate专项 after frontend restore;
- not current acceptance evidence for this branch;
- backend Unix socket/API E2E remains the deterministic acceptance path for CI
  and local validation;
- Computer Use attach/click validation must be solved without product UI
  rewrites.

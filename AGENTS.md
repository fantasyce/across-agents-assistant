# AGENTS.md

## Project Overview

Across Agents Assistant is the desktop control room for the Across ecosystem.
The public product position is supervised engineering loops for coding agents:
repo quality reviews, release readiness checks, plugin compatibility reviews,
and human-approved autonomous product iteration.

The codebase is one product in a four-repository system:

- Across Agents Assistant owns macOS UI, backend APIs, provider settings,
  approvals, local agent discovery, plugin lifecycle, and evidence views.
- Across Autopilot owns LoopSpec supervision and built-in workflow packs.
- Across Orchestrator owns durable task execution, quality gates, and evidence.
- Across Context owns local memory, policy, pending review, and context packs.

## Recommended First Workflow

When asked to demonstrate Across, lead with Repository Quality Copilot:

```bash
across-autopilot loop run --spec repo-quality-copilot --json
```

Expected output is a markdown repo-quality report, JSON evidence, release
readiness notes, and optional pending memory.

## Setup And Checks

Use a Python virtual environment for backend checks when possible.

```bash
PYTHONPATH=backend/src python -m pytest backend/tests/test_release_version_consistency.py backend/tests/test_versioning.py -q
bash scripts/open_source_check.sh
bash scripts/run_swift_behavior_checks.sh
PYTHONPATH=backend/src python -m pytest backend/tests --ignore=backend/tests/e2e -q
bash scripts/verify_swift_package_lock.sh
swift build --package-path macOS-Client --skip-update
bash scripts/run_swift_tests.sh
```

Run Live E2E only when an external Across Orchestrator command is available:

```bash
ACROSS_AGENTS_ORCHESTRATOR_COMMAND=/path/to/across-orchestrator \
ACROSS_AGENTS_LIVE_E2E_EVIDENCE_PATH="$(mktemp /tmp/across-live-e2e.XXXXXX)" \
  bash scripts/run_live_e2e.sh all
```

## Frontend Design Standard

`docs/product-experience.md` is the authoritative frontend handbook for every
main page, detail view, settings surface, sheet, inspector, and empty state.
Reuse the shared page frame, headers, semantic tokens, status components, and
disclosure rows described there. Do not introduce direct `DisclosureGroup`
usage, decorative gradients, blue selection borders, legacy page headers, or
one-off page geometry. Run this guard before Swift tests and formal UI review:

```bash
python3 scripts/audit_frontend_design.py
```

## Product Packaging Rules

- Keep the first explanation workflow-first, not module-first.
- Prefer "supervised engineering loops" over "three plugins" as the product
  framing.
- Put implementation details after the user workflow.
- Use `llms.txt` and `across.product.json` as authoritative agent-readable
  product entrypoints.
- Keep docs under `docs/` as internal local notes unless the release policy is
  intentionally changed.
- The formal local packaged app is `/Applications/Across Agents Assistant.app`.
  Use `bash scripts/build_and_run.sh` to refresh it; do not create or rely on
  duplicate long-lived AAA app copies under `~/Applications`.
- Self-iteration B app bundles are temporary candidate artifacts under
  `~/.across/data/across-autopilot/candidate-apps/<candidate_id>/`, not local
  installed apps. They may be promoted only through a reviewed formal
  release/install path.

## Managed Plugin Packaging And Lifecycle

Across Context, Across Orchestrator, and Across Autopilot are three equal
first-party managed plugins. A problem first observed in one plugin must be
treated as a possible class-wide packaging or lifecycle defect: inspect and
verify all three plugins instead of special-casing only the plugin that exposed
the symptom.

- Keep four layers consistent for every plugin: the producer repository, the
  payload and catalog bundled in AAA, the installed copy and its provenance
  under `~/.across`, and any live process consuming that copy. The presence of
  an archive, manifest, executable, or process proves only that layer.
- A formal AAA rebuild can change bundled payload bytes without changing the
  plugin version. After every formal rebuild, query all three installed plugin
  records. `status=installed`, `available=true`, and `integrity_ok=true` must
  all hold; a missing or mismatched checksum/provenance record requires a real
  repair or upgrade, not suppression of the warning.
- Install, repair, upgrade, uninstall, and rollback are host-managed atomic
  lifecycle operations. Stop or drain dependent runtimes before replacing
  files, install through a staging path, commit the payload and provenance
  together, restart every affected consumer, and verify health and reconnect.
  On failure, restore the previous verified runtime rather than leaving a
  partially replaced plugin.
- Runtime reconciliation applies to each plugin's consumers, not only Worker
  services. Orchestrator task/Worker services, Context memory consumers, and
  Autopilot workflow or scheduler consumers must not continue using deleted,
  stale, or pre-upgrade code after a lifecycle action.
- AAA must never import plugin implementation files from a development
  checkout. Formal runtime resolution must use the managed installed plugin,
  and packaging must not silently fall back to a nearby source tree.
- Packaging gates must run for all three payloads and verify the expected
  version, compatible plugin API, required entrypoints and capabilities,
  executable behavior, and required command flags. Checking only that an
  archive exists is insufficient.
- Exercise clean install, same-version repair, version upgrade, rollback, and
  uninstall in an isolated `ACROSS_HOME` for every managed plugin. Then perform
  a separate installed-App smoke test through `/Applications/Across Agents
  Assistant.app` and the commands under `~/.across/bin`.
- Scan both source and final packaged archives for credentials, absolute
  developer paths, build caches, and test-only content. Test placeholders must
  not resemble real credential prefixes because release scanners correctly
  treat those strings as leaks.
- A release candidate is not ready while any first-party plugin reports
  `needs_repair`, has a version/catalog mismatch, fails its probe, or leaves a
  dependent runtime disconnected. Recheck all three after repairing any one.

Minimum formal smoke coverage is plugin-specific but symmetric: Context must
prove health and governed memory access, Orchestrator must prove task and Worker
control health, and Autopilot must prove workflow validation and execution
delegation. Run these against installed payloads, not producer checkouts.

## Completion And Regression Rules

- Use the evidence ladder `source -> packaged payload -> installed runtime ->
  live service -> user-visible state`. A lower layer passing cannot be used to
  claim that a higher layer works.
- Treat packaged-App user journeys UJE-001 through UJE-008 in
  `docs/engineering-handbook.md` as release-blocking when applicable. Run the
  core journeys immediately after targeted tests, before expensive full
  regression, so UI/runtime defects are found early rather than at handoff.
- Accessibility trees, screenshots, API responses, unit tests, and successful
  builds are supporting evidence only. A user journey passes only after the
  formal App uses real controls to submit, observe, inspect, and complete the
  applicable decision or recovery path.
- Any later source edit, plugin payload rebuild, or formal App reinstall
  invalidates affected UI evidence. Rerun those journeys on the final installed
  bytes and record task identities, visible states, repository/data
  fingerprints, and cleanup.
- Fix the defect class, not only the observed example. When a checksum,
  lifecycle, restart, version, permission, cleanup, or UI-state bug is found,
  add coverage for sibling plugins and other consumers that share the same
  mechanism.
- Source tests and a successful build are not final acceptance. Rebuild the
  formal App, verify its signature and version, launch that copy, probe its
  Unix Socket APIs, and confirm that the installed plugin commands and live
  services use the newly packaged code.
- Local control sockets must be private at creation time and verify as `0600`
  after launch. Do not rely on a delayed permission repair that races with the
  server recreating its socket.
- Process presence alone is not service health. Verify the API or protocol
  health response, expected version, dependent-service status, and remote
  reconnect where applicable. Account for supervisor/child process models
  before reporting duplicate services.
- Never re-verify a signed receipt after a public projection has redacted or
  normalized fields covered by its hash. Prefer the top-level receipt when its
  hash still verifies; otherwise use only a hash-valid durable terminal-event
  receipt bound to the same Job, Run, Node, manifest, and terminal state. Do
  not trust an external `verified` boolean or weaken the receipt contract.
- Automated tests must use task-owned databases, ports, certificates,
  identities, plugin homes, sandboxes, and artifact roots. They must never
  write acceptance fixtures into the user's formal task, memory, approval, or
  plugin state.
- After live acceptance, remove task-owned Tasks, Loops, events, approvals,
  grants, leases, artifacts, logs, sandboxes, test identities, temporary
  archives, test App copies, and build caches. Preserve only explicitly named
  candidate runtimes and verified rollback slots. Active runtime unpack
  directories are not residue, but stale ones from exited processes are.
- Recheck proxy, DNS, default route, VPN, firewall, and network-extension
  baselines after remote-worker testing. Never change those host settings to
  make a test pass.
- Do not claim a final visual check when the graphical session is locked.
  Wake display-only sleep with the documented method, but require a manual
  unlock when macOS authentication is active and clearly record that remaining
  evidence boundary.
- Report skipped tests explicitly and distinguish optional environment probes
  from mandatory product coverage. No required test may be hidden behind an
  unexplained skip.

## Boundary Rules

- Do not make AAA import implementation files from development checkouts of
  Autopilot, Orchestrator, or Context.
- Keep the zero-plugin product baseline usable. With no managed plugins, AAA
  must still start and provide projects, sessions, direct work through an
  available Agent/model, settings, plugin installation, and growth. Missing
  Orchestrator automatically degrades Work to direct Agent mode; missing
  Autopilot degrades inferred tasks to a generic plan but must block an
  explicitly requested Workflow Pack. Hide unavailable plugin-owned surfaces
  instead of rendering empty shells. Test this in an isolated `ACROSS_HOME`;
  never uninstall the user's formal plugins to manufacture the case.
- Keep the host task surface domain-neutral. A complex example such as world
  simulation, repository review, or release readiness is a Workflow Pack use
  case, not an AAA task type. Users enter an ordinary goal; Autopilot resolves
  and plans the pack; Orchestrator and Worker receive only versioned generic
  execution contracts; AAA renders the common result and evidence model. Do
  not add pack-specific fields, forms, presets, output constants, agent IDs,
  or Workflow-ID branches to the AAA UI, Task API, Worker bridge, or host task
  model. Pack-specific behavior stays inside the producing pack and is tested
  both as a golden use case and against an unrelated ordinary goal.
- Product runtime paths must stay under `~/.across`.
- The primary source mirror root is
  `~/.across/data/across-autopilot/source-mirrors`; legacy
  `~/.across/source-mirrors` compatibility must remain opt-in.
- Keep model credentials, raw approvals, and UI permission decisions with the
  host.
- Do not store raw secrets or full transcripts as long-term memory.
- Advanced autonomous product iteration must stop with human-review promotion
  evidence by default.

## Release Rules

Use `OPEN_SOURCE_RELEASE_HANDBOOK.md` for the full release process. The short
rule is producer-first:

1. Across Orchestrator
2. Across Context
3. Across Autopilot
4. Across Agents Assistant

Release tags must point to `origin/main` commits. Delete short-lived release
branches after merge.

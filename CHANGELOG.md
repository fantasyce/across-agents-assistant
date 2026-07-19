# Changelog

## 0.13.0 - 2026-07-20

### Added

- Added approved remote Worker enrollment and execution over direct IP links or
  an optional relay, with mutual TLS, expiring identity, revocation, resource
  leases, cancellation, bounded model grants, and hash-verified artifacts.
- Added one generic task entry with goal-driven Autopilot workflow resolution,
  including optional scenario simulation through the normal task contract.
- Added governed remote Worker experience memory that remains pending until
  human approval and can be revoked per device.

### Changed

- Unified Work and Run History so ordinary work and supervised workflow runs use
  the same task identity, review state, evidence package, and result actions.
- Simplified task result, Loop Engineering, Growth, agent capability, Settings,
  diagnostics, and plugin surfaces around progressive disclosure and compact
  actionable controls.
- Cached the Loop Engineering workspace snapshot and moved refresh to an
  explicit user action to reduce repeated loading and startup work.
- Updated managed producer pins to Autopilot `v0.5.0`, Orchestrator `v0.10.3`,
  and Context `v0.11.0` after their producer-first releases completed.
- Raised the OpenAI Python client minimum to `2.45.0` after compatibility
  validation, superseding the equivalent automated dependency PR.

### Fixed

- Fixed external task cancellation, generic quality scoring, nested Autopilot
  execution-plan reading, Worker presence projection, project switching, and
  actionable Loop check feedback.
- Hardened formal app rebuild shutdown so descendant backend processes do not
  survive and continue serving stale code.

## 0.12.1 - 2026-07-16

### Fixed

- Replaced the formatted review-count string used as an inspector field title
  with a dedicated localized total label, preventing `%d items` or `%d 项`
  from appearing literally in the interface.

## 0.12.0 - 2026-07-16

### Added

- Added microphone-only, append-safe voice input with multilingual punctuation,
  longer pause handling, and explicit recording state in the Work composer.
- Added beginner-safe guided workflows, deterministic no-key demonstrations,
  visual result cards, and gameful learning through ten missions, four levels,
  and twelve achievement badges.
- Added visible role, model, and budget policy; tamper-evident approval and
  evidence receipts; safe replay and attempt comparison; and risk-aware
  sandbox status across the desktop experience.
- Added governed memory provenance and trusted capability discovery for managed
  first-party plugins.

### Changed

- Reworked the public README around the current beginner-first product, fresh
  formal-app screenshots, one-click plugin installation, and the source-first
  open-source distribution model.
- Updated managed producer pins to Autopilot `v0.4.0`, Orchestrator `v0.9.0`,
  and Context `v0.10.0` after their producer-first releases completed.
- Unified page spacing, detail layouts, project switching, Settings surfaces,
  borderless navigation, window sizing, and double-click maximize behavior.

### Fixed

- Removed unintended blue focus borders while retaining the selected blue
  background, removed redundant separators and dense prompt shortcuts, and
  corrected approval/archive, plugin, achievement, and project-detail states.
- Restored resilient external sidecars and made unsupported read-only sandbox
  execution fail closed instead of claiming enforcement.

## 0.11.0 - 2026-07-13

### Added

- Added a capability-driven desktop home that remains useful without optional
  plugins and reveals shared memory, quality workflows, and Loop Engineering as
  their managed plugins become available.
- Added a visual Growth area with unlockable capabilities and achievements,
  including earned and locked states backed by real product activity.
- Added task-specific delivery review, accept-once completion, in-place
  revision, compact action tooltips, one-click memory approval, and clearer
  empty, unavailable, and error states.
- Added stronger agent interoperability evidence, workspace readiness checks,
  and end-to-end coverage for sandboxed delegation and Autopilot workbench
  health.

### Changed

- Rebuilt the macOS interface around a borderless, minimal project workspace
  with consistent navigation, page spacing, compact icon actions, and simpler
  Work, Memory, Workflows, Loop Engineering, Growth, Plugins, MCP, and Settings
  surfaces.
- Separated Plugin Center from MCP connections, removed duplicate settings
  pages, and kept advanced quality and runtime details behind focused actions.
- Replaced the old README screenshot matrix with current formal-app screenshots
  and updated the public product framing to match the plugin-host architecture.

### Fixed

- Hardened orchestration request planning, task persistence, public error
  sanitization, release verification, and Autopilot status handling across
  restart, completion, review, and compatibility-check paths.

## 0.10.0 - 2026-07-11

### Added

- Added isolated parallel agent workspaces with comparison, anchored line-level
  review, bounded revision, selection, cleanup, and approval-gated promotion.
- Added an approval-controlled GitHub quality-gate surface with exact feature
  branch push, resumable draft PRs, CI heartbeat/wall budgets, verification
  fallback, recovery evidence, and no credential entry or persistence.
- Added governed Context distillation, explicit pending review, five-route
  merged retrieval with provenance, approval, forgetting propagation, and rollback.
- Added agent account, auth, model, usage, and rate-limit status together with
  security-scoped repository access and the Operations Workbench UI redesign.

### Changed

- Updated managed producer pins to Autopilot `v0.3.0`, Orchestrator `v0.8.0`,
  and Context `v0.9.0`.
- Updated the supported backend dependency floors to Uvicorn `0.51.0`, FastAPI
  `0.139.0`, and Anthropic `0.116.0` after their dedicated CI gates passed.

## 0.9.55 - 2026-07-09

### Changed

- Updated the managed Across Orchestrator pin and default release-source mirror
  to `v0.7.13`, keeping AAA on the latest lockfile-aligned, CodeQL-clean
  Orchestrator patch release.

## 0.9.54 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default release-source mirror to
  `v0.2.30`, moving AAA self-iteration Codex policies to locally smoke-tested
  `gpt-5.5` and adding builder/reviewer timeout-recovery evidence for stalled
  local agent calls.

## 0.9.53 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default release-source mirror to
  `v0.2.29`, removing `codex-auto-review` from AAA self-iteration model
  candidates and giving research/review Codex calls a longer silent reasoning
  window after live E2E showed `gpt-5.3-codex-spark` could exceed a 300-second
  idle budget.

## 0.9.52 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default release-source mirror to
  `v0.2.28`, keeping AAA self-iteration research and review on
  `gpt-5.3-codex-spark` first while leaving `codex-auto-review` only as a
  fallback after live E2E showed review-model sessions could hang during
  research repair.

## 0.9.51 - 2026-07-08

### Changed

- Reused already-fresh release source mirrors when refreshing self-iteration
  source snapshots, so unchanged producer repos are not recloned during a
  partial release-pin change.
- Hardened source-mirror git command timeouts by terminating the full process
  group before reporting timeout failures.

## 0.9.50 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default release-source mirror to
  `v0.2.27`, so generated self-iteration validation commands are filtered
  before candidate execution and AAA runtime dependency smoke tests recognize
  standard-library imports on older system Python runtimes.

## 0.9.49 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default release-source mirror to
  `v0.2.26`, so host command wall-timeout windows refresh while stdout/stderr
  activity is still streaming.
- Hardened local Codex process supervision to treat active CLI output as
  progress for wall-timeout windows during long autonomous self-iteration runs.

## 0.9.48 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default release-source mirror to
  `v0.2.25`, adding duplicate marker repair collapse and implicit workbench /
  capability-pack entrypoint validation for self-iteration candidates.
- Hardened the Tool Pack registry code-iteration fallback so generated
  candidates expose a real pack-id contract, dynamic advice, and executable
  product-entrypoint smoke tests before independent review.

## 0.9.47 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default release-source mirror to
  `v0.2.24`, so self-iteration uses locally smoke-tested Codex models by role.
- Hardened local Codex timeout handling to terminate the full subprocess group
  when idle or max-wall timeouts fire.

## 0.9.46 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default release-source mirror to
  `v0.2.23`, adding hard source-discovery deadlines even when an underlying URL
  fetch or body stream ignores abort signals.

## 0.9.45 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default release-source mirror to
  `v0.2.22`, so autonomous URL source timeouts cover stalled response body
  reads as well as response headers during source discovery.

## 0.9.44 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default self-iteration
  release-source mirror to `v0.2.21`, which makes cancel requests terminate the
  recorded Autopilot executor process tree instead of only marking run state.

### Fixed

- Added per-model candidate progress evidence for autonomous research
  decisions so long Codex research attempts, fallback models, idle timeouts, and
  timeout kinds are visible in host CLI logs before code iteration starts.

## 0.9.43 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default self-iteration
  release-source mirror to `v0.2.20`, which propagates code-iteration timeout
  policy into the builder model request and gives complex local Codex builder
  runs a longer bounded idle window.

### Fixed

- Raised the default code-iteration local-agent idle window for long builder
  runs and added per-model candidate progress evidence so fallback attempts,
  idle timeouts, and wall-clock guardrails are visible in host CLI logs.

## 0.9.42 - 2026-07-08

### Fixed

- Replaced Autopilot research-decision timeout and invalid-model fallback
  reasons with fixed public reason codes so local exception strings cannot flow
  into API responses or CodeQL stack-trace exposure alerts.

## 0.9.41 - 2026-07-08

### Fixed

- Sanitized Autopilot research-decision public payloads and 422 details so
  traceback text, file paths, and internal exception content stay in local logs
  instead of API responses.

## 0.9.40 - 2026-07-08

### Changed

- Updated the managed Across Autopilot pin and default self-iteration
  release-source mirror to `v0.2.19`, which preserves long-running host command
  activity timeouts, max-wall guardrails, valid Codex model defaults, and
  deterministic platform self-repair trigger target selection.
- Added non-secret host CLI progress evidence for autonomous research, code,
  model, and review decisions so watchdog heartbeats can be distinguished from
  real local-agent stdout/stderr activity.

### Fixed

- Refreshed local Codex idle timeouts on real subprocess output during
  self-iteration instead of treating long-running model work as a silent outer
  timeout.
- Filtered unavailable Codex model candidates from self-iteration model policy
  and ignored stale configured Codex defaults that are not available locally.
- Skipped stale pending Autopilot triggers during scheduler dispatch so old
  platform self-repair work is not restarted automatically after an app rebuild.

## 0.9.39 - 2026-07-06

### Changed

- Updated the managed Across Autopilot pin and default self-iteration
  release-source mirror to `v0.2.18`, which preserves fallback model policy and
  routes host local-agent timeouts into platform self-repair.
- Documented `/Applications/Across Agents Assistant.app` as the canonical local
  packaged app target for development and release validation.

### Fixed

- Passed local Codex fallback model overrides into the universal local-agent
  client during autonomous code iteration.
- Returned structured HTTP 504/503 failures for local-agent code-iteration
  timeout and infrastructure errors so Autopilot can classify and repair the
  platform gap instead of losing the failure behind an outer timeout.

## 0.9.38 - 2026-07-06

### Changed

- Reduced automatic self-iteration candidate retention to the latest two
  candidate artifact sets by default.
- Stopped refreshing the legacy `~/.across/source-mirrors` root by default;
  self-iteration uses the primary Autopilot-managed source mirror under
  `~/.across/data/across-autopilot/source-mirrors`.

## 0.9.37 - 2026-07-05

### Changed

- Added automatic candidate artifact retention after self-iteration runs:
  candidate workspaces, candidate app artifacts, candidate runtime homes, and
  non-promotion-ready run records are pruned down to a small latest set by
  default.
- Candidate B app bundles are deleted after lifecycle validation unless the
  caller explicitly opts in to retaining the bundle or leaving the candidate
  app running.

## 0.9.36 - 2026-07-05

### Changed

- Moved candidate B app lifecycle bundles into Autopilot-managed candidate
  artifacts under `~/.across/data/across-autopilot/candidate-apps/<candidate_id>/`
  so autonomous self-iteration keeps one formal A app in `/Applications` while
  validating B apps in isolated runtime/artifact locations.

## 0.9.35 - 2026-07-05

### Changed

- Updated the managed Across Autopilot pin and default self-iteration
  release-source mirror to `v0.2.17`, which keeps OpenAI Agents SDK source
  intake on Node-fetchable official GitHub README sources.

## 0.9.34 - 2026-07-05

### Fixed

- Aligned the default self-iteration release-source mirror for Across Autopilot
  with the managed plugin pin at `v0.2.16`, so user machines without
  development checkouts bootstrap tomorrow's candidate workspace from the same
  released Autopilot build they execute.
- Added a regression test that keeps managed plugin install pins and default
  release-source mirror refs synchronized for producer repos.

## 0.9.33 - 2026-07-05

### Changed

- Updated the managed Across Autopilot pin to `v0.2.16`, which hardens
  autonomous self-iteration source intake with URL retries, longer source
  timeouts, fallback URLs, and raw Agent2Agent README content.

### Fixed

- Added structured local Codex timeout handling for autonomous research
  decisions so stalled strategy selection can fall back to bounded,
  product-integrated candidate targets instead of failing without reviewable
  output.
- Added research-decision child-process JSONL diagnostics so future timeouts
  preserve start/completion/failure events in local AAA logs and Autopilot
  stderr evidence.

## 0.9.32 - 2026-07-05

### Fixed

- Hardened public release-source bootstrap for user machines without local
  development checkouts by retrying failed clones and falling back to Git
  HTTP/1.1 when GitHub/proxy HTTP/2 framing errors occur.

## 0.9.31 - 2026-07-05

### Changed

- Updated the managed Across Autopilot pin to `v0.2.15`, finishing the Codex
  default migration for platform self-repair and older self-iteration LoopSpecs.
- AAA self-iteration source mirrors now bootstrap from public release tags when
  no explicit development source root is configured.

### Fixed

- Stopped default self-iteration status and refresh paths from implicitly
  probing `~/Documents/projects` development checkouts.
- Added timeouts around source-mirror Git probes and moved self-iteration plan
  source-mirror status checks off the API event loop.

## 0.9.30 - 2026-07-05

### Added

- Added autonomous self-iteration product integration surfaces for Autopilot tool
  manifests and A2A capability cards so the loop can expose reviewable host
  contracts without importing producer implementation code.

### Changed

- Updated the managed Across Autopilot pin to `v0.2.14`, which routes the
  autonomous self-iteration researcher, builder, and reviewer through local
  Codex and hardens candidate app lifecycle validation.
- Live E2E now discovers the managed `~/.across` Orchestrator runtime and no
  longer falls back to a sibling development checkout.

### Fixed

- Bundled the MCP CLI extra required by PyInstaller collection during candidate
  app lifecycle validation.
- Tightened candidate app socket path preflight and LLM status handling so
  valid candidates are not rejected by host validation plumbing.
- Strengthened self-iteration prompts against token-shaped fixtures in generated
  tests and examples.

## 0.9.29 - 2026-07-04

### Fixed

- Removed exception-object text from the public source-mirror status payload
  used by self-iteration plans, resolving the release CodeQL
  `py/stack-trace-exposure` alerts while preserving local backend diagnostics.

## 0.9.28 - 2026-07-04

### Added

- Added true local-time daily scheduling for AAA autonomous self-iteration so
  the default trigger runs at `10:00` in `Asia/Shanghai` instead of relying on a
  drifting interval anchor.
- Added backend startup restoration for an already configured self-iteration
  scheduler, keeping the daily trigger active across packaged-app restarts.

### Changed

- Self-iteration plan creation now records the default daily time and timezone
  alongside the existing interval fallback.

## 0.9.27 - 2026-07-03

### Added

- Added a host-side source mirror refresh gate for autonomous self-iteration.
  Candidate B workspaces now run only after AAA refreshes `~/.across` source
  mirrors from clean A checkouts and records a manifest with source heads.
- Added source mirror freshness status to the self-iteration plan so drifted or
  missing mirrors are visible before the next scheduled loop runs.

### Changed

- Queue dispatch and direct Autopilot runs now refresh source mirrors at run
  time for candidate-workspace LoopSpecs instead of relying on manually
  prepared mirrors from a previous release or test run.

## 0.9.26 - 2026-07-02

### Added

- Added a bounded AI-Ready Context synthesizer for Loop Engineering source
  signals and exposed it through the formal capability pack.

### Changed

- Updated the managed Across Autopilot pin to `v0.2.13`, which adds implicit
  AAA backend top-level name validation and explicit rejected-candidate
  completion evidence for autonomous self-iteration.

## 0.9.25 - 2026-07-02

### Changed

- Keeps Workbench trigger actions focused on actionable queued triggers instead
  of obsolete, failed, completed, or skipped queue history.
- Adds `historical_trigger_queue_count` and `terminal_trigger_queue_count`
  summary fields so old trigger evidence remains auditable without producing
  false "run queued trigger" actions.

## 0.9.24 - 2026-07-02

### Changed

- Keeps Loop Engineering ops health focused on unresolved current failures
  instead of stale recovered failures.
- Adds explicit `latest_failed`, `resolved_failed`, and `unresolved_failed`
  counters to the ops dashboard for audit clarity.
- Aligns Workbench and ecosystem telemetry with the same recovered-failure
  accounting.

## 0.9.23 - 2026-07-01

### Changed

- Enabled the self-iteration trigger scheduler to dispatch queued triggers by
  default and expose bounded dispatch controls for product-mode loop
  engineering.
- Hardened host code iteration so marker-upsert patches require explicit
  markers for code files, while documentation-only markerless upserts degrade
  to append.
- Expanded deterministic host repair fallbacks for loop-engineering capability
  targets, including target backlog, MCP/tool registry, capability classifier,
  tool pack registry, and platform self-repair replay fixtures.
- Updated the managed Across Autopilot pin to `v0.2.12`, which adds
  deterministic patch application, destructive entrypoint restore, richer
  validation diagnostics, and stricter platform-vs-candidate failure routing.

## 0.9.22 - 2026-07-01

### Changed

- Updated the managed Across Autopilot pin to `v0.2.11`, which tightens
  platform self-repair routing so ordinary candidate validation tracebacks do
  not get misclassified as host packaging gaps.

## 0.9.21 - 2026-07-01

### Changed

- Hardened candidate app lifecycle plugin installation so self-iteration
  validation installs Context and Autopilot only inside the candidate runtime
  home instead of inheriting the controller's global managed plugin paths.
- Updated the managed Across Autopilot pin to `v0.2.10`, which keeps runtime
  version reporting aligned with the package manifest.

## 0.9.20 - 2026-07-01

### Added

- Added supervised loop-engineering self-repair for AAA: platform-classified
  failures now enqueue `aaa-platform-self-repair`, run an isolated B candidate
  repair, validate replay evidence, and stop at human-review promotion.
- Added a real-provider self-repair E2E script that proves trigger routing,
  candidate repair, validation, self-hosting evidence, and promotion readiness.

### Changed

- Updated the managed Across Autopilot pin to `v0.2.9`.
- Hardened candidate app lifecycle and backend packaging checks so self-repair
  candidates validate packaged runtime dependencies without host Python leakage.

## 0.9.19 - 2026-06-30

### Changed

- Consolidated dependency hygiene updates for the backend runtime: FastAPI
  `>=0.138.2`, MCP `>=1.28.1`, OpenAI `>=2.44.0`, and Anthropic `>=0.113.0`.

## 0.9.18 - 2026-06-30

### Changed

- Updated the managed Across Orchestrator pin to `v0.7.10`, the follow-up
  CodeQL hygiene patch release. Autopilot remains `v0.2.8` and Context remains
  `v0.8.8`.

## 0.9.17 - 2026-06-30

### Changed

- Updated the managed Across Orchestrator pin to `v0.7.9`, the CodeQL and
  open-source hygiene patch release. Autopilot remains `v0.2.8` and Context
  remains `v0.8.8`.

## 0.9.16 - 2026-06-30

### Added

- Added the Workflows-first Simple Start surface in the macOS task panel:
  Repository Quality Copilot, Plugin Compatibility Lab, and Release Captain now
  create editable task drafts while the expert task form remains available.

### Changed

- Consolidated the public README release-history surface so detailed version
  notes live in this changelog while README stays focused on current product
  shape, producer pins, and workflow entrypoints.

## 0.9.15 - 2026-06-29

### Added

- Added the full frontier interop release gate for MCP Tasks projection, LF A2A
  v2 delegation, AG-UI task-card projection, Remote MCP/OAuth v1, OTel GenAI
  export, Skills bridge, optional Computer Use sandbox evidence, memory backend
  projections, and local agent protocol bridges.

### Changed

- Updated managed producer pins to Across Orchestrator `v0.7.8`, Across
  Context `v0.8.8`, and Across Autopilot `v0.2.8`.
- Switched Plugin Compatibility Lab public entrypoints to
  `plugin-compatibility-lab-v2`.

## 0.9.14 - 2026-06-29

### Changed

- Updated managed producer pins to Across Orchestrator `v0.7.7`, Across
  Context `v0.8.7`, and Across Autopilot `v0.2.7` after all three producer
  tags were verified against their current `origin/main` commits.

## 0.9.13 - 2026-06-29

### Changed

- Consolidated tracked Markdown entrypoints by removing stale root-level
  planning and validation reports, moving legal notices under `legal/`, and
  keeping agent-facing product context in `AGENTS.md`, `llms.txt`, and
  `across.product.json`.
- Updated the managed Across Autopilot pin to `v0.2.7`, which no longer depends
  on AAA's removed `LOOP_ENGINEERING_*` planning documents.

## 0.9.12 - 2026-06-29

### Changed

- Replaced the Codex, Hermes, OpenClaw, and local-agent icon rendering path with
  packaged WebP-first upstream assets plus SVG fallbacks, preserving auditable
  source metadata for open-source release review.
- Unified direct local-agent icon sizing and rounded-square clipping across the
  sidebar, model cards, and Agent Capabilities views so upstream image canvases
  no longer appear as oversized square tiles.

### Fixed

- Removed the stale `agent.cloudcode-desktop.svg` asset in favor of the
  official Claude Desktop naming surface.
- Loaded backend agent icon data URLs from packaged icon assets instead of
  handwritten placeholder SVG constants.

## 0.9.11 - 2026-06-28

### Added

- Added Kimi Code as a local CLI agent in AAA, including discovery,
  lightweight health detection, command dispatch through `kimi -p`, capability
  profiles, icons, and documentation.

## 0.9.10 - 2026-06-28

### Fixed

- Decoupled the release verification HTTP response from the in-memory report object by writing the detailed report locally first and then reading the latest local report into the fixed public DTO, closing the remaining CodeQL stack-trace exposure data flow on the default branch.

## 0.9.9 - 2026-06-28

### Fixed

- Replaced high-risk release verification and agent interop HTTP responses with fixed public DTOs that expose only status, counts, and bounded summaries while keeping detailed diagnostics in local reports/evidence, closing CodeQL stack-trace exposure alerts on the default branch.

## 0.9.8 - 2026-06-28

### Fixed

- Strengthened public API payload sanitization so traceback-shaped strings are redacted regardless of field name, and routed release verification responses through the shared public sanitizer to close CodeQL stack-trace exposure alerts.

## 0.9.7 - 2026-06-28

### Fixed

- Removed stack-trace logging from public API 500 handling so CodeQL stack-trace exposure alerts stay closed while HTTP responses continue to return only safe, non-secret error text.

## 0.9.6 - 2026-06-28

### Added

- Added Agent interop E2E evidence across Autopilot workflow packs, Context
  evidence memory, Orchestrator evidence graphs, sandbox policy checks, remote
  MCP/A2A metadata, and OTel/GenAI-style span export.
- Added workbench and release-center surfaces for interop status, plugin
  context-pack readiness, evidence coverage, and release-gate summaries.
- Added reusable pre-release gate evidence writers and a local gate runner that
  record commit, duration, runner, orchestrator command, and dirty-workspace
  state under `~/.across`.

### Changed

- Updated managed plugin pins to Across Orchestrator `v0.7.6`, Across Context
  `v0.8.6`, and Across Autopilot `v0.2.6`.
- Updated the GitHub Live E2E workflow to install Across Orchestrator
  `v0.7.6` from the main-derived release tag.
- Tightened RC verification so release evaluation readiness, required probe
  coverage, recent Release E2E evidence, and attached pre-release gate evidence
  must agree before a release can be considered ready.

### Fixed

- Preserved `workspace_dirty`, runner, and orchestrator command metadata when
  pre-release gate evidence is normalized and exposed through the packaged app.
- Kept packaged runtime release checks from treating unavailable source checkout
  paths as missing product gates.

## 0.9.5 - 2026-06-26

### Changed

- Updated managed plugin pins to Across Orchestrator `v0.7.5`, Across Context
  `v0.8.5`, and Across Autopilot `v0.2.5`.
- Updated the GitHub Live E2E workflow to install Across Orchestrator
  `v0.7.5` from the main-derived release tag.
- Revalidated the host/plugin release path with the packaged macOS app,
  host APIs, and all three managed plugins under `~/.across`.

### Fixed

- Removed stale Claude naming variants and duplicate host references from public
  README/CHANGELOG surfaces.
- Updated the route-evidence smoke matcher to use the official Claude Desktop
  name.

## 0.9.4 - 2026-06-25

### Added

- Added workflow-first product packaging for agents and model crawlers:
  `AGENTS.md`, `llms.txt`, `across.product.json`, and copyable agent task
  examples for Repository Quality Copilot, Release Captain, and Plugin
  Compatibility Lab.
- Added the open-source release handbook and Loop Engineering product packaging
  note for the four-repository Across ecosystem.

### Changed

- Updated managed plugin pins to Across Orchestrator `v0.7.4`, Across Context
  `v0.8.4`, and Across Autopilot `v0.2.4`.
- Updated the GitHub Live E2E workflow to install Across Orchestrator
  `v0.7.4` from the main-derived release tag.

## 0.9.3 - 2026-06-24

### Changed

- Updated managed plugin pins to Across Orchestrator `v0.7.3`, Across Context
  `v0.8.3`, and Across Autopilot `v0.2.3`.
- Updated the GitHub Live E2E workflow to install Across Orchestrator
  `v0.7.3` from the main-derived release tag.

### Fixed

- Includes the merged release verification hardening and CodeQL quality fixes
  that keep public release gate responses bounded and non-sensitive.
- Includes Dependabot updates for GitHub Actions, FastAPI, MCP, and pytest.

## 0.9.2 - 2026-06-24

### Added

- Added Claude Desktop as a local Agent integration, including backend
  discovery, Swift model/catalog support, runtime icon fallback, and task
  routing visibility.
- Added Agnes as a cloud provider with API key configuration, provider/model
  registry support, Swift settings integration, and an Across-owned
  compatibility icon tile.

### Changed

- Updated managed plugin pins to Across Orchestrator `v0.7.2`, Across Context
  `v0.8.2`, and Across Autopilot `v0.2.2`.
- Updated README guidance to describe Across Orchestrator, Across Context, and
  Across Autopilot as generic host plugins for Codex, Claude Code,
  Claude Desktop, AAA, and other CLI/MCP-capable hosts, not AAA-only
  implementation modules.

## 0.9.1 - 2026-06-24

### Added

- Added the Autopilot Workbench and generic external agent plugin gateway
  surfaces so AAA can validate host-neutral plugin contracts outside the
  original in-app task orchestration flow.
- Added backend and Swift coverage for the Autopilot Workbench, ecosystem
  roadmap reporting, and cross-process agent plugin runtime E2E paths.

### Changed

- Updated managed plugin pins to Across Orchestrator `v0.7.1`, Across Context
  `v0.8.1`, and Across Autopilot `v0.2.1`.
- Hardened managed plugin runtime boundaries so Codex, Claude Code,
  Claude Desktop, and AAA load wrappers through `~/.across/bin` instead of developer
  checkout paths.

### Fixed

- Preserved Orchestrator-owned loop recovery by letting Autopilot host-session
  supervision re-enter incomplete host sessions without human repair guidance.
- Extended release/open-source checks with path-boundary assertions for managed
  plugin install sources and runtime wrappers.

## 0.9.0 - 2026-06-23

### Added

- Added Across Autopilot as a managed Across ecosystem plugin and exposed the
  Loop Engineering control plane under `/api/autopilot/*`.
- Added the Plugin Center Loop Engineering Workbench for validating, previewing,
  running, and inspecting general LoopSpec workflows through Autopilot,
  Orchestrator, and Context.
- Added `scripts/run_loop_engineering_e2e.sh`, a user-level four-product E2E
  that starts the AAA backend and verifies a complete Autopilot -> Orchestrator
  -> Context workflow with evidence, events, telemetry, outputs, and pending
  memory.
- Strengthened the Loop Engineering platform contract with a durable Autopilot
  trigger queue, Tool Pack input/output schemas, evidence section hashes,
  audit-chain integrity metadata, and explicit planner/builder/validator/
  reviewer role evidence.
- Hardened installed-app Loop Engineering validation with a canonical AppKit
  fallback main window, `NSPrincipalClass` in the generated app bundle, and
  documented Computer Use attach evidence for packaged-app E2E.
- Hardened autonomous B repair by rejecting generated pytest-dependent candidate
  tests, requiring stdlib/runpy-compatible tests, and allowing bounded
  validation-repair fallbacks only for explicit safe helper targets.
- Added a non-secret Candidate Model Capability Lease for B runtimes, including
  candidate `/api/llm/status` lifecycle gates that require
  `candidate_model_lease` availability without copying or symlinking raw model
  credentials.
- Hardened dynamic `autopilot_*` B targets with package-import enforcement and a
  generic validation-repair fallback for model-selected module/test pairs.
- Updated managed plugin pins to Across Orchestrator `v0.7.0`, Across Context
  `v0.8.0`, and Across Autopilot `v0.2.0`.

## 0.8.29 - 2026-06-20

### Added

- Completed the Agent Loop host consumption surface with bounded loop telemetry,
  resume-aware event snapshots/streams, budget indicators, routing
  alternatives, and Across Context memory-candidate metrics in the Plugin
  Center.
- External Orchestrator loop transitions now best-effort enrich responses with
  telemetry alongside health and compact evidence summaries.
- Added a scheduled ecosystem review workflow and autonomous workflow
  guardrails for future research, triage, and release automation.
- Updated managed plugin pins to Across Orchestrator `v0.6.18` and Across
  Context `v0.7.8`.

## 0.8.28 - 2026-06-20

### Added

- RC verification reports now surface malformed pre-release gate evidence files
  as parse errors in JSON, Markdown, and Diagnostics UI.
- Added release process, architecture overview, and Agent Loop completeness
  documents to make the post-`v0.8.27` boundary explicit.

## 0.8.27 - 2026-06-20

### Added

- RC verification reports now include structured pre-release gate evidence for
  backend regression, open-source checks, Swift behavior/build gates, local Live
  E2E, GitHub Live E2E, and Quality CI; the Diagnostics UI renders the gate
  checklist and the Swift behavior runner now covers release-verification model
  decoding.
- Live E2E now writes non-secret gate evidence JSON, the manual GitHub workflow
  uploads that evidence as an artifact, and RC verification consumes gate
  evidence plus machine-readable missing required gate paths.
- Required manual pre-release gates now keep RC verification in attention until
  their evidence is attached, while failed required gate evidence blocks release
  approval.

## 0.8.26 - 2026-06-20

### Added

- Added a reusable `scripts/run_live_e2e.sh` runner and a manual GitHub
  `Live E2E` workflow that install/use Across Orchestrator `v0.6.17`, start a
  temporary AAA backend, and run both tiered live E2E and the legacy socket API
  E2E with the live gate enabled.
- Added `scripts/run_swift_behavior_checks.sh` and wired Quality CI to run
  standalone Swift behavior checks after the Swift build.

### Changed

- Agent Loop timeline source localization tests now consume enum-derived keys
  directly, keeping the App Preferences localization coverage tied to
  `AgentLoopTimelineSource`.
- Open-source checks now syntax-check every shell script under `scripts/`, not
  only the app build script.

## 0.8.25 - 2026-06-20

### Changed

- Documented that the Agent Loop SSE timeline endpoint defaults to a finite
  snapshot stream and requires `follow=true` for live polling.

### Fixed

- Kept Plugin Center timeline source labels covered by localization tests and
  narrowed the legacy live-events Boolean to a read-only compatibility mirror.
- Marked the legacy socket-backed API E2E as live-runtime gated and added a
  clearer skip/diagnostic path when no external Orchestrator runtime is
  configured locally.

## 0.8.24 - 2026-06-19

### Changed

- Plugin Center Agent Loop timelines now expose a Live/Snapshot mode control
  and distinguish live, snapshot, fallback, and unavailable timeline sources.
- External Orchestrator task acceptance records document that synthesized
  `created_at` can be `null` when upstream task timestamps are absent.

## 0.8.23 - 2026-06-19

### Changed

- Plugin Center loop health details now keep compact release readiness visible
  while folding lower-level Agent Loop evidence into an expandable details
  section.
- Updated managed Orchestrator defaults to Across Orchestrator `v0.6.17` for
  centralized Agent Loop cancel category policy.

### Fixed

- External Orchestrator task acceptance records now omit nondeterministic
  fallback timestamps and de-duplicate root-cause artifact ids when upstream
  task timestamps or artifact rows are incomplete.

## 0.8.22 - 2026-06-19

### Fixed

- External Orchestrator task details now synthesize a task-level acceptance
  record from external artifact and delivery-quality evidence so REST API and
  complex E2E views expose accepted delivery evidence consistently.

## 0.8.21 - 2026-06-19

### Added

- Plugin Center loop health details now consume Orchestrator
  `host_release_evidence`, showing release readiness, the first attention
  check, risk, and next action from compact Agent Loop evidence summaries.
- Task capability preflight now displays backend routing evidence so native
  skill and platform-skill matches are visible before task submission.

### Changed

- Updated managed Orchestrator defaults to Across Orchestrator `v0.6.16` for
  Agent Loop host release evidence support.

## 0.8.20 - 2026-06-19

### Added

- Agent Capabilities now diagnoses whether the non-secret Orchestrator host
  capability registry is synchronized with the local profile, plugins, tools,
  active native skills, and strict-scope state for the selected agent.

### Changed

- Updated backend dependency floors for `pytest-asyncio`, `numpy`, `uvicorn`,
  `anthropic`, and `openai` after local regression coverage and PR CI passed.

## 0.8.19 - 2026-06-19

### Added

- Plugin Center loop health details now surface structured memory candidate
  evidence from Orchestrator evidence summaries, including provider, status,
  and turn hints when available.
- Plugin Center shared-memory review now lists Agent Loop memory candidates
  from the latest evidence summary and can focus the review list on the
  candidate lifecycle status.
- Agent Capabilities now shows the non-secret Orchestrator host capability
  registry, including exported agent descriptors, routing signals, and
  redaction status.

## 0.8.18 - 2026-06-19

### Added

- Plugin Center loop health details now surface recovery policy decision
  evidence and recovered-step hints from Orchestrator evidence summaries, not
  only recovery counts.

### Changed

- External Across Orchestrator Agent Loop transition responses now include
  best-effort compact `health` and `evidence_summary` snapshots after run,
  approve, reject, cancel, and retry actions. External task evidence refreshes
  also apply to failed and cancelled terminal states, not only completed tasks.

### Validation

- AAA open-source release check passed.
- AAA backend regression passed.
- Swift package lock verification, Swift build, Swift tests, standalone Plugin
  Lifecycle/App Preferences behavior tests, and CI-compatible Swift build
  passed.

## 0.8.17 - 2026-06-19

### Fixed

- External Across Orchestrator task run responses now enrich completed tasks
  with the sidecar evidence bundle before mapping them into AAA task info. This
  keeps Release E2E quality, produced-file inventory, and delivery report status
  consistent immediately after `/api/tasks/{task_id}/run`, not only after a
  later status/detail refresh.

### Validation

- AAA open-source release check passed.
- AAA backend regression passed.
- Cross-repo HTTP E2E passed against Across Orchestrator `v0.6.15`: Agent Loop
  evidence summary, Release E2E run response quality, status refresh quality,
  and evidence benchmark all passed.

## 0.8.16 - 2026-06-19

### Added

- Added optional Agent Loop evidence summary consumption for Plugin Center
  probes. The backend proxies Orchestrator evidence summaries, and the macOS
  health popover can show event audit coverage, routing, recovery, and memory
  candidate counts when the sidecar supports the new read-only protocol.

### Changed

- Updated managed Orchestrator defaults to Across Orchestrator `v0.6.15` while
  keeping managed Across Context defaults at `v0.7.7`.

### Validation

- AAA open-source release check passed.
- AAA backend regression passed.
- Swift package lock verification, Swift build, Swift tests, standalone Plugin
  Lifecycle/App Preferences behavior tests, and packaged app build checks
  passed.
- Across Orchestrator `v0.6.15` release checks passed before updating the AAA
  managed pin.

## 0.8.15 - 2026-06-19

### Added

- Added true live Agent Loop timeline streaming for Plugin Center probes. The
  AAA backend now emits incremental sanitized SSE events, and the macOS
  timeline updates while the probe is running instead of labeling a completed
  SSE snapshot as live.

### Changed

- Updated managed Orchestrator defaults to Across Orchestrator `v0.6.14` while
  keeping managed Across Context defaults at `v0.7.7`.

### Validation

- AAA open-source release check passed.
- AAA backend regression passed.
- Swift package lock verification, Swift build, Swift tests, standalone Plugin
  Lifecycle/App Preferences behavior tests, and packaged app build checks
  passed.
- Across Orchestrator `v0.6.14` release checks passed before updating the AAA
  managed pin.

## 0.8.14 - 2026-06-19

### Added

- Added Plugin Center Agent Loop health detail popovers for stale leases,
  cancellation state, and recent failure counts.
- Added Agent Loop timeline sequence chips with hover audit identifiers from
  Across Orchestrator `v0.6.13`.
- Added structured cancellation-category display while keeping unknown future
  categories readable as plain strings.

### Changed

- Updated managed Orchestrator defaults to Across Orchestrator `v0.6.13` while
  keeping managed Across Context defaults at `v0.7.7`.

### Validation

- AAA open-source release check passed.
- AAA backend regression passed.
- Swift package lock verification, Swift build, Swift tests, and standalone
  Plugin Lifecycle/App Preferences behavior tests passed.
- Across Orchestrator `v0.6.13` release checks passed before updating the AAA
  managed pin.

## 0.8.13 - 2026-06-19

### Added

- Added a non-secret host agent capability registry at
  `/api/host/agent-capabilities` for Orchestrator capability-hint routing.
- Added macOS Plugin Center Agent Loop event timeline rendering after
  Orchestrator probes.

### Changed

- Updated managed Orchestrator defaults to Across Orchestrator `v0.6.12` and
  managed Across Context defaults to `v0.7.7`.
- Kept external Orchestrator HTTP error status mapping precise while reducing
  duplicate warning noise on already-typed upstream HTTP errors.
- Allowed external Orchestrator-owned pause, resume, and cancel task lifecycle
  calls to report `409` when a sidecar rejects duplicate terminal actions.

### Validation

- AAA open-source release check passed.
- AAA backend regression passed with 675 tests and 1 warning.
- Swift package lock verification, Swift build, and Swift tests passed.
- Across Orchestrator checks passed with 119 tests.
- Across Context checks passed with 63 tests.
- GitHub PR checks passed for the AAA, Orchestrator, and Context release inputs.

## 0.8.12 - 2026-06-19

### Added

- Proxied Across Orchestrator Agent Loop health through
  `/api/orchestrator/loops/{loop_id}/health`.
- Added macOS Plugin Center loop health decoding and probe chips for current
  action, pending approval, and execution lease state.

### Changed

- Updated managed Orchestrator defaults to Across Orchestrator `v0.6.11` while
  keeping Across Context pinned to `v0.7.6`.
- Made Plugin Center health fetching best-effort so a successful loop probe is
  not marked failed when the optional health snapshot is unavailable.
- Normalized external Orchestrator HTTP GET error wrapping to match POST
  behavior.

### Validation

- AAA open-source release check passed.
- AAA backend regression passed with 672 tests and 1 warning.
- Swift package lock verification and Swift build passed.
- Across Orchestrator checks passed with 124 tests and 2 subtests.
- Across Context checks passed with 63 tests.
- Complex Agent Loop health E2E passed through a real Orchestrator HTTP sidecar.

## 0.8.11 - 2026-06-19

### Changed

- Removed the remaining host-side `task_manager` and `legacy_task_history`
  compatibility packages; host task history now lives under
  `across_agents_assistant.task_history`.
- Removed stale compatibility aliases for local-agent exports, task persistence
  subtask loading, release verification monkeypatch signatures, and the
  shadowed `/api/tasks/resumable` route.
- Updated managed Orchestrator defaults to Across Orchestrator `v0.6.10` while
  keeping Across Context pinned to `v0.7.6`.

### Fixed

- Released with Across Orchestrator `v0.6.10`, which keeps terminal external
  tasks idempotent after cancellation or approval rejection and normalizes older
  `stopped` task rows to `failed` without duplicate task events.

### Validation

- AAA open-source release check passed.
- AAA backend regression passed with 671 tests and 1 warning.
- AAA focused boundary regression passed with 90 tests and 1 warning.
- Swift package lock verification and Swift build passed.
- Across Orchestrator checks passed with 122 tests and 2 subtests.
- Across Context checks passed with 63 tests.

## 0.8.10 - 2026-06-17

### Fixed

- Removed an unused legacy shutdown helper that cancelled running tasks during
  old shutdown flows; current shutdown uses task suspension through
  `_suspend_running_tasks_for_shutdown()`.

### Changed

- Updated managed Orchestrator defaults to Across Orchestrator `v0.6.9` while
  keeping Across Context pinned to `v0.7.6`.

### Validation

- AAA backend tests passed with 694 tests and 20 skipped.
- SwiftPM Swift Testing passed with 28 tests.
- AAA open-source release check passed.

## 0.8.9 - 2026-06-17

### Fixed

- Released with Across Orchestrator `v0.6.8`, which synchronizes task terminal
  status with Agent Loop terminal states so cancelled, rejected, and max-turns
  stopped loops no longer leave host-visible tasks in `running`.
- Kept `stopped` as an Orchestrator loop detail while mapping host task status
  to AAA-supported terminal states (`failed` or `cancelled`).

### Changed

- Updated managed plugin defaults to Across Orchestrator `v0.6.8` and Across
  Context `v0.7.6`.

### Validation

- AAA backend tests passed with 694 tests and 20 skipped.
- SwiftPM Swift Testing passed with 28 tests.
- Across Orchestrator checks passed with 104 tests.
- Across Context checks passed with 63 tests.
- AAA open-source release check passed.

## 0.8.8 - 2026-06-16

### Changed

- Removed the legacy in-app task orchestration runtime from production task API
  initialization and startup diagnostics; the Swift restore flow now uses the
  current task API boundary.
- Updated managed plugin defaults to Across Orchestrator `v0.6.7` and Across
  Context `v0.7.5`.
- Integrated the generic, declarative Across Orchestrator agent adapter
  contract while preserving AAA host compatibility.
- Strengthened Agent Loop checkpointing, host action-plan handoff, repeated
  action handling, and dispatch-to-quality ordering.

### Validation

- AAA backend tests passed with 975 tests and 18 skipped.
- SwiftPM Swift Testing passed with 28 tests.
- Across Orchestrator tests passed with 89 tests.
- Across Context checks passed with 63 tests.
- Packaged UI task-orchestration E2E passed through Computer Use on a temporary
  packaged app with task `task-c39eff9ae5`, loop `loop-f8fa09a60a`, two serial
  waves, two generated artifacts, five loop checkpoints, and the
  `serial_wave_dependencies` quality gate.

## 0.8.7 - 2026-06-15

### Changed

- Updated managed plugin defaults to Across Orchestrator `v0.6.6` and Across
  Context `v0.7.4`.
- Hardened packaged runtime boundaries so managed plugin installs stay under
  `~/.across` and development checkout paths are rejected from packaged
  product execution.
- Preserved external orchestration artifact metadata through task persistence
  and API surfaces.

### Validation

- AAA backend tests passed with 972 tests and 18 skipped.
- AAA open-source release check passed.
- SwiftPM Swift Testing passed with 28 tests.
- Packaged macOS app build passed for version `0.8.7`; codesign verification
  passed, and `/Applications/Across Agents Assistant.app` reported version
  `0.8.7`.
- Packaged app startup diagnostics passed with 11 checks, 0 warnings, and 0
  failures.
- Packaged UI complex E2E passed through Computer Use with AAA `0.8.7`,
  Across Orchestrator `0.6.6`, and Across Context `0.7.4`: task
  `task-c4f629165e`, loop `loop-0a85291955`, seven serial dependency waves,
  seven generated artifacts, quality score 100, required failed count 0, and a
  pending Across Context memory candidate `mem_84d220c9949e4bcca1`.
- The generated E2E project passed `node cli/quality-check.mjs` and
  `node tests/e2e-smoke.mjs`.

## 0.8.6 - 2026-06-14

### Changed

- Moved release verification, external Orchestrator protocol mapping,
  Orchestrator release-evidence handling, task API schemas, and task
  observability helpers out of the FastAPI route module into dedicated backend
  boundaries.
- Split Swift task orchestration models into Core, Events, Execution, and
  Quality model files.
- Added CI validation that `Package.resolved` stays aligned with
  `Package.swift`.

### Fixed

- Replaced the Pydantic V1-style `KeysRequest.Config` with `ConfigDict`.
- Constrained the backend package to Python `>=3.10,<3.14` and added a local
  `.python-version` baseline of `3.11`.
- Prevented managed Across Orchestrator installs from selecting unsupported
  Python 3.14 runtimes.

### Validation

- Open-source release check passed.
- AAA backend tests passed on Python 3.11 with 894 tests and one third-party
  Starlette/httpx deprecation warning.
- Complex orchestration E2E checks passed with 24 tests and 4 environment
  skips.
- SwiftPM Swift Testing passed with 18 tests.
- Swift package lock consistency check passed.

## 0.8.5 - 2026-06-14

### Changed

- Split external task deliverable, owner-agent, and strict-dependency planning
  out of the FastAPI route module into a dedicated backend planning boundary.
- Moved Swift task orchestration DTOs out of
  `TaskOrchestrationViewModel` into model-layer types while keeping nested
  typealiases for source compatibility.
- Moved Swift task progress, polling merge, terminal-state, and detail-polling
  decisions into testable state reducers.
- Moved Across Orchestrator strict-dependency repair out of `runtime.py` into
  the planning boundary.
- Updated the managed Across Orchestrator install pin to `v0.6.5`.

### Validation

- AAA backend tests passed with 928 tests and 18 skipped.
- SwiftPM Swift Testing passed with 18 tests.
- Across Orchestrator full check passed with 59 tests, CLI smoke, and
  sensitive text scan.
- Across Context full check passed with 55 tests, CLI smoke, and sensitive text
  scan.
- Packaged app startup diagnostics passed with 11 checks on version `0.8.5`,
  loading Across Orchestrator `0.6.5` from the managed `~/.across` wheel.
- Packaged Release E2E completed through the external Orchestrator runtime with
  seven serial waves, seven artifacts, all required probes passing, and quality
  score 100.

## 0.8.4 - 2026-06-14

### Fixed

- Preserved external task boundary metadata across Swift task-detail state
  updates, polling, and SSE events so packaged tasks keep their lifecycle
  controls, delivery mode, task types, owner contract, and observability.
- Reused existing dispatched jobs during orphan recovery instead of creating
  duplicate dispatch records for the same orphaned subtask.
- Preserved strict dependency plans when AAA submits explicit external subtasks
  to Across Orchestrator through the managed runtime.

### Changed

- Updated the managed Across Orchestrator install pin to `v0.6.4`.

### Validation

- AAA backend tests passed with 924 tests and 18 skipped.
- SwiftPM Swift Testing passed with 15 tests.
- Across Orchestrator full check passed with 58 tests, CLI smoke, and
  sensitive text scan.
- Across Context full check passed with 55 tests, CLI smoke, and sensitive text
  scan.
- Packaged app startup diagnostics passed with 11 checks, and packaged Release
  E2E produced seven serial dependent tasks, seven artifacts, and quality score
  100.

## 0.8.3 - 2026-06-14

### Fixed

- Hardened managed Across Orchestrator repair so stale runtime artifacts,
  editable installs, and host-source trees are removed before reinstall.
- Marked stale Across Orchestrator source trees, `.pth` files, and
  `direct_url.json` metadata that point at protected development checkouts as
  plugin integrity failures.
- Rejected protected-path Across Orchestrator command overrides by default,
  unless development command overrides are explicitly enabled.
- Updated the managed Across Context and Across Orchestrator install pins to
  `v0.7.3` and `v0.6.3`.
- Aligned the Swift availability test with the current English Model Settings
  readiness message.

### Changed

- Documented the three-product boundary between Across Agents Assistant,
  Across Context, and Across Orchestrator.
- Documented managed plugin runtime paths under `~/.across` and the rule that
  packaged product paths must not execute plugin runtimes from development
  checkouts.

### Validation

- AAA backend plugin-boundary, API, and version consistency tests passed with
  63 tests.
- Across Context check passed with 55 tests plus CLI and MCP smoke.
- Across Orchestrator full check passed with 56 tests, CLI smoke, and
  sensitive text scan.
- SwiftPM Swift Testing passed with 12 tests.
- Packaged app smoke verified stale Orchestrator source trees report repair
  required and clean managed runtimes report installed with passing integrity.
- Open-source release check passed.

## 0.8.2 - 2026-06-13

### Documentation

- Clarified the three-product boundary between Across Agents Assistant,
  Across Context, and Across Orchestrator.
- Documented managed plugin runtime paths under `~/.across` and the rule that
  packaged product paths must not execute plugin runtimes from development
  checkouts.

### Fixed

- Removed the built-in Across Context compatibility runtime so shared memory is
  resolved only through the external plugin boundary.
- Startup diagnostics now preserve the installed plugin source reported from
  managed runtime metadata without leaking protected development checkout paths.
- The task submission project-directory field now synchronizes accessibility
  value writes with the SwiftUI binding, so packaged UI automation can submit
  tasks through the same form path as users.

### Changed

- Managed plugin install sources are pinned to Across Context `v0.7.2` and
  Across Orchestrator `v0.6.2` for reproducible source-first releases.

## 0.8.1 - 2026-06-13

### Fixed

- Managed Across plugin installs now reject stale wrappers, editable installs,
  and Python metadata that point back to protected user directories such as
  Documents, Desktop, or Downloads.
- Across Orchestrator repair now recreates the managed virtualenv before
  reinstalling, so AAA does not keep launching an old plugin runtime.
- Across Context repair and upgrade now force a fresh managed install instead
  of returning an already-installed older wrapper.
- Managed Across Context installs use an app-owned npm cache under
  `~/.across/cache/across-agents-assistant/npm` and bounded install timeouts, so
  broken user-level npm caches or network failures do not leave Plugin Center
  waiting indefinitely.
- Built-in local knowledge, SQLite, and filesystem MCP defaults now use
  managed directories under `~/.across/data/across-agents-assistant`.
- Saved MCP settings that still point at old Across hidden directories or the
  previous Documents defaults are reset to managed `~/.across` paths.

### Changed

- Removed automatic read/copy migration from legacy `~/.across_agents` and
  legacy Across Context vaults. Fresh installs and managed plugins use only the
  unified `~/.across` ecosystem root unless an explicit override is provided.

## 0.8.0 - 2026-06-12

### Added

- Agent Loop v2 host integration for the external Across Orchestrator plugin,
  including approval-action proxying and Plugin Center capability decoding.
- Sidecar environment wiring that explicitly enables Across Context as the
  Orchestrator memory provider when the plugin is launched by AAA.
- Plugin Center memory review now asks Across Context for all-project pending
  memories, so project-scoped Agent Loop summaries are visible for approval.
- Managed install sources now route through the Across plugin repositories so
  one-click repair does not pin stale plugin runtimes.

### Changed

- AAA remains a thin host: Agent Loop planning, dynamic remediation dispatch,
  checkpoints, and memory hooks stay in Across Orchestrator.

## 0.7.1 - 2026-06-12

### Changed

- Refined the main toolbar icon sizing so built-in controls, capability entry,
  MCP entry, and Plugin Center entry use one shared glyph/button metric.
- Reworked the Plugin Center icon as an Across-owned hollow puzzle-piece SVG
  with the bottom-left jigsaw shape and a larger effective drawing area.
- Updated managed install sources to Across Context `v0.6.1` and Across
  Orchestrator `v0.5.1`.

### Validation

- Open-source release check passed.
- Backend regression passed with `857 passed`.
- Swift package build passed.

## 0.7.0 - 2026-06-11

### Added

- Agent Loop Runtime integration for the external Across Orchestrator plugin,
  including loop start, run, status, events, and Plugin Center probe support.
- Plugin Center capability badges for Agent Loop, checkpoint, and memory-hook
  support.
- Managed install source alignment for Across Context `v0.6.0` and Across
  Orchestrator `v0.5.0`.

### Changed

- Task orchestration remains external-plugin only, but hosts can now use the
  loop protocol directly instead of relying only on task-level lifecycle APIs.
- Shared-memory governance is exposed as an external Across Context loop-memory
  policy surface instead of app-owned vault inspection.

## 0.6.0 - 2026-06-10

### Added

- Plugin Center UI for Across plugin discovery, install, repair, uninstall,
  status probing, compatibility metadata, and shared-memory review.
- Shared memory governance endpoints that call the external Across Context
  plugin CLI instead of directly owning the plugin's vault implementation.
- Generic plugin lifecycle action API for `across-context` and
  `across-orchestrator`.

### Changed

- Managed Across Context install source now targets `v0.5.0`.
- Managed Across Orchestrator install source now targets `v0.4.0`.
- The AAA host remains a thin console: task orchestration and shared memory are
  unavailable when their external plugins are not installed.

## 0.5.1 - 2026-06-09

### Fixed

- Preserve successful tool results when the automatic post-approval continuation
  hits a gateway fallback, so shared-memory reads and writes are not hidden by a
  downstream model-routing error.
- Point the managed Across Orchestrator install source at `v0.3.1`.

## 0.5.0 - 2026-06-09

This release turns Across Agents Assistant into a thinner Across ecosystem host.
AAA, Across Context, and Across Orchestrator now share one `~/.across` root while
keeping plugin runtime code, durable data, logs, run metadata, and cache files
in separate component namespaces.

### Added

- Unified Across ecosystem paths:
  `~/.across/data/across-agents-assistant`,
  `~/.across/data/across-context`, and
  `~/.across/data/across-orchestrator`.
- Plugin wrapper discovery through `~/.across/bin`.
- Sidecar-first Across Orchestrator launch from the AAA host when no explicit
  endpoint is configured.
- Fresh installs and managed plugins use only the unified `~/.across`
  ecosystem root.

### Changed

- Across Context external MCP mode now uses `~/.across/data/across-context` as
  the shared-memory vault.
- The Across Orchestrator managed install now writes runtime code under
  `~/.across/plugins/across-orchestrator` and wrapper commands under
  `~/.across/bin`.
- App logs and sockets moved to
  `~/.across/logs/across-agents-assistant` and
  `~/.across/run/across-agents-assistant`.
- The managed Orchestrator install source now targets
  `fantasyce/across-orchestrator@v0.3.1`.

### Validation

- AAA backend regression: `870 passed, 18 skipped`.
- Swift behavior checks passed for app preferences and MCP plugin defaults.
- AAA open-source check passed.
- Packaged AAA Release E2E submitted through the external Across Orchestrator
  sidecar and passed with quality score `100`.
- Across Context external MCP write/search smoke passed through AAA's MCP tool
  path and was verified in the external vault.
- Across Orchestrator plugin repo check: `414 passed`.
- Across Context plugin repo check: `46 passed`.

## 0.4.3 - 2026-06-07

This is a source-first patch release for the Across Orchestrator plugin slot.
Across Agents Assistant now treats task orchestration as an external plugin
runtime instead of an app-owned fallback path for new task submission.

### Added

- Across Orchestrator runtime status API and startup diagnostic coverage.
- One-click managed plugin install endpoint for `across-orchestrator`.
- External HTTP/CLI task lifecycle support for Release E2E creation, run,
  status, quality benchmark, evidence bundle, and task-list surfaces.
- UI support for unavailable/installing/installed plugin states in the task
  orchestration view.

### Changed

- New task orchestration submissions now require the external Across
  Orchestrator plugin; `builtin` and `auto` mode values normalize to the
  external plugin boundary.
- Packaged app plugin install resolves a real Python interpreter instead of
  accidentally invoking the packaged backend binary as `python -m venv`.
- The app-managed Across Orchestrator CLI takes precedence over PATH lookup
  after installation.
- README release notes now document the plugin slot, install source, task index
  location, and external evidence gates.

### Validation

- App open-source guard: `bash scripts/open_source_check.sh`.
- Focused backend regression for Across Orchestrator plugin/API/release/startup
  paths.
- Across Orchestrator plugin repo check: `bash scripts/check.sh`.
- UI-level Release E2E completed through the packaged app using the external
  Across Orchestrator CLI with 7/7 required files and app-grade quality score
  100.

## 0.4.2 - 2026-06-07

This is a source-first patch release for plugin-first shared memory. Across
Context remains an independent local memory product; Across Agents Assistant now
hosts it through the external MCP plugin when available, with a bundled
compatibility bridge only for first-run fallback.

### Added

- Built-in Across Context shared-memory support is now available from the main
  app surface without requiring the MCP settings view to be opened first.
- Packaged-app Across Context integration can use a native Python compatibility
  bridge for the local Across Context JSONL vault, avoiding a packaged-backend
  stdio hang when launching the external Node MCP server.
- Across Context now uses a plugin-first host architecture: the app prefers the
  external `across-context mcp` server, falls back to the built-in compatibility
  bridge only in auto mode, and reports the active implementation in API/UI.
- E2E coverage now verifies that one agent can write project memory and another
  agent can retrieve the same memory through Across Context tools.

### Changed

- Across Context is enabled by default for built-in MCP plugin state, including
  older saved preferences that previously persisted it as disabled.
- Tool approval and chat continuation paths now preserve project context so
  project-scoped MCP tools receive the correct project root.
- MCP connection errors no longer disable built-in plugins automatically, so a
  transient startup issue does not hide shared-memory tools from the catalog.
- Later ecosystem releases moved the canonical shared-memory vault under the
  unified `~/.across` root.

### Validation

- Backend regression: `849 passed, 18 skipped`.
- Swift release build passed for the macOS client.
- Focused MCP plugin behavior check passed.
- Packaged app build and `codesign --verify --deep --strict` passed.
- UI-level E2E verified project memory shared from DeepSeek to MiniMax through
  Across Context approval prompts.
- Packaged-app `/api/approve` executed `across_context__remember_context`
  through the external `across-context mcp` integration; the standalone
  `across-context search` CLI found the same pending project memory.
- Plugin-mode regression verifies external-first, fallback, and forced-external
  failure behavior for Across Context.
- `bash scripts/open_source_check.sh`.

## 0.4.1 - 2026-06-07

This is a source-first patch release for the local-agent and cloud-provider
catalog. It remains intended for local building and inspection; public binary
distribution still requires Developer ID signing, hardened runtime, and
notarization outside this repository.

### Added

- Official/library tile icons for the expanded cloud LLM catalog, including
  OpenAI, Anthropic, Gemini, xAI, Mistral, Groq, Cohere, OpenRouter, Together
  AI, Fireworks AI, and existing Chinese provider entries.
- Agent icon provenance manifest, workflow documentation, preview artwork, and
  third-party notice updates for the bundled icon set.
- Runtime Codex app-icon support: installed OpenAI-signed `Codex.app` icons are
  read from the user's machine when present, with the bundled OpenAI tile as
  the fallback.

### Changed

- OpenCode now uses the LobeHub Icons `opencode.svg` source inside the
  project-owned dark/light tile, avoiding release reliance on a Marketplace
  image with unclear redistribution terms.
- Cursor keeps the clean bundled tile first and only falls back to the local
  app icon if no bundled asset is available, avoiding macOS icon halos in the
  compact sidebar.
- Unsupported local IDE integrations were removed from the local-agent catalog
  until their CLI availability and setup flow can be supported reliably.
- The open-source guard script now fails if bundled icon metadata still carries
  a `review-before-release` redistribution status.
- README product-tour screenshots and the agent icon preview were refreshed
  from the `0.4.1` app surface with public-safe demo labels.

### Validation

- Focused backend regression for local-agent health, provider registry, icon
  policy, and version consistency.
- `bash scripts/open_source_check.sh`.
- `swift build --package-path macOS-Client --skip-update`.
- `./build_app.sh`.
- `codesign --verify --deep --strict --verbose=2 "build/Across Agents Assistant.app"`.

## 0.4.0 - 2026-05-31

This is a source-first release for local building and inspection. The packaged
app bundle produced by `build_app.sh` is suitable for local validation; public
binary distribution still requires Developer ID signing, hardened runtime, and
notarization outside this repository.

### Added

- Release Evidence Center for reviewing release readiness, probe coverage,
  recent task evidence, task evidence bundles, and local JSON exports.
- Startup Diagnostics in Settings for backend health, provider readiness,
  app-owned paths, socket, database, task persistence, and evidence directory
  checks.
- RC Verification in Settings -> Diagnostics and `/api/release/verification`.
  The verifier combines startup diagnostics, the latest fixed Release E2E
  benchmark, release-evaluation context, and local JSON/Markdown report files.
- Read-only task Evidence Bundle API with credential-shaped value redaction,
  delivery contract, requirement manifest, quality health, artifacts,
  acceptance records, and benchmark output.
- Non-secret Agent Cards export for local capability and routing audit.
- Fixed complex Release E2E scenario covering exact seven-file Web/API/CLI
  delivery, static web checks, API probes, CLI checks, browser E2E, workspace
  hygiene, security/privacy, remediation budget, and cross-agent coverage.

### Improved

- Release Evaluation now includes readiness checks, recent score trend,
  required probe coverage, local/cloud agent-mix coverage, benchmark status,
  and per-task audit traces.
- Delivery quality benchmarks and evidence bundles can evaluate persisted task
  records without restoring or resuming old tasks.
- Startup and main-window behavior avoid duplicate main windows and use a
  faster unpacked backend bundle layout by default.
- Release E2E remediation now reports actual remediation subtask count and
  provides targeted patch plans for route-evidence failures.

### Validation

- Backend regression excluding slow E2E tests.
- Focused Swift behavior tests for diagnostics, release verification,
  preferences, settings state, and release evidence.
- `swift build --package-path macOS-Client --skip-update`.
- `bash build_app.sh`.
- `codesign --verify --deep --strict --verbose=2 "build/Across Agents Assistant.app"`.
- `bash scripts/open_source_check.sh`.
- Packaged-app RC Verification report with `status=ready`.

### Known Limits

- The repository does not include Developer ID credentials, notarization
  profiles, private maintainer notes, local databases, logs, or generated
  runtime data.
- The local app bundle is ad-hoc signed unless `SIGNING_IDENTITY` is provided.

## 0.3.1 - 2026-05-31

### Added

- Release-evaluation audit workflow with readiness signals exposed in the task
  orchestration surface.
- Task Evidence Bundle API for read-only review of delivery contracts,
  requirement manifests, owner decisions, quality health, artifacts, acceptance
  records, and benchmark results.
- Non-secret Agent Cards export for capability, native-skill health, tool-risk,
  MCP scope, strict-scope, and repair-hint review.
- Public open-source guard script and GitHub Actions Quality workflow for
  release hygiene.

### Improved

- Delivery quality benchmarks can use persisted task evidence, not only live
  in-memory task state.
- Release-evaluation output includes benchmark status, probe coverage, agent
  mix, and per-task audit traces.
- Task details surface richer execution evidence, quality gates, remediation
  history, and final quality metrics.

## 0.3.0 - 2026-05-31

### Added

- Release Evaluation summary for comparing recent quality-gated tasks.
- Fixed high-complexity Release E2E scenario for cross-agent Web/API/CLI
  delivery, route evidence, quality gates, browser checks, remediation trace,
  MCP safety audit, and native skill routing evidence.
- Stronger delivery quality gates for exact file contracts, workspace hygiene,
  runnable probes, API service checks, CLI checks, static web behavior, browser
  evidence, and local/cloud agent-mix coverage.
- Capability preflight and routing signals that account for native local-agent
  skills and MCP safety information.

### Improved

- Owner-led orchestration can produce targeted remediation work when required
  deliverables or quality probes fail.
- Native skill readiness keeps unavailable skills visible with repair context
  while preventing them from being used as strong routing evidence.
- Main-window behavior and packaged startup paths were hardened for release
  validation.

## 0.2.0 - 2026-05-29

### Added

- Delivery Quality Benchmark API for completed complex tasks.
- Exact deliverable contract checks, requirement-manifest validation, and
  quality score reporting.
- Static web and browser-oriented acceptance probes for UI tasks.
- Benchmark support for expected files, required probes, minimum quality score,
  remediation state, skipped checks, and workspace hygiene.

### Improved

- Owner review and final task state now retain delivery-quality evidence for
  later inspection.
- Build metadata and backend version reporting were aligned for source-first
  release validation.

# Changelog

## Unreleased

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

<h1 align="center">Across Agents Assistant</h1>

<p align="center">
  <img src="assets/readme/app-icon.png" alt="Across Agents Assistant app icon" width="120" height="120">
</p>

<p align="center">
  <strong>A local-first macOS workspace for cross-agent collaboration.</strong>
</p>

<p align="center">
  <a href="https://github.com/fantasyce/across-agents-assistant/actions/workflows/quality.yml"><img src="https://github.com/fantasyce/across-agents-assistant/actions/workflows/quality.yml/badge.svg" alt="Quality workflow status"></a>
  <a href="https://github.com/fantasyce/across-agents-assistant/actions/workflows/security.yml"><img src="https://github.com/fantasyce/across-agents-assistant/actions/workflows/security.yml/badge.svg" alt="Security workflow status"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
</p>

<p align="center">
  Coordinate local coding agents and cloud LLMs from one native desktop app, keep work tied to a project tree, approve tools explicitly, and review complex task delivery before it leaves your machine.
</p>

<p align="center">
  <img src="assets/readme/zh-dark-main-chat.png" alt="Across Agents Assistant dark main chat with project tree, local agents, and cloud LLMs">
</p>

<p align="center">
  <img src="assets/readme/zh-dark-task-orchestration.png" alt="Across Agents Assistant dark task orchestration with release readiness, task list, and new task entry">
</p>

<p align="center">
  <img src="assets/readme/zh-dark-new-task.png" alt="Across Agents Assistant new complex task form with function and product delivery modes, owner agent, subtask agents, and strict dependency mode">
</p>

## Why It Exists

Across Agents Assistant is built for developers who want more than a single chat box. It brings local agents, cloud LLMs, project chat, voice, MCP context, tool permissions, and owner-led task orchestration into one macOS workbench.

The core idea is cross-agent collaboration: pick an owner agent, keep local agents and cloud LLMs visible, break a complex request into waves, and inspect the final delivery. You can also choose a single agent for a focused complex task. Delivery quality is designed to be strong and reviewable, while still acknowledging that some generated artifacts may occasionally need small human refinements.

## Product Tour

### Current Dark Theme

The current product screenshots show the refreshed dark interface,
agent/provider icon catalog, task orchestration, model settings, MCP plugins,
tool permissions, and preferences.

| Project chat | Task orchestration |
| --- | --- |
| <img src="assets/readme/zh-dark-main-chat.png" alt="Dark project chat with directory tree and refreshed agent sidebar icons"> | <img src="assets/readme/zh-dark-task-orchestration.png" alt="Dark task orchestration with release readiness and task list"> |

| Complex task creation |
| --- |
| <img src="assets/readme/zh-dark-new-task.png" alt="New complex task form with selectable delivery type, owner agent, subtask agents, and dependency blocking"> |

| Models | MCP plugins |
| --- | --- |
| <img src="assets/readme/zh-dark-model-settings.png" alt="Dark model settings with local agents, cloud LLMs, and refreshed provider icons"> | <img src="assets/readme/zh-dark-mcp-plugins.png" alt="Dark MCP plugin settings with local knowledge, RAG, SQLite, and filesystem plugins"> |

| Tool permissions | Voice and preferences |
| --- | --- |
| <img src="assets/readme/zh-dark-tool-permissions.png" alt="Dark tool permission management with native and MCP tool policies"> | <img src="assets/readme/zh-dark-settings.png" alt="Dark settings with language, theme, voice, and auto-read controls"> |

### Agent And Provider Catalog

The `0.4.1` icon refresh keeps third-party marks as descriptive compatibility
labels inside Across-owned neutral tiles. Codex reads the installed
OpenAI-signed `Codex.app` icon at runtime when available and falls back to the
bundled OpenAI tile when it is not installed.

| Live model catalog | Icon source preview |
| --- | --- |
| <img src="assets/readme/zh-dark-model-settings.png" alt="Model catalog with local agents and cloud providers"> | <img src="assets/agent-icons/agent-icon-preview.png" alt="Dark and light agent icon preview with local agents and cloud providers"> |

### Light Chinese Theme

The app also includes a light Simplified Chinese interface.

| 项目对话 | 任务编排 |
| --- | --- |
| <img src="assets/readme/zh-light-main-chat.png" alt="浅色中文项目对话、目录树、本地 Agent 和云端 LLM"> | <img src="assets/readme/zh-light-task-orchestration.png" alt="浅色中文任务编排、Owner Agent、Wave 和子任务"> |

| 模型 | MCP 插件 |
| --- | --- |
| <img src="assets/readme/zh-light-model-settings.png" alt="浅色中文模型设置"> | <img src="assets/readme/zh-light-mcp-plugins.png" alt="浅色中文 MCP 插件"> |

| 工具权限 | 设置 |
| --- | --- |
| <img src="assets/readme/zh-light-tool-permissions.png" alt="浅色中文工具权限"> | <img src="assets/readme/zh-light-settings.png" alt="浅色中文语音和偏好设置"> |

### Release Quality Surfaces

Recent releases added visible quality and readiness workflows directly inside the app, so users can inspect complex task delivery instead of trusting a text-only status.

| Release evidence center | Release evaluation and E2E gate |
| --- | --- |
| <img src="assets/readme/zh-dark-release-evidence-center.png" alt="Dark release evidence center with readiness status, risks, checklist, and quality trend"> | <img src="assets/readme/zh-dark-release-evaluation.png" alt="Dark task orchestration release evaluation card with quality-gated tasks and complex E2E action"> |

| Startup diagnostics and RC check | Agent capabilities and native skills |
| --- | --- |
| <img src="assets/readme/zh-dark-startup-diagnostics.png" alt="Dark startup diagnostics with backend, provider, path, and packaged app readiness checks"> | <img src="assets/readme/zh-dark-agent-capabilities.png" alt="Dark agent capability settings with local agents, cloud LLMs, native skills, MCP plugins, and tool scope"> |

## What's New Since 0.2.0

The screenshots above are still the primary entry points: project chat, task orchestration, complex task creation, model settings, MCP plugins, tool permissions, and preferences. The newer releases mainly make those workflows more inspectable, safer to route, and easier to validate before release.

| Version | User-visible capability |
| --- | --- |
| `0.8.2` | Fully external shared-memory and task-runtime boundaries, pinned managed plugin sources for Across Context `v0.7.2` and Across Orchestrator `v0.6.2`, and packaged UI task-form accessibility synchronization. |
| `0.8.1` | Managed plugin runtime integrity repair, bounded Across Context upgrade/repair reinstalls, no automatic legacy hidden-directory migration, and built-in MCP defaults reset to managed `~/.across` paths to avoid macOS Documents prompts on fresh installs. |
| `0.8.0` | Agent Loop v2 host integration, external approval proxy, Plugin Center v2 capability badges, Across Context memory-provider handoff, all-project pending memory review, and managed install sources routed through the Across plugin repositories. |
| `0.7.1` | Toolbar icon sizing cleanup, Across-owned hollow Plugin Center icon polish, and managed install sources aligned to Across Context `v0.6.1` and Across Orchestrator `v0.5.1`. |
| `0.7.0` | Agent Loop integration through the external Across Orchestrator plugin, Plugin Center loop probes, checkpoint capability badges, and managed install sources aligned to Across Context `v0.6.0` and Across Orchestrator `v0.5.0`. |
| `0.6.0` | Plugin Center for Across plugin lifecycle management, external Across Context memory governance through the plugin CLI, and managed install sources aligned to Across Context `v0.5.0` and Across Orchestrator `v0.4.0`. |
| `0.5.1` | Tool approval now preserves successful MCP/local tool results even if the automatic continuation hits a gateway fallback. |
| `0.5.0` | Unified Across ecosystem runtime under `~/.across`, external Across Context MCP plugin data under `~/.across/data/across-context`, sidecar-first Across Orchestrator under `~/.across/plugins/across-orchestrator`, and AAA host discovery through `~/.across/bin`. |
| `0.4.3` | Plugin-required Across Orchestrator slot with one-click managed install, external HTTP/CLI task lifecycle, app-grade Release E2E evidence, packaged-app installer fix, and no built-in task-orchestration fallback for new submissions. |
| `0.4.2` | Plugin-first Across Context shared memory, external `across-context mcp` preference with built-in compatibility fallback, implementation status in API/UI, and packaged-app proof that standalone CLI and app share one vault. |
| `0.4.1` | Expanded local-agent/cloud-provider icon catalog, OpenCode MIT-source icon treatment, runtime Codex.app icon support with OpenAI fallback, unsupported local IDE integration cleanup, and stricter icon release-status checks. |
| `0.4.0` | Release Evidence Center, Startup Diagnostics, one-click RC Verification, local JSON/Markdown release reports, packaged-app health checks, exact seven-file Release E2E proof, and CI-backed open-source release checks. |
| `0.3.1` | Evidence Bundle export for completed tasks, non-secret Agent Cards, richer release-evaluation audit traces, persisted task quality rechecks, and public repository guards for private docs, local data, signing files, README assets, and secret patterns. |
| `0.3.0` | Release Evaluation summary, fixed high-complexity cross-agent Release E2E scenario, stronger delivery quality gates, capability preflight, native skill readiness, MCP safety signals, and targeted quality-remediation feedback. |
| `0.2.0` | Delivery Quality Benchmark, exact deliverable contracts, project/workspace hygiene checks, static web and browser probes, quality score reporting, and benchmark APIs for comparing complex task delivery across versions. |

## Core Capabilities

- Cross-agent task orchestration through the external Across Orchestrator plugin, with an owner agent, subtask agents, waves, status tracking, delivery health, and acceptance-oriented review.
- Per-agent capability profiles for tuning built-in skills, custom skills, native local-agent skills, MCP plugin scope, tool scope, and execution instructions before tasks are decomposed.
- Native skill management for local agents: create directory-based Claude Code skills, inspect installed OpenClaw/Hermes skills, and use each agent's own skill commands for install, update, and validation where supported.
- Native skill readiness checks mark missing binaries, environment variables, or config as unavailable; unavailable native skills stay visible for repair but are not used as strong routing signals.
- Task capability preflight that recommends the best-fit agent mix before submission and shows which skills matched the request.
- Delivery quality gates for exact file contracts, workspace hygiene, runnable probes, and static web feature evidence when UI behavior is requested.
- Built-in release E2E gate that can submit a fixed high-complexity cross-agent task covering exact artifact delivery, Web UI, Node API, CLI checks, browser verification, and quality-gate evidence.
- Unified model surface for local agents such as OpenClaw, Hermes, and Claude Code, plus cloud LLMs such as DeepSeek and MiniMax.
- Project-scoped chat with a real directory tree, session history, file attachments, screenshots, and context-aware prompts.
- Single-agent mode for sending a complex task to one chosen agent when collaboration is unnecessary.
- Voice and continuous conversation features that let you talk through work, auto-read assistant replies, and reduce keyboard time.
- Local tool approval for file search/read/write/edit, browser URL context, Finder context, Xcode context, image OCR, screenshot OCR, Mail drafts, Notes drafts, system volume, dark mode, and MCP-backed tools.
- MCP plugin settings for Across Context shared memory, local knowledge, external retrieval, SQLite, and filesystem context.
- Local runtime state under `~/.across`, kept outside the source tree.

## Local macOS Swiss Army Knife

Across Agents Assistant is not just a model launcher. Its local backend can connect agent work to the Mac around it, with explicit permission controls:

- Draft email in Mail without sending it automatically.
- Draft notes in Notes.
- Read Finder selection and folder context.
- Read the active Xcode document path.
- Inspect browser URL/title context when enabled.
- Read image text and screenshot text through OCR.
- Search, list, read, write, and edit scoped local files.
- Adjust simple system utilities such as volume or appearance when approved.
- Extend context through MCP servers for knowledge bases, SQLite, filesystem access, and external retrieval.

## Current Status

This project is under active development. More local agents, more cloud LLMs, stronger delivery validation, richer tool integrations, and additional product workflows are planned. The current release is `0.8.2` and source-first: the repository is intended for local building and inspection, not notarized binary distribution. See [CHANGELOG.md](CHANGELOG.md) for the release summary.

The `0.8.2` release completes the stricter product-boundary split for the
current source-first line. Shared memory is resolved through the external Across
Context plugin rather than an app-owned compatibility runtime, task
orchestration remains routed through the external Across Orchestrator plugin,
and managed plugin installs are pinned to Across Context `v0.7.2` and Across
Orchestrator `v0.6.2`. The packaged task form also accepts accessibility value
writes for the project-directory field, keeping UI-level E2E submission aligned
with normal user interaction.

The `0.8.1` release is a runtime hygiene patch for the Across plugin boundary.
Managed plugin installs now reject stale wrappers, editable installs, and
Python metadata that point back to protected user directories. Across Context
repair and upgrade force a fresh managed install with an app-owned npm cache and
bounded install timeout. Built-in local knowledge, SQLite, and filesystem MCP
defaults use managed `~/.across` paths, and saved settings that still reference
old Across hidden directories or the previous Documents defaults are reset to
the managed namespace.

The `0.8.0` release moves Agent Loop from a probe-level lifecycle into an
adapter-backed external runtime path. Across Orchestrator owns dynamic loop
planning, remediation dispatch, checkpoints, approval execution, and memory
provider hooks. Across Agents Assistant starts the sidecar with
`ACROSS_ORCHESTRATOR_MEMORY_PROVIDER=across-context`, proxies approval actions,
and surfaces Agent Loop v2 capability metadata without embedding orchestration
logic in the app.
Plugin Center memory review includes project-scoped pending summaries from
Across Context, so Agent Loop write candidates can be approved from the host UI.

The `0.7.1` release keeps the Agent Loop architecture intact while polishing
the console surface: toolbar icons now share one sizing metric, the Plugin
Center uses an Across-owned hollow puzzle-piece SVG, and managed plugin install
sources point to Across Context `v0.6.1` and Across Orchestrator `v0.5.1`.

The `0.7.0` Agent Loop work keeps AAA as the console and plugin host while
moving the repeat-observe-act-checkpoint lifecycle into Across Orchestrator.
The Plugin Center can inspect loop capabilities, start a loop probe through the
external plugin, and show checkpoint/memory-hook support without reading plugin
private data directly.

The `0.6.0` plugin lifecycle work adds a Plugin Center for installing,
repairing, probing, and uninstalling Across ecosystem plugins. Shared memory
review now goes through the external Across Context CLI contract, so the host
does not need to own the plugin's vault internals.

The `0.5.0` ecosystem work standardizes every Across-owned runtime path under
`~/.across`. Across Agents Assistant stores its own data in
`~/.across/data/across-agents-assistant`, discovers plugin wrappers from
`~/.across/bin`, and keeps plugin runtime code under `~/.across/plugins`.
Fresh installs and managed plugins do not read or write older standalone
hidden directories.

Across Context remains a standalone shared-memory plugin. Across Agents
Assistant runs it through the external `across-context mcp` server in product
mode, reports the active implementation mode in MCP settings/API responses, and
stores shared memory in `~/.across/data/across-context`.

Across Orchestrator is also standalone. Across Agents Assistant installs it
under `~/.across/plugins/across-orchestrator`, launches it as a local sidecar
HTTP runtime by default, and keeps CLI/MCP as external protocol adapters. If
the external plugin is not installed or connected, task orchestration is
unavailable and the UI offers one-click installation; new task submission does
not fall back to the historical in-app TaskOrchestrator.

Startup diagnostics discover Across-owned plugins by reading manifests and
wrappers under `~/.across/plugins` and `~/.across/bin`. That discovery path is
read-only and does not launch plugin processes, so startup should not require
Documents access. Explicit refresh, install, task submission, and MCP actions
may start the selected plugin when the user asks for that capability.

The `0.4.1` catalog work focuses on making the main agent and model surface ready for public source inspection:

- Local-agent and cloud-provider icons are bundled as dark/light neutral tiles with provenance recorded in `macOS-Client/Sources/Assets/icons/agent-icon-sources.json`.
- Codex prefers the installed OpenAI-signed `Codex.app` icon at runtime when present, while falling back to the bundled OpenAI tile when it is not installed.
- OpenCode uses the LobeHub Icons `opencode.svg` source inside the app-owned tile instead of relying on a Marketplace image with unresolved redistribution terms.
- Unsupported local IDE integrations are omitted from the shipped local-agent catalog until their CLI install and authentication flow can be supported reliably.
- `scripts/open_source_check.sh` now blocks icon entries that still require release review.

The `0.4.0` quality work that this release builds on focuses on making complex agent deliveries easier to inspect and harder to overclaim:

- Release Evaluation summarizes recent task evidence into a local readiness signal without rerunning expensive probes or restoring old tasks automatically.
- Release Evaluation now includes a readiness checklist, recent score trend, required probe coverage, local/cloud agent-mix coverage, benchmark status, and per-task audit traces so release quality can be compared across versions instead of judged from one task row.
- Release Evidence Center turns those backend audit signals into an in-app review surface with readiness checks, probe coverage, recent task evidence, per-task Evidence Bundle viewing, and local JSON export.
- Startup Diagnostics adds a first-run and packaged-app health surface for backend status, provider readiness, app data paths, logs, socket, database, task persistence, and local evidence exports.
- RC Verification adds a one-click release report in Settings -> Diagnostics. It combines startup diagnostics, the latest fixed Release E2E benchmark, release-evaluation context, and local JSON/Markdown report files under the app data directory.
- Task details expose execution evidence, quality gates, remediation history, quality score, and local/cloud agent mix.
- Agent Cards include native-skill health, tool-risk summaries, strict-scope warnings, and repair hints for unavailable native skills. A non-secret `/api/agent-cards` export provides an A2A-like internal capability card for each supported agent.
- Complex Release E2E validates an exact multi-file Web/API/CLI delivery through static checks, API probes, CLI checks, browser evidence, workspace hygiene, security/privacy scans, and cross-agent coverage.
- Complex Release E2E remediation now reports actual remediation subtask count and gives agents targeted patch plans for Route Evidence failures, reducing false benchmark failures and broad rewrite attempts.
- Delivery quality benchmarks and evidence bundles support both live in-memory tasks and lazily loaded persisted task records, so historical task details can be rechecked from the packaged app without restoring or restarting the task.
- Delivery contract extraction filters system temporary project-directory hints so local scratch directories do not become phantom deliverables.
- Native skill readiness and MCP safety information now participate in task preflight so unavailable skills stay visible for repair but do not become strong routing signals.
- GitHub Actions, CodeQL, Dependabot, secret scanning, and `scripts/open_source_check.sh` protect the public repository from private docs, local runtime data, signing artifacts, missing README assets, whitespace issues, dependency drift, and common secret patterns.
- The packaged app defaults to a faster backend bundle layout and avoids reopening duplicate main windows on launch.

## Quick Start

Clone the repository:

```bash
git clone git@github.com:fantasyce/across-agents-assistant.git
cd across-agents-assistant
```

Build the local macOS app bundle:

```bash
bash build_app.sh
```

The default packaging mode uses an unpacked backend bundle for faster app startup. For troubleshooting only, you can compare the older single-file backend mode:

```bash
BACKEND_BUNDLE_MODE=onefile bash build_app.sh
```

Open the app from the generated bundle:

```bash
open -n "build/Across Agents Assistant.app"
```

Optional: install the locally built app into Applications:

```bash
rm -rf "/Applications/Across Agents Assistant.app"
ditto "build/Across Agents Assistant.app" "/Applications/Across Agents Assistant.app"
open -n "/Applications/Across Agents Assistant.app"
```

On first launch:

- Open Settings -> Diagnostics to confirm backend health, local runtime paths, provider readiness, and task persistence before starting a complex task.
- Open Model Settings.
- Configure at least one cloud LLM API key, or install/configure one local agent.
- Supported local agent integrations currently include OpenClaw, Hermes, Claude Code, Codex, OpenCode, and Cursor Agent.
- Open Agent Capabilities to tune each agent's built-in/custom skills, install or inspect native local-agent skills, configure MCP plugins, set tool scope, and add task-specific operating notes.
- Native skills that fail readiness checks are shown as unavailable with the missing requirement, and are excluded from automatic capability routing until repaired.
- When creating a complex task, review Capability Preflight before submitting; it previews the recommended agent and matching skills.
- Grant macOS permissions only when you need the related feature, such as microphone, screen capture, Apple Events, or file access.

Local runtime state is stored under `~/.across`. Build outputs, local credentials, logs, databases, certificates, and model files should stay outside Git.

## Requirements

- macOS 14 or newer
- Xcode command line tools
- Swift 5.9 or newer
- Python 3.10 or newer

Optional integrations may require local CLI agents, provider API keys, MCP server configuration, or user-granted macOS permissions.

## Build From Source

```bash
bash build_app.sh
```

The script creates a local development app bundle at:

```text
build/Across Agents Assistant.app
```

By default, the bundle is ad-hoc signed and is not a distributable DMG. Newer macOS versions may require a trusted signing identity before opening a packaged GUI app through LaunchServices. For future binary distribution, provide a real signing identity through `SIGNING_IDENTITY`, then complete Developer ID signing, hardened runtime, and notarization outside the public Git tree.

## Backend Development

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python3 -m pytest tests --ignore=tests/e2e -q
```

### Delivery Quality Benchmark

After a complex task completes, the backend can turn the task's delivery report
into a release-quality benchmark result. This is useful for comparing versions
with the same task prompt and acceptance thresholds.

```bash
curl --unix-socket "$HOME/.across/run/across-agents-assistant/across-agents.sock" \
  "http://backend/api/tasks/<task-id>/quality-benchmark?expected_files=index.html,styles.css,app.js,README.md&required_probes=static_web_smoke,browser_e2e&min_quality_score=70"
```

The benchmark fails if required probes fail, expected files drift, the quality
gate is not passed, required checks are skipped, active remediation remains, or
the final score falls below the requested threshold.

For a broader release audit, export the task evidence bundle. It is read-only,
redacts credential-shaped values, includes the delivery contract, requirement
manifest, owner decision, quality health, artifacts, acceptance records, and a
benchmark result in one local JSON payload:

```bash
curl --unix-socket "$HOME/.across/run/across-agents-assistant/across-agents.sock" \
  "http://backend/api/tasks/<task-id>/evidence-bundle?expected_files=index.html,styles.css,app.js,README.md&required_probes=static_web_smoke,browser_e2e&min_quality_score=70"
```

Agent capability cards can also be exported without secrets:

```bash
curl --unix-socket "$HOME/.across/run/across-agents-assistant/across-agents.sock" \
  "http://backend/api/agent-cards"
```

Startup diagnostics can be checked from the packaged app or from the socket:

```bash
curl --unix-socket "$HOME/.across/run/across-agents-assistant/across-agents.sock" \
  "http://backend/api/diagnostics/startup"
```

### Across Orchestrator Runtime Slot

Task orchestration is hosted by an external Across Orchestrator product. The
desktop app is the console and plugin host; it does not silently fall back to
the historical in-app orchestrator in normal product mode. If the plugin is not
installed or connected, the task orchestration entry is shown as unavailable
with a one-click install action.

```bash
ACROSS_AGENTS_ORCHESTRATOR_MODE=external    # default and only supported product mode
ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT=http://127.0.0.1:8765
ACROSS_AGENTS_ORCHESTRATOR_COMMAND=across-orchestrator
ACROSS_AGENTS_ORCHESTRATOR_PLUGIN_HOME="$HOME/.across/plugins"
ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE=git+https://github.com/fantasyce/across-orchestrator.git
ACROSS_AGENTS_ORCHESTRATOR_PYTHON=/opt/homebrew/bin/python3
ACROSS_AGENTS_ORCHESTRATOR_AUTORUN=1
ACROSS_ORCHESTRATOR_MEMORY_PROVIDER=across-context
ACROSS_CONTEXT_COMMAND="$HOME/.across/bin/across-context"
```

When an endpoint is configured, the app talks to that external HTTP runtime. If
no endpoint is configured, it discovers the wrapper at
`~/.across/bin/across-orchestrator`, starts a local sidecar with
`across-orchestrator serve --host 127.0.0.1 --port 0`, and reads runtime
metadata from `~/.across/run/across-orchestrator`. The UI calls
`/api/orchestrator/plugin/install` to create the managed virtualenv under
`~/.across/plugins/across-orchestrator` and install the external product from
the configured source.

Packaged builds cannot use the backend binary itself to create Python
virtualenvs. The installer auto-discovers a Python 3 interpreter from common
locations; set `ACROSS_AGENTS_ORCHESTRATOR_PYTHON` only when you need to force a
specific interpreter.

External task state stays in `~/.across/data/across-orchestrator`; the app only
keeps a thin task-id index in
`~/.across/data/across-agents-assistant/orchestrator-plugin/tasks.json` so the
main task UI can show external tasks.

The historical in-app `TaskOrchestrator` code remains only for legacy task data
inspection and migration-oriented maintenance paths. It is not a product
runtime for new task submission.

External Release E2E evidence is accepted only when the app-grade benchmark
passes artifact integrity, workspace hygiene, security/privacy, agent mix,
static web smoke, browser E2E, API service, and CLI gates. The focused backend
check is:

```bash
PYTHONPATH=backend/src pytest \
  backend/tests/test_orchestrator_plugin.py \
  backend/tests/test_api_orchestrator_plugin.py \
  backend/tests/test_api_release_e2e.py \
  backend/tests/test_api_startup_diagnostics.py \
  -q
```

RC verification can be run from Settings -> Diagnostics or through the packaged app backend. It writes non-secret JSON and Markdown reports to `$HOME/.across/data/across-agents-assistant/release-reports/`:

```bash
curl --request POST --unix-socket "$HOME/.across/run/across-agents-assistant/across-agents.sock" \
  "http://backend/api/release/verification"
```

When changing startup, task orchestration, delivery contracts, capability routing, native skills, MCP safety, or release evaluation, also run the focused tests for the touched area and verify the packaged app path before considering the change release-ready.

## Open-Source Quality Checks

Run the public repository guard locally before publishing changes:

```bash
bash scripts/open_source_check.sh
```

The check verifies whitespace, forbidden tracked artifacts, common secret patterns, README image assets, and basic build-script syntax. GitHub Actions also runs the open-source check, backend regression tests, and a Swift build on pushes to `main` and pull requests.

GitHub security automation is also enabled:

- The Security workflow runs CodeQL for the Python backend on pull requests, pushes to `main`, scheduled weekly runs, and manual dispatches. The Quality workflow separately verifies the Swift macOS client build.
- Dependabot monitors GitHub Actions, Python requirements, and Swift Package Manager dependencies.
- Repository secret scanning and push protection are enabled for the public repository.

## macOS Client Development

```bash
cd macOS-Client
swift build -c release --force-resolved-versions --skip-update
```

## Configuration And Secrets

Do not commit API keys, local runtime data, build outputs, app databases, logs, screenshots with private content, local model files, certificates, notarization credentials, or machine-specific paths.

Provider credentials should be configured through the app, environment variables, Keychain, or another local ignored configuration path.

Optional MOSS-TTS integration is controlled by:

- `MOSS_TTS_PATH`
- `MOSS_TTS_MODEL_DIR`

If these variables are not set, the TTS service falls back to Edge-TTS when available.

## License and IP

Project-owned source code is licensed under the GNU Affero General Public
License v3.0. The intended SPDX expression is `AGPL-3.0-only`.

The AGPLv3 permits commercial use, but modified covered versions must provide
corresponding source when the license requires it, including for remote network
interaction. Proprietary closed-source use requires a separate commercial
license from the rights holder.

See `IP_AND_LICENSE_POLICY.md`, `CONTRIBUTOR_CERTIFICATE.md`,
`THIRD_PARTY_NOTICES.md`, and `CODE_OF_CONDUCT.md` for contribution
certification, dependency notices, release review policy, and community
expectations.

## Contributing

Community channels are open:

- [Discussions](https://github.com/fantasyce/across-agents-assistant/discussions) for questions, troubleshooting, workflows, and early ideas.
- [Issues](https://github.com/fantasyce/across-agents-assistant/issues/new/choose) for reproducible bugs, scoped feature requests, and concrete product feedback.

See [CONTRIBUTING.md](CONTRIBUTING.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing code or opening long-form feedback.

Security reporting guidance is in [SECURITY.md](SECURITY.md).

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).

Project names, logos, app icons, and official release branding are governed by the [Trademark Policy](TRADEMARK_POLICY.md). Third-party agent and provider names are used only to describe compatibility.

See [NOTICE](NOTICE) for copyright and attribution notes.

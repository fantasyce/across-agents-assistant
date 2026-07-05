<h1 align="center">Across Agents Assistant</h1>

<p align="center">
  <img src="assets/readme/app-icon.png" alt="Across Agents Assistant app icon" width="120" height="120">
</p>

<p align="center">
  <strong>Supervised engineering loops for coding agents.</strong>
</p>

<p align="center">
  <a href="https://github.com/fantasyce/across-agents-assistant/actions/workflows/quality.yml"><img src="https://github.com/fantasyce/across-agents-assistant/actions/workflows/quality.yml/badge.svg" alt="Quality workflow status"></a>
  <a href="https://github.com/fantasyce/across-agents-assistant/actions/workflows/security.yml"><img src="https://github.com/fantasyce/across-agents-assistant/actions/workflows/security.yml/badge.svg" alt="Security workflow status"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
</p>

<p align="center">
  Turn repo audits, release checks, plugin evaluations, and candidate product
  iterations into repeatable AI workflows with local evidence, memory, and
  human approval across Codex, Kimi Code, Claude Code, Claude Desktop,
  AAA, and other MCP-capable hosts.
</p>

<p align="center">
  <img src="assets/readme/zh-dark-main-chat.png" alt="Across Agents Assistant dark main chat with project tree, local agents, and cloud LLMs">
</p>

<p align="center">
  <img src="assets/readme/zh-dark-task-orchestration.png" alt="Across Agents Assistant dark workflows panel with release readiness, run list, and guided workflow entry">
</p>

<p align="center">
  <img src="assets/readme/zh-dark-new-task.png" alt="Across Agents Assistant expert task form with function and product delivery modes, owner agent, subtask agents, and strict dependency mode">
</p>

## Try This First

Across should be evaluated through a concrete workflow before its internal
modules. The recommended first run is Repository Quality Copilot:

In the desktop app, open **Workflows** and choose **Repository Quality
Copilot**. From a terminal, the same starting point is:

```bash
across-autopilot loop run --spec repo-quality-copilot --json
```

Expected output:

- markdown repository quality report
- JSON evidence artifact
- release/readiness checklist
- optional pending memory for Across Context review

Agent-readable entrypoints:

- [llms.txt](llms.txt) for model and agent product discovery
- [AGENTS.md](AGENTS.md) for coding-agent repository instructions
- [across.product.json](across.product.json) for machine-readable product
  classification
- [examples/agent-tasks](examples/agent-tasks) for copyable agent task
  templates

## Why It Exists

Across Agents Assistant is built for developers who want more than a single chat
box. It brings local agents, cloud LLMs, project chat, voice, MCP context, tool
permissions, guided workflow starts, owner-led task orchestration, and Loop
Engineering evidence into one macOS workbench.

The first screen is workflow-first: Repository Quality Copilot, Plugin
Compatibility Lab, and Release Captain prepare the task contract and evidence
targets before submission. Expert users can still open the full task form, pick
an owner agent, keep local agents and cloud LLMs visible, break a complex
request into waves, and inspect the final delivery.

## Loop Engineering Use Cases

Across is now packaged as a Loop Engineering workspace: a way to turn repeat
engineering chores into supervised agent loops with evidence, repair attempts,
and reusable memory.

Start with concrete workflows:

- **Repository Quality Copilot:** run a bounded repo health loop before releases
  or PR review.
- **Release Captain:** convert a release checklist into an evidence-backed
  readiness report.
- **Plugin Compatibility Lab:** evaluate external MCP or agent plugins before
  adding them to a team's workflow.
- **Autonomous Product Iteration:** let Across create a candidate workspace,
  validate the change, and stop with a human-review promotion package.

Start with **Plugin Compatibility Lab v2** when you want to test whether an MCP
server, coding-agent plugin, or agent tool is safe enough for a team workflow.
It turns the adoption decision into a workflow card, protocol-readiness matrix,
trust receipt, evidence graph, pending memory, A2A delegation envelope, and
OTel/OTLP-compatible trace export. See
[Plugin Compatibility Lab](examples/agent-tasks/plugin-compatibility-lab.md).

The product packaging, examples, and host-neutral install story are kept in
`README.md`, `llms.txt`, `across.product.json`, and the copyable tasks under
`examples/agent-tasks/`.

## Across Product Boundaries

The Across ecosystem is intentionally split into four independently releasable
products:

- **Across Agents Assistant** is the macOS host and control panel. It owns the
  Swift UI, local backend API, provider configuration, credentials, macOS
  permissions, local agent process discovery, tool approvals, task evidence
  views, and plugin lifecycle UI.
- **Across Context** is the shared-memory plugin. It owns memory search, memory
  write policy, pending review, MCP memory tools, and durable memory under
  `~/.across/data/across-context`. The host discovers it through
  `~/.across/bin/across-context` after a managed install under
  `~/.across/plugins/across-context`.
- **Across Orchestrator** is the task-runtime plugin. It owns task lifecycle,
  delivery contracts, dependency waves, Agent Loop checkpoints, quality gates,
  remediation behavior, evidence bundles, and durable task state under
  `~/.across/data/across-orchestrator`. The host discovers it through
  `~/.across/bin/across-orchestrator`.
- **Across Autopilot** is the LoopSpec supervision plugin. It owns trigger
  queues, candidate run supervision, host-session recovery, repair/retry
  evidence, release-readiness reports, and autonomous iteration guardrails under
  the managed `~/.across` plugin boundary.

The three core plugins are generic agent-host plugins, not AAA-only modules.
Codex, Claude Code, Claude Desktop, AAA, and
other CLI/MCP-capable hosts should consume them through pinned managed installs,
CLI, HTTP, MCP, plugin manifests, or host APIs. AAA product code must not import
or execute plugin implementation files from a development checkout such as
`~/Documents/projects/...`. Development checkouts are valid only as
user-selected project roots or explicit developer install source overrides.
Normal packaged-app runtime paths stay under `~/.across` so fresh installs do
not trigger macOS Documents permission prompts just because a plugin exists.

## Product Tour

### Current Dark Theme

The current product screenshots show the refreshed dark interface,
agent/provider icon catalog, workflows, model settings, MCP plugins,
tool permissions, and preferences.

| Project chat | Workflows and runs |
| --- | --- |
| <img src="assets/readme/zh-dark-main-chat.png" alt="Dark project chat with directory tree and refreshed agent sidebar icons"> | <img src="assets/readme/zh-dark-task-orchestration.png" alt="Dark workflows panel with release readiness and run list"> |

| Expert task creation |
| --- |
| <img src="assets/readme/zh-dark-new-task.png" alt="Expert task form with selectable delivery type, owner agent, subtask agents, and dependency blocking"> |

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

| 项目对话 | 工作流和运行记录 |
| --- | --- |
| <img src="assets/readme/zh-light-main-chat.png" alt="浅色中文项目对话、目录树、本地 Agent 和云端 LLM"> | <img src="assets/readme/zh-light-task-orchestration.png" alt="浅色中文工作流、Owner Agent、Wave 和子任务"> |

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

## Recent Product Highlights

The screenshots above are still the primary entry points: project chat, task
workflows, expert task creation, model settings, MCP plugins, tool
permissions, and preferences. This README keeps the product shape current; the
full release chronology lives in [CHANGELOG.md](CHANGELOG.md).

| Version | User-visible capability |
| --- | --- |
| `0.9.37` | Adds automatic lifecycle retention for self-iteration B candidates so old workspaces, candidate app artifacts, runtime homes, and failed run records do not accumulate indefinitely. |
| `0.9.36` | Moves self-iteration candidate app bundles into Autopilot-managed candidate artifacts under `~/.across` instead of leaving B apps in `~/Applications`. |
| `0.9.35` | Pins Autopilot `v0.2.17` so autonomous self-iteration uses Node-fetchable OpenAI Agents SDK source signals instead of a docs HTML page that Node fetch can receive as 403. |
| `0.9.34` | Aligns the self-iteration release-source mirror with the managed Autopilot `v0.2.16` plugin pin, keeping user-machine candidate workspaces on the same released producer version they execute. |
| `0.9.33` | Hardens autonomous research-decision timeout handling with structured local Codex fallback diagnostics and pins Autopilot `v0.2.16` for more reliable source intake. |
| `0.9.32` | Hardens public release-source bootstrap for user machines without development checkouts by retrying failed clones and falling back to Git HTTP/1.1. |
| `0.9.31` | Removes implicit development-checkout source discovery from self-iteration, bootstraps source mirrors from public release tags, pins Autopilot `v0.2.15`, and finishes Codex defaults for self-repair LoopSpecs. |
| `0.9.30` | Routes autonomous self-iteration through local Codex, pins Autopilot `v0.2.14`, adds reviewable tool/A2A integration surfaces, and removes development-checkout fallback from Live E2E. |
| `0.9.29` | Removes exception-object text from the public self-iteration source-mirror status payload while preserving local diagnostics. |
| `0.9.28` | Adds true daily 10:00 local-time autonomous self-iteration scheduling and restores the scheduler after packaged-app restarts. |
| `0.9.27` | Adds a pre-run source mirror refresh gate so autonomous B candidates start from a fresh, clean A baseline instead of a stale mirror. |
| `0.9.26` | Adds bounded AI-Ready Context synthesis for loop source signals and pins Autopilot `v0.2.13` for stronger self-iteration validation. |
| `0.9.25` | Keeps Workbench trigger actions focused on actionable queued triggers instead of terminal queue history. |
| `0.9.24` | Keeps Loop Engineering ops health focused on unresolved current failures while preserving recovered and historical failure evidence for audit. |
| `0.9.23` | Enables queued self-iteration dispatch by default, expands deterministic host repair fallbacks, and pins Autopilot `v0.2.12` for stricter candidate/platform failure routing. |
| `0.9.22` | Updates the managed Autopilot pin to `v0.2.11`, keeping platform self-repair focused on platform gaps instead of ordinary candidate validation failures. |
| `0.9.21` | Hardens candidate app lifecycle isolation so self-iteration validation installs managed plugins only inside the candidate runtime home. |
| `0.9.20` | Adds supervised loop-engineering self-repair: eligible platform failures enqueue an isolated B candidate repair, run validation and self-hosting evidence, and stop at human-review promotion. |
| `0.9.19` | Consolidates backend dependency hygiene updates for FastAPI, MCP, OpenAI, and Anthropic SDK lower bounds. |
| `0.9.18` | Updates the managed Across Orchestrator pin to `v0.7.10`, keeping Autopilot at `v0.2.8` and Context at `v0.8.8`. |
| `0.9.17` | Updates the managed Across Orchestrator pin to `v0.7.9`, keeping Autopilot at `v0.2.8` and Context at `v0.8.8`. |
| `0.9.16` | Makes Workflows the task entry point: Repository Quality Copilot, Plugin Compatibility Lab, and Release Captain now create editable task drafts while the expert task form remains available. |
| `0.9.15` | Completes the P0-P3 frontier interop release gate with MCP Tasks projection, LF A2A v2, AG-UI task-card projection, Remote MCP/OAuth v1, OTel export, Skills bridge, optional sandbox evidence, memory backend projections, local agent protocol bridges, and managed pins for Autopilot `v0.2.8`, Orchestrator `v0.7.8`, and Context `v0.8.8`. |
| `0.9.13`-`0.9.14` | Consolidates public Markdown entrypoints, keeps removed planning docs out of agent-readable surfaces, and verifies producer-first source sync. |
| `0.9.11`-`0.9.12` | Adds Kimi Code and refreshes local-agent icon provenance, packaged assets, and backend icon loading. |
| `0.9.6` | Adds the frontier agent-team interop release gate, including workbench status, E2E evidence, stricter RC verification, and unified pre-release gate evidence. |
| `0.9.0` | Ships the four-product Loop Engineering platform with managed Autopilot, candidate workspaces, model lease checks, distinct-model review, and human-review promotion packages. |
| `0.8.0` | Moves Agent Loop execution into the external Orchestrator runtime while AAA stays the host UI, approval proxy, Plugin Center, and memory review surface. |
| `0.5.0` | Standardizes Across-owned runtime paths under `~/.across`, including plugin wrappers, plugin runtime code, and durable product data. |
| `0.4.0` | Adds Release Evidence Center, Startup Diagnostics, one-click RC Verification, local release reports, packaged-app checks, Release E2E proof, and open-source guards. |
| `0.2.0` | Introduces delivery quality benchmarks, exact deliverable contracts, workspace hygiene checks, static web/browser probes, and quality score reporting. |

## Core Capabilities

- Guided workflow start for Repository Quality Copilot, Plugin Compatibility
  Lab, and Release Captain, with editable task drafts before submission.
- Cross-agent task orchestration through the external Across Orchestrator plugin, with an owner agent, subtask agents, waves, status tracking, delivery health, and acceptance-oriented review.
- Per-agent capability profiles for tuning built-in skills, custom skills, native local-agent skills, MCP plugin scope, tool scope, and execution instructions before tasks are decomposed.
- Native skill management for local agents: create directory-based Claude Code skills, inspect installed OpenClaw/Hermes skills, and use each agent's own skill commands for install, update, and validation where supported.
- Native skill readiness checks mark missing binaries, environment variables, or config as unavailable; unavailable native skills stay visible for repair but are not used as strong routing signals.
- Task capability preflight that recommends the best-fit agent mix before submission and shows which skills matched the request.
- Delivery quality gates for exact file contracts, workspace hygiene, runnable probes, and static web feature evidence when UI behavior is requested.
- Release E2E gate in the AAA host that submits and inspects an app-grade scenario through the external orchestration runtime, covering exact artifact delivery, Web UI, Node API, CLI checks, browser verification, quality-gate evidence, and host-visible remediation.
- Unified model surface for local agents such as OpenClaw, Hermes, Claude Code,
  Claude Desktop, Codex, Kimi Code, OpenCode, and Cursor Agent, plus cloud LLMs such as
  DeepSeek, MiniMax, and Agnes.
- Project-scoped chat with a real directory tree, session history, file attachments, screenshots, and context-aware prompts.
- Single-agent mode for sending a complex task to one chosen agent when collaboration is unnecessary.
- Voice and continuous conversation features that let you talk through work, auto-read assistant replies, and reduce keyboard time.
- Local tool approval for file search/read/write/edit, browser URL context, Finder context, Xcode context, image OCR, screenshot OCR, Mail drafts, Notes drafts, system volume, dark mode, and MCP-backed tools.
- MCP plugin settings for host-managed MCP defaults. Across Context is the external shared-memory plugin; local knowledge, external retrieval, SQLite, and filesystem entries remain host-configured MCP integrations.
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

This project is under active development. The current release is `0.9.37` and
source-first: the repository is intended for local building and inspection, not
notarized binary distribution. See [CHANGELOG.md](CHANGELOG.md) for detailed
release notes.

Current managed producer pins:

- Across Autopilot `v0.2.17`
- Across Orchestrator `v0.7.10`
- Across Context `v0.8.8`

The current release keeps autonomous Loop Engineering reviewable while routing
the researcher, builder, and reviewer through the local Codex agent. AAA restores
an already configured daily scheduler on startup, dispatches the default
self-iteration trigger at `10:00` in `Asia/Shanghai`, and validates candidates
through managed plugin runtimes under `~/.across`.

Autonomous Product Iteration uses `~/.across` source mirrors as controlled
snapshots, not as editable working copies. Before candidate B workspaces run,
AAA refreshes those mirrors from clean A checkouts and exposes mirror freshness
in the self-iteration plan; drifted mirrors block the loop before any candidate
mutation starts.
Candidate B app lifecycle checks install temporary app bundles under
`~/.across/data/across-autopilot/candidate-apps/<candidate_id>/` with isolated
runtime homes instead of leaving long-lived candidate apps in `~/Applications`.

AAA remains the host UI and policy surface. It uses plugin manifests, wrappers,
HTTP, CLI, MCP, or host APIs; product code must not import implementation files
from Autopilot, Orchestrator, or Context development checkouts.

Operational references:

- [Open Source Release Handbook](OPEN_SOURCE_RELEASE_HANDBOOK.md) records the
  producer-first release flow, validation gates, Live E2E, tagging, and
  rollback path.
- [AGENTS.md](AGENTS.md), `llms.txt`, and `across.product.json` are the
  agent-readable product entrypoints.
- `examples/agent-tasks/` contains the copyable workflow tasks for Repository
  Quality Copilot, Release Captain, and Plugin Compatibility Lab.

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

- Open Settings -> Diagnostics to confirm backend health, local runtime paths,
  provider readiness, and task persistence.
- Open Model Settings.
- Configure at least one cloud LLM API key, or install/configure one local agent.
- Supported local agent integrations currently include OpenClaw, Hermes, Claude
  Code, Claude Desktop, Codex, Kimi Code, OpenCode, and Cursor Agent.
- Open Agent Capabilities to tune each agent's built-in/custom skills, install or inspect native local-agent skills, configure MCP plugins, set tool scope, and add task-specific operating notes.
- Native skills that fail readiness checks are shown as unavailable with the missing requirement, and are excluded from automatic capability routing until repaired.
- Open Workflows and start with Repository Quality Copilot, Plugin
  Compatibility Lab, or Release Captain. The generated task draft stays editable
  before submission.
- For expert tasks, review Capability Preflight before submitting; it previews
  the recommended agent and matching skills.
- Grant macOS permissions only when you need the related feature, such as microphone, screen capture, Apple Events, or file access.

Local runtime state is stored under `~/.across`. Build outputs, local credentials, logs, databases, certificates, and model files should stay outside Git.

## Requirements

- macOS 14 or newer
- Xcode command line tools
- Swift 5.10 or newer
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
any in-app task runtime in normal product mode. If the plugin is not
installed or connected, the task orchestration entry is shown as unavailable
with a one-click install action.

```bash
ACROSS_AGENTS_ORCHESTRATOR_MODE=external    # default and only supported product mode
ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT=http://127.0.0.1:8765
ACROSS_AGENTS_ORCHESTRATOR_COMMAND=across-orchestrator
ACROSS_AGENTS_ORCHESTRATOR_PLUGIN_HOME="$HOME/.across/plugins"
ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE=git+https://github.com/fantasyce/across-orchestrator.git@v0.7.10
ACROSS_AGENTS_AUTOPILOT_INSTALL_SOURCE=git+https://github.com/fantasyce/across-autopilot.git#v0.2.17
ACROSS_AGENTS_ORCHESTRATOR_PYTHON=/opt/homebrew/bin/python3
ACROSS_AGENTS_ORCHESTRATOR_AUTORUN=1
ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE=git+https://github.com/fantasyce/across-context.git#v0.8.8
ACROSS_ORCHESTRATOR_MEMORY_PROVIDER=across-context
ACROSS_CONTEXT_COMMAND="$HOME/.across/bin/across-context"
```

In packaged or product mode, set `ACROSS_AGENTS_PRODUCT_MODE=1`. Protected
runtime overrides such as `ACROSS_HOME`, `ACROSS_PLUGIN_HOME`,
`ACROSS_BIN_HOME`, `ACROSS_CONTEXT_COMMAND`, and
`ACROSS_AGENTS_BACKEND_DIR` are ignored when they point under user project
locations such as `~/Documents`, `~/Desktop`, or `~/Downloads`; the host uses
the managed `~/.across` runtime instead. The same rule applies to
`ACROSS_AGENTS_HOME`, `ACROSS_AGENTS_DB_PATH`, plugin install-source overrides,
`ACROSS_CONTEXT_HOME`, and `ACROSS_ORCHESTRATOR_HOME`. Product diagnostics and
MCP auto-connect also ignore protected `across-context` or
`across-orchestrator` commands found through `PATH` instead of reading or
executing those wrappers. Source checkout paths are accepted only when
`ACROSS_AGENTS_DEVELOPER_MODE=1` or
`ACROSS_AGENTS_ALLOW_DEVELOPMENT_RUNTIME_PATHS=1` is set intentionally. The
same boundary is applied when plugin child environments carry
`ACROSS_CONTEXT_PRODUCT_MODE=1` or `ACROSS_ORCHESTRATOR_PRODUCT_MODE=1`.

When an endpoint is configured, the app talks to that external HTTP runtime. If
no endpoint is configured, it discovers the wrapper at
`~/.across/bin/across-orchestrator`, starts a local sidecar with
`across-orchestrator serve --host 127.0.0.1 --port 0`, and reads runtime
metadata from `~/.across/run/across-orchestrator`. The UI calls
`/api/orchestrator/plugin/install` to create the managed virtualenv under
`~/.across/plugins/across-orchestrator` and install the external product from
the configured source.

Packaged builds cannot use the backend binary itself to create Python
virtualenvs. The managed Across Orchestrator installer requires Python
`>=3.11,<3.14` and auto-discovers a supported interpreter from common
locations; set `ACROSS_AGENTS_ORCHESTRATOR_PYTHON` only when you need to force a
specific interpreter. Product mode rejects interpreters under protected user
project locations unless developer mode is explicitly enabled. The AAA backend source runtime remains Python
`>=3.10,<3.14`.

External task state stays in `~/.across/data/across-orchestrator`; the app only
keeps a thin task-id index in
`~/.across/data/across-agents-assistant/orchestrator-plugin/tasks.json` so the
main task UI can show external tasks.

### Across Context Memory Plugin

Shared memory is hosted by the external Across Context product. The desktop app
owns the Plugin Center, memory review surfaces, and host permissions; Across
Context owns memory policy, CLI/MCP tools, pending write review, and durable
vault files.

Managed installs place runtime code under
`~/.across/plugins/across-context`, create the wrapper at
`~/.across/bin/across-context`, and keep durable memory under
`~/.across/data/across-context`. The packaged app should discover and repair
that managed runtime instead of pointing at `npm link`, a source checkout, or a
path under `~/Documents/projects`.

AAA no longer packages an in-app task orchestration runtime. Task execution,
loop state, checkpoints, remediation, and final evidence are owned by the
external Across Orchestrator plugin; AAA keeps only host UI, API projection, and
read-only evidence views for task records.

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

Live E2E can be run against a temporary AAA backend and an external
Across Orchestrator command without touching the packaged app socket:

```bash
ACROSS_AGENTS_ORCHESTRATOR_COMMAND=/path/to/across-orchestrator \
  bash scripts/run_live_e2e.sh all
```

The script creates temporary `ACROSS_HOME` and `ACROSS_AGENTS_HOME` roots,
starts the backend on a temporary Unix socket, runs
`backend/tests/e2e/run_e2e.py`, and then runs the legacy socket-backed
`backend/tests/e2e/test_api_e2e.py` with `ACROSS_AGENTS_RUN_LIVE_E2E=1`.
It writes a non-secret gate evidence JSON file to
`$HOME/.across/data/across-agents-assistant/release-reports/` by default; set
`ACROSS_AGENTS_LIVE_E2E_EVIDENCE_PATH` to store it elsewhere. Remove
`$HOME/.across/data/across-agents-assistant/release-reports/*-gate-evidence.json`
to clear stale local gate evidence.
Other pre-release gates use the same non-secret evidence contract. After a
local gate passes, write evidence with:

```bash
bash scripts/write_pre_release_gate_evidence.sh open_source_check passed local_script
bash scripts/write_pre_release_gate_evidence.sh backend_regression passed local_script
bash scripts/write_pre_release_gate_evidence.sh swift_behavior_checks passed local_script
bash scripts/write_pre_release_gate_evidence.sh swift_package_gate passed local_script
```

Or run all local pre-release gates and write evidence in one pass:

```bash
bash scripts/run_pre_release_local_gates.sh
```

The packaged app reads these files from
`$HOME/.across/data/across-agents-assistant/release-reports/`. It does not need
or use a development checkout path to verify attached release evidence.
The GitHub `Live E2E` workflow exposes the same runner as a manual
`workflow_dispatch` job and installs Across Orchestrator `v0.7.10` before
running it. The workflow uploads `live-e2e-gate-evidence` as a run artifact.
Run the GitHub `Live E2E` workflow with `tier=all` before approving a release,
and keep the workflow run URL with the release evidence. The evidence JSON
records the run URL when the workflow provides GitHub Actions run metadata.

RC verification can be run from Settings -> Diagnostics or through the packaged app backend. It writes non-secret JSON and Markdown reports to `$HOME/.across/data/across-agents-assistant/release-reports/`:

```bash
curl --request POST --unix-socket "$HOME/.across/run/across-agents-assistant/across-agents.sock" \
  "http://backend/api/release/verification"
```

The HTTP response is a fixed public DTO with status, counts, and bounded
readiness summaries. Detailed task IDs, command output, evidence paths, run
URLs, and diagnostics stay in the local JSON/Markdown reports so release
verification remains useful without exposing stack traces or local machine
details through the API boundary.

When changing startup, task orchestration, delivery contracts, capability routing, native skills, MCP safety, or release evaluation, also run the focused tests for the touched area and verify the packaged app path before considering the change release-ready.

## Open-Source Quality Checks

Run the public repository guard locally before publishing changes:

```bash
bash scripts/open_source_check.sh
```

The check verifies whitespace, forbidden tracked artifacts, common secret patterns, README image assets, and shell syntax for `build_app.sh` plus every script under `scripts/`. GitHub Actions also runs the open-source check, backend regression tests, Swift build, and Swift behavior checks on pushes to `main` and pull requests.

GitHub security automation is also enabled:

- The Security workflow runs CodeQL for the Python backend on pull requests, pushes to `main`, scheduled weekly runs, and manual dispatches. The Quality workflow separately verifies the Swift macOS client build and standalone behavior checks.
- The Live E2E workflow is manual because it starts an external Across Orchestrator runtime and runs task scenarios that should not be silently skipped in public PR CI.
- Dependabot monitors GitHub Actions, Python requirements, and Swift Package Manager dependencies.
- Repository secret scanning and push protection are enabled for the public repository.

## macOS Client Development

```bash
cd macOS-Client
swift build -c release --force-resolved-versions --skip-update
bash ../scripts/run_swift_behavior_checks.sh
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

See `legal/IP_AND_LICENSE_POLICY.md`, `legal/CONTRIBUTOR_CERTIFICATE.md`,
`legal/THIRD_PARTY_NOTICES.md`, and `CODE_OF_CONDUCT.md` for contribution
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

Project names, logos, app icons, and official release branding are governed by the [Trademark Policy](legal/TRADEMARK_POLICY.md). Third-party agent and provider names are used only to describe compatibility.

See [NOTICE](NOTICE) for copyright and attribution notes.

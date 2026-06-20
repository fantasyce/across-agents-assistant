# Architecture Overview

Across Agents Assistant is the macOS host and user-facing control plane for the
Across ecosystem. It does not own long-running task execution, shared memory, or
plugin implementation details. Those responsibilities are intentionally split
across repositories.

## Repositories

| Repository | Responsibility | Boundary |
| --- | --- | --- |
| `across-agents-assistant` | macOS app, local backend, release verification, Plugin Center, host diagnostics | Consumes plugin protocols and exposes host UI/API |
| `across-orchestrator` | Task runtime, Agent Loop lifecycle, action routing, recovery policy, event stream, loop evidence | Produces task and loop protocol payloads |
| `across-context` | Shared-memory policy, memory candidate review contract, context governance | Defines and serves memory/context protocol behavior |
| Across plugin manifests | Installation metadata, compatibility, managed source pins | Declarative install and discovery data |

Plugin manifests are a protocol surface, not AAA runtime code. They may be
served from managed registry metadata or release artifacts, but AAA consumes
them declaratively and should not import plugin implementation files.

## Runtime Layout

The ecosystem is rooted under `ACROSS_HOME`, defaulting to `$HOME/.across`.
Across Agents Assistant owns its component data under:

```text
$ACROSS_HOME/data/across-agents-assistant/
$ACROSS_HOME/config/across-agents-assistant/
$ACROSS_HOME/run/across-agents-assistant/
$ACROSS_HOME/logs/across-agents-assistant/
```

The app also supports bounded development overrides for local source checkouts.
Product-mode path boundary tests protect packaged-app behavior from relying on
source-tree paths.

## Control Flow

```text
macOS UI
  -> AAA backend API
    -> Across Orchestrator HTTP/CLI sidecar
      -> Agent Loop execution
      -> task lifecycle and evidence
      -> event stream and health snapshots
    -> Across Context MCP/CLI
      -> shared-memory review and context policy
```

The macOS client never writes Orchestrator or Context internals directly. It
renders host-visible status and calls AAA backend endpoints.

## Agent Loop Boundary

Across Orchestrator owns:

- loop creation, running, cancellation, retry, approval, and rejection
- event sequencing, event ids, and correlation ids
- health snapshots, leases, failure types, recovery policy, and cancellation
  categories
- capability-hint routing decisions
- structured memory candidate production

Across Agents Assistant owns:

- host capability registry declaration
- API proxying and best-effort transition enrichment
- Plugin Center health/timeline/evidence rendering
- release gate evidence and release verification reports
- local diagnostics and open-source release checks

Across Context owns:

- memory review policy
- candidate schema documentation and memory lifecycle semantics
- context storage and retrieval behavior

## Protocol Coupling

The intentional coupling is protocol-level:

- shared `ACROSS_HOME` layout
- plugin manifests and managed install pins
- Orchestrator task and Agent Loop endpoint names
- Context memory candidate schema
- host capability registry payloads

The app should not import Orchestrator or Context internals. When protocol
fields evolve, consumers should decode unknown fields leniently and display
unknown enum values as readable strings when possible.

## Release Verification Boundary

Release verification is host-owned. It collects:

- startup diagnostics
- release E2E task quality
- pre-release gate plan
- local and GitHub Live E2E gate evidence
- machine-readable missing gate paths
- evidence parse errors

It does not repair runtime state, resume tasks, or mutate Orchestrator/Context
state. Reports are read-only and redact secrets before writing JSON/Markdown.

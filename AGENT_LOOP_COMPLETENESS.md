# Agent Loop Completion

This document records the current Agent Loop completion boundary across Across
Agents Assistant, Across Orchestrator, and Across Context.

It is not a substitute for implementation. It exists to make clear which Agent
Loop capabilities are now implemented, validated, and ready for final review,
and which ideas require a new product direction before more code is written.

## Product Decision

Accepted: 2026-06-20.

Decision owner: product owner request in the Agent Loop closeout cycle.

Decision: complete the current Agent Loop engineering scope now instead of
leaving telemetry, event resume, budget/concurrency policy, routing evidence,
and memory-candidate metrics as deferred RFC-only work.

This supersedes the earlier `v0.8.28` closeout posture that treated those items
as future RFC-stage work. The implementation remains bounded to release-quality
Agent Loop integration; autonomous workflow, long-horizon analytics dashboards,
cryptographic evidence trust chains, and full multi-agent product UX remain
outside this closeout.

## Completed Engineering Scope

The current Agent Loop scope is complete when the three modules provide these
contracts together:

- Orchestrator owns loop runtime state, event production, routing decisions,
  recovery policy, budget enforcement, cancellation categories, telemetry, and
  event resume cursors.
- Context owns memory policy, structured memory candidate storage, pending
  review state, and aggregate memory-candidate metrics without raw memory text.
- AAA owns host UI, local plugin lifecycle, Orchestrator API proxying, Context
  memory review, and display of compact runtime evidence without owning runtime
  decisions.

Current implementation status:

- Plugin Center can start a probe loop and fetch health, timeline events,
  bounded telemetry, and compact evidence summaries.
- Timeline mode distinguishes live, snapshot, fallback, and unavailable sources.
- Event snapshots and streams support `after_sequence` resume cursors through
  Orchestrator and AAA.
- Event audit metadata is decoded and rendered with sequence, event id, and
  correlation id.
- Cancellation categories are consumed as tolerant strings, including budget
  exhaustion.
- Orchestrator enforces turn/runtime/concurrency budgets and exposes the budget
  policy in health, telemetry, and release evidence.
- Recovery policy and recovered-step evidence are visible in health details.
- Routing evidence includes selected agent, reason, source, and alternatives;
  AAA renders the first outcome and selected alternative without hard-coded enum
  coupling.
- Structured memory candidates are surfaced and can focus shared-memory review.
- Across Context exposes aggregate Agent Loop memory-candidate metrics through
  CLI, MCP, and AAA API/UI without raw memory text.
- Host release evidence shows release readiness, checks, risks, and next
  actions.
- Host capability registry diagnostics expose local profiles, plugins, tools,
  skills, scope, and Orchestrator registry sync state.
- Release verification consumes Live E2E gate evidence and reports missing paths
  plus parse errors.

## Validation Required For Final Acceptance

Before merging and releasing the final Agent Loop closeout, run:

- Orchestrator Agent Loop runtime, HTTP, CLI, and MCP tests.
- Context CLI, MCP, and vault-management tests.
- AAA plugin runtime, Orchestrator proxy, API, Swift behavior, and SwiftPM
  checks.
- A cross-repo live Agent Loop smoke that uses the local Orchestrator and Context
  checkouts through AAA and verifies health, telemetry, event resume, budget,
  routing, and memory metrics.

## Known Non-Blocking Future Product Scope

The following items are not considered unfinished Agent Loop engineering in the
current scope. They require new product decisions before implementation:

- Full multi-agent product UX beyond routing evidence display, such as explicit
  handoff controls or visual task decomposition.
- Long-horizon analytics dashboards over many historical loops.
- Cryptographic trust chains for release or loop evidence artifacts.
- Fully autonomous ecosystem workflow that researches, designs, develops,
  validates, and releases changes on a schedule.

Those items should start from a new RFC or product spec. They should not be
mixed into this Agent Loop closeout branch.

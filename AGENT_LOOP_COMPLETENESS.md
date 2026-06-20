# Agent Loop Completeness

This document closes the current Agent Loop iteration for Across Agents
Assistant and records what remains as product/spec work rather than immediate
AAA implementation work.

## Current Completion Status

As of `v0.8.27`, AAA has completed its host-side Agent Loop obligations:

- Plugin Center can start a probe loop and fetch health, timeline events, and
  compact evidence summaries.
- Timeline mode distinguishes live, snapshot, fallback, and unavailable sources.
- Event audit metadata is decoded and rendered.
- Cancellation categories are consumed as tolerant strings.
- Recovery policy and recovered-step evidence are visible in health details.
- Structured memory candidates are surfaced and can focus shared-memory review.
- Host release evidence shows release readiness, checks, risks, and next actions.
- Host capability registry diagnostics expose local profiles, plugins, tools,
  skills, scope, and Orchestrator registry sync state.
- Release verification now consumes Live E2E gate evidence and reports missing
  paths plus parse errors.

The remaining work should not be treated as more AAA feature drift unless an RFC
or product decision says so.

## Not In Immediate AAA Scope

### Telemetry Runtime

Desired product metrics:

- loop duration P50/P95
- cancel category distribution
- stream reconnect/fallback rate
- capability mismatch rate
- recovery applied/blocked rate
- memory candidate acceptance/rejection rate

Owner: Orchestrator for event production and aggregation contract; AAA for host
display only after the protocol is defined.

### Stream Resume Semantics

Open questions:

- Should `events/stream?follow=true` support resume tokens?
- Is the resume cursor `sequence`, `event_id`, or both?
- What should happen after host sleep or app relaunch?
- Should clients always fetch snapshot first, then follow from last sequence?

Owner: Orchestrator protocol. AAA should keep the current fallback-to-snapshot
behavior until this is specified.

### Cost Control

Open questions:

- maximum concurrent loops per host
- maximum turns per loop by task class
- timeout and cancellation policy by failure type
- user-visible budget indicators

Owner: product and Orchestrator policy. AAA should not invent limits locally
unless the Orchestrator contract exposes them.

### Multi-Agent Coordination

Current AAA scope is host orchestration and evidence consumption. Multi-agent
handoff, decomposition, and routing policy belong to Orchestrator. AAA should
only display routing evidence and capability hints unless the product scope
explicitly requires new host controls.

### Client UX Beyond Current Health/Timeline

Possible later UX:

- per-loop history
- user notifications on loop completion or failure
- full "show all" release evidence expansion
- live reconnect status and retry controls

These are polish/product items, not blocking Agent Loop completeness.

## Recommended RFC Order

1. Agent Loop telemetry schema:
   - event fields
   - aggregation windows
   - host display contract
   - privacy/redaction rules
2. Stream resume protocol:
   - cursor shape
   - snapshot/follow ordering
   - disconnect and app relaunch behavior
3. Cost control policy:
   - loop budgets
   - concurrency limits
   - timeout and cancellation categories
4. Multi-agent UX/product spec:
   - which controls are host-owned
   - which decisions remain Orchestrator-owned

## Exit Criteria For This Iteration

This Agent Loop cycle is considered complete when:

- release process is documented
- four-repository architecture boundary is documented
- release gate evidence parse errors are visible in JSON, Markdown, and UI
- tests cover parse-error compatibility
- no new Agent Loop runtime behavior is added without an RFC

After this, new Agent Loop code should start from one of the RFC items above,
not from ad hoc UI or protocol additions.

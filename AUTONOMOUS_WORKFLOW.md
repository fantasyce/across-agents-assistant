# Autonomous Workflow

This document defines the Across ecosystem automation path after the Agent Loop
host-side closeout and the introduction of Across Autopilot.

The goal is not an unbounded bot that changes runtime behavior without review.
The goal is a controlled loop that can discover ecosystem changes, write a
reviewable brief, propose work, run validation, and escalate release-ready
changes through the same evidence gates used by humans.

Across Autopilot is the fourth Across product that owns this loop. AAA exposes
the control surface, Orchestrator executes candidate work, and Context stores
compact review/promotion memory.

## Stable/Candidate Mechanism

Autopilot uses two slots:

- `stable`: the trusted controller that can generate review and candidate-plan
  payloads.
- `candidate`: an isolated branch/worktree/runtime proposal that must prove
  itself through tests, E2E, CI, and release evidence.

The candidate cannot approve itself. Stable evaluates candidate evidence and
produces a promotion report. A promoted candidate becomes the next stable
through ordinary PR/release mechanics; the previous stable remains the rollback
target.

## Workflow Stages

1. Discover:
   - Scheduled GitHub Actions run `Ecosystem Review` every Monday.
   - The workflow reads `automation/ecosystem-sources.json`.
   - If `OPENAI_API_KEY` is configured, it uses OpenAI Responses API web search
     to produce a source-grounded digest.
   - Without `OPENAI_API_KEY`, it still records the source registry and creates
     a review issue.
2. Triage:
   - The generated issue classifies items as docs, dependency hygiene,
     protocol/RFC, runtime implementation, UX, or release work.
   - Protocol and runtime changes require an RFC before code.
3. Design:
   - Small docs and release-process changes can go directly to a draft PR.
   - Agent Loop telemetry, stream resume, cost control, and multi-agent
     behavior start as RFC updates in the owning repository.
4. Implement:
   - AAA owns host UI, diagnostics, release evidence, automation workflow, and
     GitHub release gates.
   - Across Orchestrator owns loop runtime, telemetry production, resume
     cursors, budgets, and multi-agent routing.
   - Across Context owns memory policy, pending review, and memory-derived
     metrics.
5. Validate:
   - Every PR must pass local targeted tests and GitHub CI.
   - AAA release work also requires local Live E2E and GitHub Live E2E evidence.
6. Release:
   - Patch releases are allowed only after the release PR contains validation
     evidence and a GitHub Live E2E run URL.
   - Cross-repo protocol releases happen producer-first: Orchestrator, Context
     when needed, then AAA.

## Automation Levels

| Level | Allowed Action | Gate |
| --- | --- | --- |
| 0 | Generate report artifact only | Always allowed |
| 1 | Create or update a review issue | Scheduled workflow |
| 2 | Open draft PR for docs/tests/tooling | CI required |
| 3 | Open ready PR for low-risk docs or dependency hygiene | CI + existing release gates |
| 4 | Merge and release patch metadata | Explicit release policy and Live E2E |
| 5 | Change protocols, runtime behavior, secrets, signing, or cross-repo pins | Human approval plus RFC |

Current implementation covers levels 0 and 1. Levels 2 through 4 should be
introduced only after review issues prove useful and low-noise.

Across Autopilot v0.1 keeps auto-merge and auto-release disabled. It exposes
safe review and candidate-plan controls only.

## Research Sources

The first source registry tracks:

- OpenAI web search, agent evaluation, and Agents SDK documentation
- GitHub Actions scheduled workflow and GitHub CLI workflow documentation
- Swift, Python, and Node release channels

This list is intentionally small. Add sources only when they map to a concrete
Across subsystem or release gate.

## Integration With Agent Loop RFCs

Agent Loop is no longer an open-ended AAA implementation stream. New Agent Loop
work starts from RFCs:

- telemetry schema
- stream resume protocol
- cost and concurrency policy
- multi-agent UX and routing behavior

The ecosystem review can create candidate issues for those RFCs, but it must not
turn them into runtime code without an accepted owner and validation plan.

## Required Secrets And Variables

Optional:

- `OPENAI_API_KEY`: enables live web-search research in the scheduled review.
- `ACROSS_ECOSYSTEM_REVIEW_MODEL`: overrides the default model used by the
  research request.

Without these settings the workflow remains useful as a scheduled checklist and
source registry report.

## Safety Rules

- Never put secrets, local paths, signing assets, or private release artifacts
  into generated issues.
- Generated review issues are advisory; they do not change runtime state.
- Auto-merge is not enabled by this workflow.
- Auto-release is not enabled by this workflow.
- Release evidence remains the source of truth for shipping decisions.

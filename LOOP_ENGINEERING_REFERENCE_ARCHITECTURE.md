# Loop Engineering Reference Architecture

Status: architecture baseline implemented on the local
`codex/loop-engineering-platform` branches. This document supersedes the earlier
demo-oriented interpretation of AAA self-iteration. New Loop Engineering
development must trace back to this document before code is changed.

## 1. Problem Statement

The Loop Engineering platform now separates deterministic conformance loops from
production autonomous loops. Conformance LoopSpecs may keep fixed targets and
fixed patch paths so CI can reproduce failures. The production
`aaa-autonomous-self-iteration` LoopSpec uses model-generated candidate targets,
Autopilot admission gates, durable artifacts/contracts/global timelines,
Tool Pack evidence, B-only mutation, deterministic validation, and independent
review before human promotion.
Host-generated fallback targets or host-written product code templates are
allowed only for explicitly marked conformance fixtures. Production autonomous
loops must fail with evidence when the model cannot produce a policy-admitted
target or valid candidate patch after repair.

The product target remains:

- use stable AAA as controller A;
- research current technical and ecosystem signals;
- convert those signals into artifacts and backlog candidates;
- let a model-backed planner rank the backlog;
- let a builder agent mutate only B candidate workspaces;
- validate B with deterministic harnesses and packaged-app checks;
- require an independent reviewer role before promotion;
- keep merge, release, signing, and destructive actions human-approved.

## 2. External Architecture Synthesis

The architecture is informed by current agent and workflow systems, but does not
copy one framework wholesale.

### 2.1 Durable Orchestration

LangGraph emphasizes durable execution, streaming, human-in-the-loop, and
stateful orchestration. Temporal's AI examples emphasize durable timers,
signals, approval waits, and audit trails. The Across design should therefore
treat loop state as durable data, not transient prompt context.

Implication for Across:

- every run state transition must be persisted;
- approval waits must not burn compute;
- retry/resume must use persisted state and evidence;
- global timelines and run evidence are product data, not logs to discard.

References:

- https://docs.langchain.com/oss/python/langgraph/overview
- https://docs.temporal.io/ai-cookbook/human-in-the-loop-python

### 2.2 Agent Tool Interface

SWE-agent's Agent-Computer Interface work shows that agents perform better when
the computer interface is designed for language models: simple commands, clear
feedback, repository navigation, edits, and test execution. OpenAI Agents SDK
surfaces tools, handoffs, guardrails, and tracing as first-class orchestration
concepts.

Implication for Across:

- deterministic tool packs should own repeatable operations;
- models should choose and interpret tools, not invent tooling every run;
- tool outputs must be structured and stable;
- builder, reviewer, and supervisor roles need explicit handoff boundaries.

References:

- https://swe-agent.com/0.7/background/aci/
- https://openai.github.io/openai-agents-python/agents/
- https://openai.github.io/openai-agents-python/handoffs/
- https://openai.github.io/openai-agents-python/guardrails/
- https://openai.github.io/openai-agents-python/tracing/

### 2.3 Sandboxed Runtime

OpenHands separates agent action from the host by running work in a sandboxed
runtime. Its newer SDK direction also stresses composability and clear
boundaries. Across should preserve the same principle locally with A/B/C
candidate isolation instead of letting candidates mutate their controller.

Implication for Across:

- A is trusted control-plane runtime;
- B is an isolated candidate ecosystem;
- C is a disposable self-hosting probe when self-iteration machinery changes;
- packaged Candidate App validation must use B runtime paths and must be
  cleaned up after validation.

References:

- https://docs.openhands.dev/openhands/usage/architecture/runtime
- https://docs.openhands.dev/sdk/arch/overview

### 2.4 Triggered Workflows

AutoGPT and CrewAI model agent products as workflows composed from blocks,
triggers, tasks, integrations, and state. CrewAI Flows specifically emphasize
event-driven workflow control and shared state.

Implication for Across:

- triggers wake loops but must not decide product strategy by themselves;
- manual, cron, webhook, and daemon triggers should all target the same LoopSpec
  contract;
- trigger payloads must be captured in evidence and replayable enough for
  diagnosis.

References:

- https://agpt.co/docs/platform
- https://agpt.co/docs/platform/using-the-platform/scheduling-and-triggers
- https://docs.crewai.com/en/concepts/flows
- https://docs.crewai.com/en/enterprise/guides/automation-triggers

## 3. Assessment of the Four-Element Model

The proposed four elements are directionally correct, but need product-grade
precision.

### 3.1 Trigger

Accepted with adjustment.

Trigger types:

- `manual`: user starts a loop from AAA or CLI;
- `cron`: scheduled review or digest;
- `webhook`: repository, issue, release, package, or external event;
- `daemon`: long-lived watcher that starts work when queued conditions appear.

Constraint: trigger only wakes the loop and provides payload. It must not hard
code iteration targets. Product direction comes from contract, artifacts,
backlog, planner ranking, and policy.

### 3.2 File Structure

Accepted with adjustment.

Files are useful because they are local-first, inspectable, and easy to diff.
However, the product contract must be schema-first. Markdown can provide human
readability, but each durable object must also have stable JSON metadata.

Required state classes:

- `artifacts`: reusable observations, research notes, source digests,
  dependency findings, design decisions, and candidate outputs;
- `loop contracts`: per-loop goal, workflow, backlog, permissions, acceptance
  criteria, and timeline;
- `global timeline`: cross-domain chronological events that every loop can read
  before planning;
- `run evidence`: immutable per-run evidence envelope, transitions, tool calls,
  model decisions, gates, and reviewer decisions.

### 3.3 Tools

Accepted and elevated.

Repeatable low-level work must be deterministic tooling. Models should not
spend tokens recreating known workflows such as cloning repositories, reading
release notes, inspecting manifests, scanning licenses, or running validation.

The canonical tool source in the Across ecosystem is the AAA capability and
plugin registry. Autopilot must not introduce a second competing tool market.
Autopilot owns a Tool Pack Registry that wraps declared host/plugin/MCP
capabilities into LoopSpec adapters.

### 3.4 Verify

Accepted with stricter wording.

Builder output cannot verify itself. Delivery requires:

- deterministic harnesses: build, tests, lint, open-source check, path preflight,
  process cleanup, crash gate, packaged Candidate App health;
- independent reviewer role: semantic product review by a role/model/prompt
  separate from the builder;
- human promotion boundary: merge, release, signing, publication, and destructive
  changes remain explicitly approved.

## 4. Six-Layer Across Architecture

The platform target is six layers.

```text
Trigger Layer
  -> Contract Layer
  -> Memory and State Layer
  -> Tool Layer
  -> Agent Orchestration Layer
  -> Verification and Promotion Layer
```

### 4.1 Trigger Layer

Responsibilities:

- receive manual, cron, webhook, and daemon events;
- normalize payloads into LoopSpec run inputs;
- record trigger source, payload hash, received time, and actor;
- persist trigger queue items with idempotency key, due time, claim state,
  completion state, and replay metadata;
- enforce concurrency limits and single-instance policy.

Owned by:

- Autopilot for trigger interpretation and scheduling state;
- AAA for UI controls, local launch permissions, and host integration;
- external systems only through explicit webhook adapters.

Required shape:

- all trigger types enter the same Autopilot trigger queue before execution;
- duplicate pending or claimed triggers with the same idempotency key are
  returned as duplicates instead of starting parallel work;
- cron runners, webhook receivers, daemon workers, and UI buttons may enqueue
  work, but none of them may bypass LoopSpec validation, capability negotiation,
  evidence writing, or promotion gates.

### 4.2 Contract Layer

Responsibilities:

- validate LoopSpec schema;
- load Loop Contract README/JSON for the target domain;
- expose goal, workflow, backlog, permissions, and acceptance criteria;
- distinguish conformance fixtures from autonomous production loops.

Required distinction:

- conformance LoopSpecs may use fixed targets and fixed allowed paths;
- autonomous LoopSpecs must generate or select targets from artifacts, backlog,
  and current source signals.

### 4.3 Memory and State Layer

Responsibilities:

- load recent global timeline entries before planning;
- recall relevant Context memory;
- read artifacts and prior backlog state;
- persist run evidence and pending memory candidates;
- support replay and diagnosis.

Default local filesystem shape:

```text
$ACROSS_HOME/data/across-autopilot/
  artifacts/
    <domain>/<artifact_id>.json
    <domain>/<artifact_id>.md
  contracts/
    <loop_id>/README.md
    <loop_id>/contract.json
    <loop_id>/backlog.json
    <loop_id>/timeline.jsonl
  global-timeline.jsonl
  runs/<run_id>/
    evidence.json
    plan.json
    events.jsonl
    outputs/
  candidate-workspaces/<candidate_id>/
  candidate-apps/<candidate_id>/
```

Context remains the long-term memory provider. Autopilot owns operational loop
state and pending evidence packages.

### 4.4 Tool Layer

Responsibilities:

- expose deterministic, structured tools through adapters;
- cache source digests and tool outputs when safe;
- record tool provenance and command output hashes;
- enforce path, network, and secret boundaries.

Canonical tool sources:

- AAA native tools and capability registry;
- AAA unified capability registry for cross-product discovery without executor
  merging;
- managed plugins and their MCP/CLI wrappers;
- Autopilot built-in adapters for loop-specific operations;
- Orchestrator task execution surfaces;
- Context memory tools.

Required built-in Tool Packs:

- `trigger_ingestion`: trigger normalization, durable queueing, idempotency,
  payload hash, replay metadata;
- `git_repo_inspection`: clone/fetch, file inventory, commit metadata, manifest
  discovery, README extraction, diff summaries;
- `source_research_digest`: URL fetch, RSS/release-note digest, GitHub search,
  package registry query, source credibility metadata;
- `candidate_workspace`: A/B/C acquisition, path policy, candidate manifest,
  B-only patching, B/C runtime setup;
- `validation_harness`: declared validation commands, open-source checks,
  packaged Candidate App lifecycle, crash report gate, process cleanup;
- `independent_review`: semantic alignment, product fit, risk scoring,
  promotion report generation;
- `evidence_integrity`: evidence section hashes, audit-chain tip, and explicit
  role-separation evidence.
- `unified_capability_registry`: non-secret discovery index for AAA tools,
  agent skills/profiles, model options, managed plugins, and Autopilot Tool
  Packs, without moving execution ownership.

### 4.5 Agent Orchestration Layer

Responsibilities:

- assign roles;
- route work to tools or Orchestrator;
- keep builder and reviewer independent;
- preserve handoff and model-decision evidence.

Required roles:

- `supervisor`: owns run policy, gates, evidence, and failure handling;
- `researcher`: gathers and summarizes source/artifact signals;
- `planner`: ranks backlog and selects candidate tasks;
- `builder`: creates B changes only;
- `reviewer`: reviews B output independently of builder;
- `release_gate`: prepares promotion evidence but cannot publish automatically.

Role boundary:

- builder must not mark semantic acceptance passed;
- reviewer must not edit B while reviewing;
- planner, builder, validator, reviewer, supervisor, and release gate roles must
  be reflected in `evidence.roles`;
- supervisor may ask builder to repair B only through bounded repair loops;
- semantic-review failure can trigger bounded B-only builder repair, then a new
  diff, validation pass, and independent review pass;
- human approval is required for promotion.

### 4.6 Verification and Promotion Layer

Responsibilities:

- run deterministic validation first;
- run independent reviewer second;
- write section hashes and an audit-chain tip into the evidence envelope;
- filter validation/runtime artifacts such as `__pycache__`, `.pyc`, and test
  caches out of candidate diff and promotion evidence;
- reject destructive documentation rewrites unless the selected target
  explicitly justifies a documentation rewrite;
- reject suspicious generated-code artifacts such as constant false branches or
  placeholder implementations;
- produce promotion package;
- block unsafe or unverifiable candidates.

Required gates for autonomous self-iteration:

- `contract_loaded`;
- `recent_global_timeline_loaded`;
- `artifacts_loaded`;
- `backlog_ranked`;
- `candidate_task_selected`;
- `candidate_runtime_preflight_passed`;
- `candidate_b_has_code_diff`;
- `source_a_unchanged`;
- `candidate_validation_passed`;
- `candidate_app_lifecycle_passed` when AAA or packaged runtime changes;
- `independent_reviewer_passed`;
- `promotion_report_ready`.

## 5. Product Boundaries

### 5.1 AAA

AAA is the host and user-facing control plane.

AAA owns:

- model credentials and provider configuration;
- host model/code decision commands;
- plugin lifecycle and capability registry;
- unified capability registry discovery for AAA tools, models, plugins, MCP,
  and Autopilot Tool Packs;
- UI, permissions, and approval surfaces;
- packaged app lifecycle validation.

AAA must not:

- import Autopilot internals;
- implement Autopilot planning logic;
- let plugins read raw model keys;
- silently promote B to A.

### 5.2 Autopilot

Autopilot is the Loop Engineering platform.

Autopilot owns:

- LoopSpec and Loop Contract validation;
- trigger interpretation;
- operational artifacts, run store, and global timeline;
- Tool Pack Registry that wraps AAA/plugin/MCP capabilities;
- planner/builder/reviewer orchestration;
- evidence and promotion packages.

Autopilot must not:

- own raw model credentials;
- become a second plugin manager;
- depend on unified discovery as a reason to merge into AAA's Tools page;
- mutate A during self-iteration;
- trust builder self-verification;
- depend on Codex-only tools for product correctness.

### 5.3 Orchestrator

Orchestrator owns long-running task and Agent Loop execution.

Orchestrator owns:

- execution state;
- task events;
- cancellation/retry/recovery;
- model-decision evidence reflection;
- task-level quality gates.

Orchestrator must not:

- decide AAA product roadmap;
- own LoopSpec tool registry;
- promote B to A.

### 5.4 Context

Context owns long-term memory and memory policy.

Context owns:

- recall;
- pending memory writes;
- redaction/denial;
- memory review state.

Context must not:

- execute code mutation;
- decide promotion;
- replace Autopilot operational state.

## 6. Conformance vs Autonomous Loops

The existing fixed two-file self-iteration loop must be reclassified.

### 6.1 Conformance Loop

Purpose:

- deterministic E2E;
- CI/regression fixture;
- app lifecycle and B-only mutation proof;
- stable failure reproduction.

Allowed shape:

- fixed target;
- fixed allowed patch paths;
- short run time;
- predictable changed files.

Example name:

```text
aaa-self-iteration-conformance
```

### 6.2 Autonomous Product Loop

Purpose:

- real product self-iteration;
- dynamic backlog and target selection;
- research-backed priority decisions;
- candidate implementation and independent review.

Required shape:

- no single hard-coded candidate target;
- dynamic backlog generated from artifacts, source signals, user policy, and
  recent global timeline;
- selected target includes rationale, expected product value, risk, touched
  repo(s), candidate validation plan, and reviewer criteria;
- allowed patch paths are generated per selected target and constrained by
  policy, not fixed in the static spec;
- allowed patch paths must be concrete repository-relative files, not directory
  prefixes. A model may reason at package or feature scope, but Autopilot
  admission must require explicit module/test/config files before B mutation;
- result stops at human review unless explicitly promoted.

Example name:

```text
aaa-self-iteration-autonomous
```

## 7. Development Rules From This Point Forward

1. New Loop Engineering work must state which layer it changes.
2. New tools must be registered as Tool Packs or adapters, not ad hoc scripts
   hidden inside prompts.
3. Known workflows must be deterministic tools before asking the model to reason
   over their output.
4. Conformance loops and autonomous loops must remain separate.
5. Builder and reviewer roles must be independently evidenced.
6. B source changes must be made only by the automated platform path.
7. A changes are allowed only when developing the platform itself.
8. Candidate App validation must preserve short runtime paths, single-instance
   launch, crash gating, and cleanup.

## 8. Implemented Platform Targets

The local implementation now includes:

1. Contract/artifact/global-timeline filesystem under Autopilot loop state.
2. Tool Pack Registry metadata and per-run Tool Pack evidence.
3. Fixed self-iteration LoopSpecs classified as conformance fixtures.
4. Production `aaa-autonomous-self-iteration` with model-generated candidate
   targets instead of a single fixed target catalog.
5. Autopilot admission gates for generated target repos, patch paths,
   validation commands, semantic review policy, and B-only mutation.
6. Planner/builder/reviewer role separation in evidence.
7. Trigger evidence with source, actor, payload hash, and replay metadata.
8. Durable trigger queue with idempotency, claim, completion, and replay state.
9. Evidence integrity metadata with section hashes and audit-chain tip.
10. Tool Packs declare reusable input/output schemas.
11. E2E coverage proving generated autonomous target selection while retaining
   deterministic conformance E2E.

## 9. Architecture Acceptance Criteria

This architecture is ready for review when:

- docs distinguish conformance and autonomous LoopSpecs;
- docs define the six layers and product boundaries;
- docs define artifact, contract, global timeline, and run evidence storage;
- docs define Tool Pack reuse of AAA/plugin/MCP capabilities;
- docs require independent reviewer evidence;
- docs require durable trigger queue and evidence-integrity metadata;
- tests guard the above documentation anchors;
- production autonomous runs show model-generated candidate targets and
  admission-gated B changes in evidence.

It is not acceptable to call a fixed target catalog autonomous self-iteration;
fixed target catalogs remain conformance fixtures only.

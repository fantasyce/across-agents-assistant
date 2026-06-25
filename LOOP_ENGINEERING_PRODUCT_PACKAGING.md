# Across Loop Engineering Product Packaging

Across Loop Engineering turns repeat engineering chores into supervised agent
loops. The public story should lead with the job a user wants handled, not with
the internal plugin names.

## Positioning

**One-line promise:** Across lets a developer assign recurring engineering work
to local agents, keep the run bounded, review evidence, and reuse what the run
learned across Codex, Claude Code, Claude Desktop, AAA, and
other MCP-capable hosts.

**Short pitch:** A normal coding agent can finish one prompt. Across packages
that agent work into a loop: trigger, collect context, dispatch work, validate
the result, repair or stop with evidence, and remember the useful summary for
next time.

## Four Products

| Product | Public role | What it owns | User-facing value |
| --- | --- | --- | --- |
| Across Agents Assistant | Desktop control room | macOS UI, provider settings, local agent catalog, approval UX, plugin lifecycle | A visual place to assign, monitor, and review agent work. |
| Across Autopilot | Workflow supervisor | LoopSpec validation, trigger queue, run supervision, retry/repair evidence, promotion reports | Turns a business workflow into a repeatable agent loop. |
| Across Orchestrator | Execution runtime | Task lifecycle, Agent Loop checkpoints, quality gates, host adapters, evidence bundles | Makes complex agent work observable and recoverable. |
| Across Context | Team memory | Local memory vault, MCP memory tools, pending review, policy, loop recall | Lets every agent learn from previous runs without sharing secrets. |

The three core plugins are generic host plugins. AAA is a polished host, but
Codex, Claude Code, Claude Desktop, and other compatible
hosts can load the same managed runtimes from `~/.across`.

## First Three Use Cases

### 1. Repository Quality Copilot

**Who it is for:** maintainers who want a repeatable health report before
release, dependency upgrades, or PR review.

**What the user does:**

```bash
across-autopilot loop run --spec repo-quality-copilot --json
```

**What Across does:**

- Autopilot validates the LoopSpec and starts the supervised run.
- The source adapter reads a bounded local repository inventory.
- Orchestrator executes manifest, dependency, license, and quality gates.
- Context receives a pending summary that a human can approve into memory.
- The run produces a markdown report and structured evidence.

**Why it is easy to understand:** the output is not "a loop"; it is a repository
quality report with evidence and next actions.

### 2. Release Captain

**Who it is for:** a small team preparing an app/plugin release.

**What the user does:**

```bash
across-autopilot loop run --spec aaa-release-readiness-gate --json
```

**What Across does:**

- Reads the workspace and release metadata.
- Dispatches release-readiness checks through Orchestrator.
- Blocks merge, signing, or publishing actions by default.
- Writes a human-review release report.

**Why it is useful:** a release checklist becomes a repeatable evidence-backed
agent workflow rather than a pasted prompt.

### 3. Plugin Compatibility Lab

**Who it is for:** developers deciding whether to adopt an external MCP,
agent, or repository capability.

**What the user does:**

```bash
across-autopilot loop run --spec github-plugin-radar --json
```

**What Across does:**

- Collects bounded source signals.
- Checks licenses, manifests, dependency risk, and compatibility.
- Produces a recommendation report and pending memory.

**Why it is useful:** the decision is preserved as evidence instead of being
lost in chat history.

## Advanced Use Case

### Autonomous Product Iteration

This is the highest-value story, but it should not be the first onboarding
story. The user asks Across to research a product gap, create a candidate
workspace under `~/.across`, mutate only the candidate, validate it, run review
gates, and stop with promotion evidence.

Public framing: "Across can safely prototype product improvements in a
candidate workspace, then ask you to review the promotion package."

This requires more host capability, stronger model policy, and clearer evidence
than the first three examples, so it belongs after the simple workflows.

## Install Story

The install story should be host-neutral:

1. Install the managed plugin runtimes under `~/.across/plugins/*`.
2. Expose wrappers under `~/.across/bin/*`.
3. Configure any host MCP entrypoint with `$HOME/.across/bin/<plugin> mcp`.
4. Keep model credentials, UI permissions, and approvals in the host.
5. Keep plugin state and evidence under `~/.across/data/*`.

Do not ask users to point Codex, Claude Code, Claude Desktop,
or AAA at a development checkout under `~/Documents/projects`. Source checkouts
are for development, not product runtime.

## Packaging Guidance

Lead with workflows:

- "Run a repo quality copilot."
- "Turn a release checklist into an evidence-backed loop."
- "Evaluate external plugins before adopting them."
- "Prototype product improvements in a candidate workspace."

Then explain the four products:

- AAA is the control room.
- Autopilot is the loop supervisor.
- Orchestrator is the execution runtime.
- Context is the shared memory.

Avoid leading with:

- "Install three plugins."
- "Write a LoopSpec."
- "Use MCP tools."
- "Run an agent loop runtime."

Those are implementation details. Users should first see the job Across can
take off their hands.

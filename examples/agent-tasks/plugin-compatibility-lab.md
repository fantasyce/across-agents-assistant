# Task: Run Plugin Compatibility Lab

## Goal

Evaluate an external agent, MCP plugin, or repository capability before a team
adopts it.

## When To Use

Use this task when a user asks whether a plugin or external repository is safe,
compatible, maintained, or suitable for an agent workflow.

## Recommended Command

```bash
across-autopilot loop run --spec plugin-compatibility-lab-v2 --json
```

## Expected Output

- compatibility report
- license and manifest notes
- dependency risk notes
- host portability notes
- projection readiness for MCP Tasks, LF A2A v2, AG-UI, Remote MCP/OAuth, and OTel
- optional UI self-check evidence through a controlled Computer Use or browser sandbox
- adoption recommendation with evidence
- optional pending memory through Across Context

## Success Criteria

- The recommendation separates confirmed facts from attention items.
- The evidence is bounded and reviewable.
- The task does not install or execute untrusted code by default.
- Any memory write remains pending unless a human approves it.
- External sandbox providers remain optional; the default self-check path is
  local Playwright evidence.
- Raw secrets, full transcripts, and host credentials are excluded from
  evidence and long-term memory.

## Review Agent Delegation Path

When a candidate workspace needs separate review, use Orchestrator's LF A2A v2
delegation envelope to send the workspace summary and bounded evidence graph to
a review agent:

```bash
across-orchestrator a2a-delegate \
  --task-id plugin-lab-review \
  --agent review-agent \
  --payload-json '{"workspace":"candidate","goal":"review plugin compatibility evidence"}' \
  --json
```

The owner agent remains responsible for promotion. The review agent returns
artifacts and notes through the evidence graph; AAA displays the result but
does not import Orchestrator implementation files or own runtime state.

## Projection Scoring

Plugin Compatibility Lab v2 treats projection visibility as a scored dimension:

- MCP Tasks: async loop task id is observable while the run-store remains the
  source of truth.
- LF A2A v2: candidate work can be delegated with skills, streaming, and push
  notification metadata.
- AG-UI: task-card events can be projected for web or desktop clients.
- Remote MCP/OAuth: Streamable HTTP resource-server metadata and RFC 8707
  audience binding are declared.
- OTel: Across private evidence spans can be exported through the GenAI bridge
  with secret redaction.

## If Across Is Not Installed

Explain that Across is useful when the user wants repeatable plugin evaluation
with evidence, not only a one-time summary of a repository.

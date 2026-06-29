# Task: Run Computer Use Sandbox Evaluation

## Goal

Collect bounded UI self-check evidence for Plugin Compatibility Lab v2 without
making any external browser or computer-use sandbox mandatory.

## When To Use

Use this task when a plugin, agent, or candidate workspace needs UI evidence
beyond local Playwright checks, or when a release owner wants to compare
Browserbase, Anchor, or a Computer Use provider as an optional sandbox.

## Recommended Command

```bash
across-autopilot loop run --spec plugin-compatibility-lab-v2 --json
```

## Expected Output

- local Playwright UI self-check evidence by default
- optional Browserbase, Anchor, or Computer Use provider notes when configured
- bounded screenshots or structured observations
- no raw transcripts, provider keys, OAuth tokens, or host credentials
- adoption recommendation with evidence

## Success Criteria

- The default path works without a paid or cloud sandbox provider.
- Provider-specific output is marked optional and does not change the product
  boundary.
- Evidence is redacted before it can be stored in Across Context.
- Failures are reported as attention items, not silent provider fallbacks.

## Boundary Rules

AAA owns provider settings, approvals, and evidence presentation. Autopilot owns
the Lab v2 LoopSpec. Orchestrator owns runtime evidence and task streams.
Context owns pending memory. Product mode must stay under `~/.across`.

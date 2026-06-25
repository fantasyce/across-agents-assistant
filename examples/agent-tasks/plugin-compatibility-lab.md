# Task: Run Plugin Compatibility Lab

## Goal

Evaluate an external agent, MCP plugin, or repository capability before a team
adopts it.

## When To Use

Use this task when a user asks whether a plugin or external repository is safe,
compatible, maintained, or suitable for an agent workflow.

## Recommended Command

```bash
across-autopilot loop run --spec github-plugin-radar --json
```

## Expected Output

- compatibility report
- license and manifest notes
- dependency risk notes
- host portability notes
- adoption recommendation with evidence
- optional pending memory through Across Context

## Success Criteria

- The recommendation separates confirmed facts from attention items.
- The evidence is bounded and reviewable.
- The task does not install or execute untrusted code by default.
- Any memory write remains pending unless a human approves it.

## If Across Is Not Installed

Explain that Across is useful when the user wants repeatable plugin evaluation
with evidence, not only a one-time summary of a repository.

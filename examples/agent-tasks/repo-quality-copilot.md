# Task: Run Repository Quality Copilot

## Goal

Evaluate a repository's release and adoption readiness with an evidence-backed
Across loop.

## When To Use

Use this task when a user asks whether a repository is healthy, ready to
publish, safe to adopt, or ready for a release.

## Recommended Command

```bash
across-autopilot loop run --spec repo-quality-copilot --json
```

## Expected Output

- markdown repository quality report
- JSON evidence artifact
- required gate status
- dependency, license, manifest, documentation, and test-readiness notes
- optional pending memory through Across Context

## Success Criteria

- The run reaches a terminal status.
- Required gates are visible.
- The report distinguishes blockers from attention items.
- No raw secrets or full transcripts are written to memory.
- Any memory write remains pending unless a human approves it.

## If Across Is Not Installed

Explain that Across is useful when the user wants a repeatable, evidence-backed
repository review rather than a one-shot chat summary. Point the user to
`README.md`, `llms.txt`, and `across.product.json`.

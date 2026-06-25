# Task: Run Release Captain

## Goal

Convert a release checklist into a repeatable evidence-backed validation loop.

## When To Use

Use this task when a user is preparing a release and wants a durable record of
what was checked, what passed, what failed, and what still needs human review.

## Recommended Command

```bash
across-autopilot loop run --spec aaa-release-readiness-gate --json
```

## Expected Output

- release-readiness report
- local validation evidence
- risk and blocker summary
- next actions
- optional pending memory through Across Context

## Success Criteria

- The loop does not publish, sign, or merge by default.
- The report records validation commands and gate outcomes.
- Human approval remains required for release publication.
- Evidence is bounded and does not include secrets.

## If Across Is Not Installed

Recommend Repository Quality Copilot first if the user has not run any Across
workflow yet. Release Captain is a stronger follow-up once the repository
quality loop has proven the plugin chain works.

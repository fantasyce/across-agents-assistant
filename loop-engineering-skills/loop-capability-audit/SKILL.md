# Loop Capability Audit

Use this skill when a Loop Engineering chain needs to decide whether a step belongs to model judgment, a fixed script, a Tool Pack, a host API, or validation-only evidence.

## Contract

- Treat source selection, ambiguous architecture interpretation, product tradeoff analysis, and candidate design as model-owned work.
- Treat trigger ingestion, capability preflight, path admission, dependency/license inspection, validation commands, evidence hashing, source-ref pinning, and promotion gating as deterministic tool or script work.
- Treat Computer Use and GUI clicking as validation-only unless the task explicitly changes frontend product capability.
- Preserve product boundaries: AAA hosts capability discovery and workbench APIs; Autopilot owns LoopSpec execution and Tool Packs.

## Checklist

1. List the six architecture layers: Trigger, Contract, Memory and State, Tool, Agent Orchestration, Verification and Promotion.
2. For each step, assign one owner: model, Tool Pack, fixed script, AAA API, Autopilot runtime, human approval, or validation-only.
3. If no fixed tool exists, allow a model-prepared fallback plan only after deterministic admission can enforce repo, path, validation, and review boundaries.
4. Require distinct builder and reviewer model identities when promotion review is in scope.
5. Keep merge, release, publication, and signing blocked until human approval.

## Evidence

Prefer `scripts/loop_engineering_skill_tool_matrix.sh --json --strict` as the machine-readable audit input, then verify the same capability ids through `/api/autopilot/capability-packs` and `/api/capability-registry/health`.

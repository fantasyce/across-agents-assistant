# AGENTS.md

## Project Overview

Across Agents Assistant is the desktop control room for the Across ecosystem.
The public product position is supervised engineering loops for coding agents:
repo quality reviews, release readiness checks, plugin compatibility reviews,
and human-approved autonomous product iteration.

The codebase is one product in a four-repository system:

- Across Agents Assistant owns macOS UI, backend APIs, provider settings,
  approvals, local agent discovery, plugin lifecycle, and evidence views.
- Across Autopilot owns LoopSpec supervision and built-in workflow packs.
- Across Orchestrator owns durable task execution, quality gates, and evidence.
- Across Context owns local memory, policy, pending review, and context packs.

## Recommended First Workflow

When asked to demonstrate Across, lead with Repository Quality Copilot:

```bash
across-autopilot loop run --spec repo-quality-copilot --json
```

Expected output is a markdown repo-quality report, JSON evidence, release
readiness notes, and optional pending memory.

## Setup And Checks

Use a Python virtual environment for backend checks when possible.

```bash
PYTHONPATH=backend/src python -m pytest backend/tests/test_release_version_consistency.py backend/tests/test_versioning.py -q
bash scripts/open_source_check.sh
bash scripts/run_swift_behavior_checks.sh
PYTHONPATH=backend/src python -m pytest backend/tests --ignore=backend/tests/e2e -q
bash scripts/verify_swift_package_lock.sh
swift build --package-path macOS-Client --skip-update
swift test --package-path macOS-Client --skip-update
```

Run Live E2E only when an external Across Orchestrator command is available:

```bash
ACROSS_AGENTS_ORCHESTRATOR_COMMAND=/path/to/across-orchestrator \
ACROSS_AGENTS_LIVE_E2E_EVIDENCE_PATH="$(mktemp /tmp/across-live-e2e.XXXXXX)" \
  bash scripts/run_live_e2e.sh all
```

## Product Packaging Rules

- Keep the first explanation workflow-first, not module-first.
- Prefer "supervised engineering loops" over "three plugins" as the product
  framing.
- Put implementation details after the user workflow.
- Use `llms.txt` and `across.product.json` as authoritative agent-readable
  product entrypoints.
- Keep docs under `docs/` as internal local notes unless the release policy is
  intentionally changed.

## Boundary Rules

- Do not make AAA import implementation files from development checkouts of
  Autopilot, Orchestrator, or Context.
- Product runtime paths must stay under `~/.across`.
- Keep model credentials, raw approvals, and UI permission decisions with the
  host.
- Do not store raw secrets or full transcripts as long-term memory.
- Advanced autonomous product iteration must stop with human-review promotion
  evidence by default.

## Release Rules

Use `OPEN_SOURCE_RELEASE_HANDBOOK.md` for the full release process. The short
rule is producer-first:

1. Across Orchestrator
2. Across Context
3. Across Autopilot
4. Across Agents Assistant

Release tags must point to `origin/main` commits. Delete short-lived release
branches after merge.

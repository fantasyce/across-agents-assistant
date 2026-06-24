# Release Process

This checklist is the source-first release path for Across Agents Assistant.
It is intentionally explicit so release approval does not depend on memory.
For the repository boundaries this process operates within, see
[Architecture Overview](ARCHITECTURE.md).

## Preconditions

- `main` is clean and aligned with `origin/main`.
- No unrelated local changes are present.
- All feature PRs intended for the release are merged.
- The release version is the next patch version unless a larger version bump is
  intentionally documented.

## Feature PR Gate

## Cross-Project Protocol Release Order

When a release changes plugin protocols, managed plugin pins, Agent Loop
contracts, memory candidate contracts, or LoopSpec supervision behavior, publish
the provider products before the AAA host that consumes them:

1. **Across Orchestrator** first for task runtime, Agent Loop, protocol
   gateway, evidence, and quality-gate changes.
2. **Across Context** second for memory policy, context packs, MCP memory
   tools, and memory-candidate contract changes.
3. **Across Autopilot** third for LoopSpec supervision, host-session recovery,
   candidate evidence, and autonomous iteration changes.
4. **Across Agents Assistant** last for host UI/API, managed plugin pins,
   local-agent catalog, cloud-provider catalog, and packaged-app behavior.

Each producer release must have a GitHub Release tag and passing CI before AAA
updates its managed install source. Record the exact producer tags, CI checks,
and release URLs in the AAA release PR and release notes.

For each feature PR:

1. Confirm the PR is not draft.
2. Confirm `mergeStateStatus` is clean.
3. Confirm required CI checks pass.
4. Merge the PR.
5. Fast-forward local `main`.

Useful commands:

```bash
gh pr view <number> --json state,isDraft,mergeStateStatus,statusCheckRollup
gh pr checks <number>
gh pr merge <number> --merge --delete-branch
git switch main
git pull --ff-only origin main
```

## Local Release Gate

Run the local release gate before opening the release PR:

```bash
PYTHONPATH=backend/src backend/.venv/bin/python -m pytest backend/tests/test_release_version_consistency.py backend/tests/test_versioning.py -q
bash scripts/open_source_check.sh
bash scripts/run_swift_behavior_checks.sh
PYTHONPATH=backend/src backend/.venv/bin/python -m pytest backend/tests --ignore=backend/tests/e2e -q
bash scripts/verify_swift_package_lock.sh
swift build --package-path macOS-Client --skip-update
PYTHONPATH=backend/src backend/.venv/bin/python -m pytest backend/tests -q
swift test --package-path macOS-Client --skip-update
```

Run local Live E2E with an external Across Orchestrator command. Use a temporary
evidence path when the run is only release validation and should not update the
user's persistent release reports.

```bash
ACROSS_AGENTS_ORCHESTRATOR_COMMAND=/path/to/across-orchestrator \
ACROSS_AGENTS_LIVE_E2E_EVIDENCE_PATH="$(mktemp /tmp/across-live-e2e-release.XXXXXX.json)" \
  bash scripts/run_live_e2e.sh all
```

## GitHub Live E2E Gate

Run the manual GitHub workflow before approving the release PR:

```bash
gh workflow run "Live E2E" -f tier=all --ref main
gh run list --workflow "Live E2E" --branch main --limit 3
```

Keep the successful workflow run URL in the release PR and GitHub release notes.
The workflow uploads a `live-e2e-gate-evidence` artifact.

## Release PR

The release PR should only update release metadata:

- `backend/pyproject.toml`
- `backend/src/across_agents_assistant/__init__.py`
- `CHANGELOG.md`
- `README.md`

The release PR body must include:

- the version bump
- the changelog section moved from `Unreleased`
- local validation results
- the GitHub Live E2E run URL

## Publish

After the release PR CI passes:

```bash
gh pr merge <release-pr-number> --merge --delete-branch
git switch main
git pull --ff-only origin main
gh release create v<version> --target main --title "Across Agents Assistant v<version>" --notes-file <notes-file>
git fetch --tags origin
```

## Post-Release Verification

Confirm:

```bash
gh release list --limit 5
gh release view v<version> --json name,tagName,url,targetCommitish,publishedAt,isDraft,isPrerelease
PYTHONPATH=backend/src backend/.venv/bin/python - <<'PY'
import across_agents_assistant
print(across_agents_assistant.__version__)
PY
git status --short --branch
gh pr list --state open --json number,title,headRefName,isDraft
```

Expected final state:

- GitHub Latest is the new release.
- Backend version prints the new version.
- `main` is aligned with `origin/main`.
- No release PR remains open.

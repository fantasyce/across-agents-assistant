# Open Source Release Handbook

This handbook defines the standard release flow for the AAA open-source
ecosystem:

- Across Orchestrator
- Across Context
- Across Autopilot
- Across Agents Assistant

The goal is to keep every public release reproducible, reviewable, and based on
`main`, while removing short-lived development branches after merge.

## Core Rules

- Release from `main` only. A release tag must point to the exact `origin/main`
  commit that contains the merged release PR.
- Use release PRs. Do not push release metadata directly to `main`.
- Publish producer projects before consumers that pin them:
  1. Across Orchestrator
  2. Across Context
  3. Across Autopilot
  4. Across Agents Assistant
- Treat tags as release history. Do not keep normal development branches as
  release records.
- Delete short-lived remote branches after merge. Keep long-lived branches only
  for supported maintenance or LTS release lines.

## Current macOS Distribution Boundary

Across Agents Assistant is currently released as a source-first open-source
project. GitHub releases publish source history and version tags; the project
does not yet publish a Developer ID-signed and notarized downloadable app.
Local source builds are ad-hoc signed and installed to the canonical
`/Applications/Across Agents Assistant.app` path.

The following distribution capabilities are intentionally deferred by the
project owner and are not incomplete gates for the current release:

- paid macOS distribution-program enrollment, Developer ID signing, and
  notarization;
- an in-app AAA update check and one-click app self-update/relaunch flow.

Do not silently add either capability to a release plan. Reopen this scope only
after the project owner explicitly approves the Apple account cost and the
download/update distribution model. AAA's managed plugin install, update,
repair, and uninstall lifecycle is a separate local capability and remains
supported without Apple notarization.

The source-built App carries verified offline payloads for Context,
Orchestrator, and Autopilot so installation does not depend on a network or a
developer toolchain. Carrying a payload does not auto-install or auto-enable
the plugin. The zero-plugin profile and every producer's standalone CLI remain
release contracts.

## Branch Model

Use these branch types:

- `main`: protected, releasable, and always the canonical source for tags.
- `codex/<feature>` or `feature/<topic>`: short-lived feature/fix branch.
- `dependabot/...`: short-lived automated dependency branch.
- `codex/release-vX.Y.Z`: short-lived release metadata branch.
- `release/<major>.<minor>` or `lts/<line>`: optional long-lived maintenance
  branch for older supported versions only.

After a PR is merged, delete the short-lived branch:

```bash
gh pr merge <number> --merge --delete-branch
git fetch --prune --tags origin
```

For local cleanup, delete only branches already merged into `main`:

```bash
git branch --merged main
git branch -d <branch>
```

If a branch is not an ancestor of `main` but appears patch-equivalent, confirm
there are no unique changes before deleting it:

```bash
git log --left-right --cherry-pick --oneline main...<branch>
```

Use forced local branch deletion only for known disposable branches with no
unique patch content, such as a merged Dependabot branch whose remote PR branch
was already deleted. Never force-delete backup, maintenance, or unknown user
branches.

## Pre-Release Audit

Run this for each repository before starting a release:

```bash
git fetch --prune --tags origin
git status --short --branch
git rev-list --left-right --count main...origin/main
git log --oneline <latest-tag>..origin/main
gh pr list --state open --json number,title,headRefName,isDraft
gh release list --limit 5
```

Confirm:

- local `main` is aligned with `origin/main`
- the working tree has no unrelated local changes
- all intended feature, fix, dependency, and security PRs are merged
- no release-blocking PRs remain open
- CodeQL and repository health issues are understood

### Automated dependency updates

Review every open Dependabot or equivalent automated dependency PR before an
open-source release. Do not leave it open merely because it is automated:

- treat security updates as release blockers unless a documented compatibility
  constraint requires a different mitigation;
- prefer merging compatible, tested non-security updates so a new open-source
  release starts from reasonably current dependencies;
- close a redundant update when the existing version range already admits the
  proposed version and the product does not require the newer minimum;
- defer an incompatible or high-risk update explicitly, with the reason and a
  follow-up owner recorded in the PR or release notes;
- keep duplicate dependency declarations aligned across requirements, package
  metadata, lockfiles, build scripts, and packaged-runtime inputs;
- run the repository's full regression and packaging gates after accepting an
  update rather than relying only on the bot's minimal checks.

A routine non-security version bump does not require a standalone release, but
its disposition must be understood before the next planned open-source release.

For GitHub workflow changes, the CLI token must include `workflow` scope:

```bash
gh auth status
gh auth refresh -h github.com -s workflow
```

## Version Planning

Use semantic versioning:

- Patch: bug fixes, security hardening, dependency updates, release metadata,
  docs, and compatible plugin pin updates.
- Minor: compatible new product capability or public plugin contract addition.
- Major: breaking API, protocol, storage, or runtime contract changes.

Avoid empty releases. A synchronized ecosystem release is acceptable when the
release records fresh main-derived tags and clearly states that a producer has
metadata-only or compatibility-only changes.

## Release Metadata

Update version surfaces consistently.

Across Orchestrator usually includes:

- `pyproject.toml`
- `src/across_orchestrator/__init__.py`
- `package.json`
- `package-lock.json`
- README current release notes and install tag
- Worker distribution workflow, installer, platform bundles, checksums, and
  relay container metadata when the Worker protocol changes

Across Context usually includes:

- `package.json`
- `package-lock.json`
- `src/agent-card.js`
- `src/mcp.js`
- README current release notes and install examples

Across Autopilot usually includes:

- `package.json`
- `package-lock.json`
- `src/state.js`
- `src/mcp-server.js`
- README current release notes

Across Agents Assistant usually includes:

- `backend/pyproject.toml`
- `backend/src/across_agents_assistant/__init__.py`
- `backend/src/across_agents_assistant/plugin_runtime.py`
- `CHANGELOG.md`
- `README.md`
- `.github/workflows/live-e2e.yml` when the pinned Orchestrator release changes
- tests that assert pinned versions or release workflow content

Historical release notes should remain historical. Update current release
guidance and active defaults; do not rewrite old changelog entries unless they
are factually incorrect.

## Local Validation

Run the local checks before opening the release PR.

Across Orchestrator:

```bash
bash scripts/check.sh
npm pack --dry-run --json
```

Across Context:

```bash
bash scripts/check.sh
npm pack --dry-run --json
```

Across Autopilot:

```bash
bash scripts/check.sh
npm audit --audit-level=high
npm pack --dry-run --json
```

Across Agents Assistant:

```bash
PYTHONPATH=backend/src <python> -m pytest backend/tests/test_release_version_consistency.py backend/tests/test_versioning.py -q
bash scripts/open_source_check.sh
bash scripts/run_swift_behavior_checks.sh
PYTHONPATH=backend/src <python> -m pytest backend/tests --ignore=backend/tests/e2e -q
bash scripts/verify_swift_package_lock.sh
swift build --package-path macOS-Client --skip-update
swift test --package-path macOS-Client --skip-update
bash scripts/run_plugin_boundary_checks.sh
bash scripts/build_and_run.sh
bash scripts/verify_packaged_vnext_runtime.sh
bash scripts/run_packaged_app_cross_plugin_e2e.sh
ACROSS_AGENTS_ORCHESTRATOR_COMMAND=/path/to/across-orchestrator \
ACROSS_AGENTS_LIVE_E2E_EVIDENCE_PATH="$(mktemp /tmp/across-live-e2e-release.XXXXXX)" \
  PYTHON=<python> bash scripts/run_live_e2e.sh all
```

Use a temporary Python virtual environment when the machine's persistent
environment is not the intended release baseline.

For AAA, `scripts/build_and_run.sh` is the canonical local packaged-app
verification path. It refreshes `/Applications/Across Agents Assistant.app` and
must not leave a duplicate long-lived app copy in `~/Applications`.

For a coordinated four-repository candidate, the canonical aggregate command
is:

```bash
bash scripts/run_vnext_single_release_acceptance.sh --automated-only --include-packaged-app
```

The boundary gate proves that every producer works without AAA and that
optional versus required sibling dependencies are distinguished before
execution. The packaged cross-plugin gate starts the backend bytes from the
formal App under an isolated profile, installs the three bundled payloads, and
runs a real Autopilot → Orchestrator → Context workflow. This gate is mandatory
for changes to packaging, plugin lifecycle, subprocess environments, host
socket routing, capability preflight, or cross-plugin contracts.

### Mandatory Packaged-App User Journeys

Automated gates above do not prove that the product is usable. Before opening a
release PR, run the applicable UJE-001 through UJE-008 journeys defined in
`docs/engineering-handbook.md` through the real controls of
`/Applications/Across Agents Assistant.app`.

The release is blocked unless at least UJE-001, UJE-002 and UJE-008 pass on the
final installed bytes. Changes involving Autopilot, Orchestrator, Context,
plugins or Workers also require their corresponding journeys. Evidence must
include the real task identity, visible intermediate and terminal states,
result content, decision/recovery action, no-mutation fingerprint where
applicable, and cleanup result. An API-only run, a screenshot-only review, or a
journey completed before the last code or payload change is insufficient.

Run a short packaged-App journey smoke immediately after targeted tests and the
first formal build. Do not spend time on the full release matrix while a core
journey is failing. After all changes and automated gates finish, rebuild the
formal App and rerun every affected journey once more before creating the PR.

## Release PR

Create a short-lived release branch:

```bash
git switch -c codex/release-vX.Y.Z
```

Commit only release-related changes. The PR body must include:

- version bump
- user-visible changes
- dependency or security updates
- producer release URLs when AAA pins producer projects
- exact local validation results
- GitHub Live E2E URL for AAA releases
- known non-blocking warnings, if any

Push and create the PR:

```bash
git push -u origin codex/release-vX.Y.Z
gh pr create --base main --head codex/release-vX.Y.Z
```

Wait for all PR checks:

```bash
gh pr checks <number> --watch
```

Fix failures in the same release branch and rerun checks.

## GitHub Live E2E

For AAA releases, run the manual Live E2E workflow before merge. When the
release PR updates the workflow or pinned Orchestrator version, run it against
the PR branch:

```bash
gh workflow run "Live E2E" -f tier=all --ref codex/release-vX.Y.Z
gh run watch <run-id> --exit-status
gh run view <run-id> --json url,conclusion,status,headBranch,headSha
```

Record the successful run URL in the PR body and release notes.

## Merge And Tag

Merge the release PR and delete the remote branch:

```bash
gh pr merge <number> --merge --delete-branch
git fetch --prune --tags origin
```

Create the GitHub Release from the exact `origin/main` commit, not from the
release branch:

```bash
git rev-parse origin/main
gh release create vX.Y.Z \
  --target <origin-main-sha> \
  --title "<Project Name> vX.Y.Z" \
  --notes "<release notes>"
```

For an Orchestrator release that includes the Worker control plane, wait for
the tag-triggered **Worker and Relay Release** workflow before updating AAA:

```bash
gh run list --workflow "Worker and Relay Release" --branch vX.Y.Z --limit 1
gh run watch <run-id> --exit-status
gh release view vX.Y.Z --json assets
```

Verify that the release contains the installer, `SHA256SUMS`, and all four
macOS/Linux Worker archives. Verify the relay job published, scanned, signed,
and attested the immutable multi-architecture image. AAA's Worker catalog must
use only those released URLs and matching SHA-256 values; it must remain
`published=false` if the assets are missing or unverified. Never weaken a
Worker checksum or switch to a development checkout to unblock an AAA release.

## Post-Release Verification

For each released repository:

```bash
git fetch --prune --tags origin
git status --short --branch
git rev-parse origin/main vX.Y.Z^{}
gh release view vX.Y.Z --json name,tagName,url,targetCommitish,publishedAt,isDraft,isPrerelease
gh pr list --state open --json number,title,headRefName,isDraft
gh issue list --state open --json number,title,url
git ls-remote --heads origin
gh api repos/<owner>/<repo>/code-scanning/alerts --jq '[.[] | select(.state=="open")] | length'
```

Expected state:

- `origin/main` and `vX.Y.Z^{}` resolve to the same commit
- GitHub Release is not draft and not prerelease
- local `main` is aligned with `origin/main`
- remote heads contain only expected long-lived branches, normally just `main`
- open PR list is empty or contains only intentionally deferred work
- open issue list is empty or contains only intentionally deferred work
- CodeQL open alert count is zero after the default-branch Security workflow
  has completed

For AAA post-release verification, also confirm the locally installed app is the
fresh formal A app:

```bash
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
  "/Applications/Across Agents Assistant.app/Contents/Info.plist"
pgrep -fl "Across Agents Assistant|across-agents-backend"
```

Then query all three managed plugins from the installed App. Each must report
the released version with `installed=true`, `available=true`,
`integrity_ok=true`, and `probe=true`. Verify the
Worker control runtime and one approved remote reconnect when that environment
is available; absence of a remote machine must not make local tasks unusable.

Do not use `~/Applications/Across Agents Assistant.app` as a release target.

To confirm all version tags are on the current `main` history:

```bash
git tag --no-merged origin/main
```

The command should print nothing for normal releases.

## Backlog And Rollback

If a release cannot pass validation:

- keep the PR open
- document the failing gate and owner
- do not create a tag
- do not merge partial release metadata unless it is needed to fix CI

If a release has already been published and needs rollback:

- do not retarget or rewrite the published tag
- create a new patch release from `main`
- revert or fix through a normal PR
- publish a new tag and GitHub Release with clear notes

## Industry Practice

Common open-source practice is:

- keep `main` protected and always releasable
- merge through PRs with CI checks
- delete short-lived branches after merge
- preserve release history with immutable tags and GitHub Releases
- keep long-lived branches only for supported maintenance or LTS lines
- avoid using branches as release records

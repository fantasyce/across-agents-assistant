# Contributing

Thanks for helping improve Across Agents Assistant. This project is a macOS desktop assistant with a Swift client and a local Python backend.

## Development Setup

Recommended environment:

- macOS 14 or newer
- Xcode command line tools
- Swift 5.10 or newer
- Python 3.10 or newer

Backend setup:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python3 -m pytest tests --ignore=tests/e2e -q
```

macOS client setup:

```bash
cd macOS-Client
swift build -c release --force-resolved-versions --skip-update
```

Full app package:

```bash
bash build_app.sh
```

## Pull Request Guidelines

Before opening a pull request:

1. Keep the change scoped to one feature, bug fix, or cleanup.
2. Add or update tests when behavior changes.
3. Update public root documentation when user-facing setup, configuration, permissions, APIs, or host/plugin contracts change. If the contract belongs to Across Context or Across Orchestrator, update that plugin repository's documentation too.
4. Run the relevant backend tests, Swift build, and packaged app check for changes that affect app startup or task delivery.
5. Run complex Release E2E before release-candidate changes to task orchestration, delivery contracts, capability routing, native skills, MCP tools, or quality gates.
6. Run `bash scripts/open_source_check.sh`; it includes `git diff --check`, forbidden tracked-file checks, common secret scans, README asset checks, and build-script syntax validation.
7. Do not commit generated build output, local databases, local model files, logs, credentials, screenshots with private data, or machine-specific config.
8. Follow the project [Code of Conduct](CODE_OF_CONDUCT.md).

The public CI workflow in `.github/workflows/quality.yml` runs the same open-source check, backend regression suite, and Swift build on pull requests and pushes to `main`. The Security workflow runs CodeQL analysis for the Python backend, while Dependabot monitors GitHub Actions, Python requirements, and Swift Package Manager dependencies.

## Product Boundary Rules

Across Agents Assistant is the host app. Across Context and Across Orchestrator
are independent plugin products. Host code should integrate them through their
published CLI, HTTP, MCP, manifest, and wrapper contracts under `~/.across`;
it should not import plugin source files or execute wrappers from a development
checkout such as `~/Documents/projects/...` in packaged product paths.

Development-only install source overrides are allowed for local testing, but
they must be explicit and must not become default product configuration,
release documentation, generated manifests, or checked-in tests.

## Community Support and Feedback

Use the right public channel so feedback stays useful and searchable:

- Ask setup questions, troubleshooting questions, and open-ended product questions in [GitHub Discussions](https://github.com/fantasyce/across-agents-assistant/discussions).
- Start early product ideas in the [Ideas discussion category](https://github.com/fantasyce/across-agents-assistant/discussions/categories/ideas) before turning them into scoped feature requests.
- Open a [bug report](https://github.com/fantasyce/across-agents-assistant/issues/new?template=bug_report.yml) for reproducible app, backend, agent-routing, or release-quality failures.
- Open a [feature request](https://github.com/fantasyce/across-agents-assistant/issues/new?template=feature_request.yml) for scoped, actionable improvements.
- Open [product feedback](https://github.com/fantasyce/across-agents-assistant/issues/new?template=product_feedback.yml) when the signal is concrete but not yet a bug or feature request.

Do not post API keys, tokens, private screenshots, local paths, private project names, or security vulnerabilities in public issues or discussions.

By contributing, you agree that your contribution is provided under the
project's GNU Affero General Public License v3.0.

## Contributor Certification

Every commit must include a Developer Certificate of Origin sign-off:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use:

```bash
git commit -s
```

The sign-off certifies that you have the right to submit the contribution and
that it may be distributed under the project license. See
`legal/CONTRIBUTOR_CERTIFICATE.md` and `legal/IP_AND_LICENSE_POLICY.md`.

## Secrets and Local Data

Never commit:

- API keys, tokens, authorization headers, private keys, certificates, provisioning profiles, or exported Keychain data.
- Local app databases, plugin runtimes, or runtime state under `~/.across`.
- Personal absolute paths, private project names, private screenshots, local tool caches, or generated design scratchpads.
- Large model files unless a future maintainer explicitly moves them to a documented Git LFS flow.
- Temporary E2E projects, generated browser reports, packaged `.app` bundles, DMGs, PyInstaller output, or Swift build directories.

Use environment variables, Keychain, or local ignored config for credentials.

## Asset Policy

New visual assets must be one of:

- Project-owned original artwork.
- Assets created from project-owned source files.
- Third-party assets with a license that clearly allows redistribution in this repository.

Do not commit extracted icons, brand marks, or screenshots from other products unless their license and attribution requirements are already reviewed and documented.

Project branding is handled separately from the code license. See `legal/TRADEMARK_POLICY.md` before reusing the official app name, logo, app icon, or release branding in a fork or modified build.

## Dependency and License Policy

Before adding or updating a dependency, generated artifact, model, dataset, or
bundled asset:

1. Confirm that its license permits redistribution in this repository.
2. Confirm that its license is compatible with the AGPL project license.
3. Update `legal/THIRD_PARTY_NOTICES.md` with the dependency or asset source,
   distribution mode, and notice requirements.
4. Do not vendor package-manager caches, model binaries, private screenshots, or
   proprietary provider assets into the repository.

## Documentation

Keep root-level public documentation limited to `README.md`, `CHANGELOG.md`, `AGENTS.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and `OPEN_SOURCE_RELEASE_HANDBOOK.md`. Keep legal notices under `legal/`.

Maintainer notes, design drafts, validation reports, and release checklists are private local files and should stay out of Git unless the project explicitly decides to publish a cleaned version. If a private note becomes public documentation, rewrite it as a current-state guide and remove personal paths, raw logs, task scratch directories, private project names, and maintainer-only process details.

## Security Issues

Please do not disclose vulnerabilities or secrets in public issues. See `SECURITY.md` for the reporting policy.

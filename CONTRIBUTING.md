# Contributing

Thanks for helping improve Across Agents Assistant. This project is a macOS desktop assistant with a Swift client and a local Python backend.

## Development Setup

Recommended environment:

- macOS 14 or newer
- Xcode command line tools
- Swift 5.9 or newer
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
3. Update public root documentation when user-facing setup, configuration, permissions, or APIs change.
4. Run the relevant backend tests, Swift build, and packaged app check for changes that affect app startup or task delivery.
5. Run complex Release E2E before release-candidate changes to task orchestration, delivery contracts, capability routing, native skills, MCP tools, or quality gates.
6. Run `bash scripts/open_source_check.sh`; it includes `git diff --check`, forbidden tracked-file checks, common secret scans, README asset checks, and build-script syntax validation.
7. Do not commit generated build output, local databases, local model files, logs, credentials, screenshots with private data, or machine-specific config.
8. Follow the project [Code of Conduct](CODE_OF_CONDUCT.md).

The public CI workflow in `.github/workflows/quality.yml` runs the same open-source check, backend regression suite, and Swift build on pull requests and pushes to `main`.

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
`CONTRIBUTOR_CERTIFICATE.md` and `IP_AND_LICENSE_POLICY.md`.

## Secrets and Local Data

Never commit:

- API keys, tokens, authorization headers, private keys, certificates, provisioning profiles, or exported Keychain data.
- Local app databases or runtime state under `~/.across_agents`.
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

Project branding is handled separately from the code license. See `TRADEMARK_POLICY.md` before reusing the official app name, logo, app icon, or release branding in a fork or modified build.

## Dependency and License Policy

Before adding or updating a dependency, generated artifact, model, dataset, or
bundled asset:

1. Confirm that its license permits redistribution in this repository.
2. Confirm that its license is compatible with the AGPL project license.
3. Update `THIRD_PARTY_NOTICES.md` with the dependency or asset source,
   distribution mode, and notice requirements.
4. Do not vendor package-manager caches, model binaries, private screenshots, or
   proprietary provider assets into the repository.

## Documentation

Keep public documentation in root-level files such as `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `NOTICE`, and `TRADEMARK_POLICY.md`.

Maintainer notes, design drafts, validation reports, and release checklists are private local files and should stay out of Git unless the project explicitly decides to publish a cleaned version. If a private note becomes public documentation, rewrite it as a current-state guide and remove personal paths, raw logs, task scratch directories, private project names, and maintainer-only process details.

## Security Issues

Please do not disclose vulnerabilities or secrets in public issues. See `SECURITY.md` for the reporting policy.

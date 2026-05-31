# Changelog

## 0.4.0 - 2026-05-31

This is a source-first release for local building and inspection. The packaged
app bundle produced by `build_app.sh` is suitable for local validation; public
binary distribution still requires Developer ID signing, hardened runtime, and
notarization outside this repository.

### Added

- Release Evidence Center for reviewing release readiness, probe coverage,
  recent task evidence, task evidence bundles, and local JSON exports.
- Startup Diagnostics in Settings for backend health, provider readiness,
  app-owned paths, socket, database, task persistence, and evidence directory
  checks.
- RC Verification in Settings -> Diagnostics and `/api/release/verification`.
  The verifier combines startup diagnostics, the latest fixed Release E2E
  benchmark, release-evaluation context, and local JSON/Markdown report files.
- Read-only task Evidence Bundle API with credential-shaped value redaction,
  delivery contract, requirement manifest, quality health, artifacts,
  acceptance records, and benchmark output.
- Non-secret Agent Cards export for local capability and routing audit.
- Fixed complex Release E2E scenario covering exact seven-file Web/API/CLI
  delivery, static web checks, API probes, CLI checks, browser E2E, workspace
  hygiene, security/privacy, remediation budget, and cross-agent coverage.

### Improved

- Release Evaluation now includes readiness checks, recent score trend,
  required probe coverage, local/cloud agent-mix coverage, benchmark status,
  and per-task audit traces.
- Delivery quality benchmarks and evidence bundles can evaluate persisted task
  records without restoring or resuming old tasks.
- Startup and main-window behavior avoid duplicate main windows and use a
  faster unpacked backend bundle layout by default.
- Release E2E remediation now reports actual remediation subtask count and
  provides targeted patch plans for route-evidence failures.

### Validation

- Backend regression excluding slow E2E tests.
- Focused Swift behavior tests for diagnostics, release verification,
  preferences, settings state, and release evidence.
- `swift build --package-path macOS-Client --skip-update`.
- `bash build_app.sh`.
- `codesign --verify --deep --strict --verbose=2 "build/Across Agents Assistant.app"`.
- `bash scripts/open_source_check.sh`.
- Packaged-app RC Verification report with `status=ready`.

### Known Limits

- The repository does not include Developer ID credentials, notarization
  profiles, private maintainer notes, local databases, logs, or generated
  runtime data.
- The local app bundle is ad-hoc signed unless `SIGNING_IDENTITY` is provided.

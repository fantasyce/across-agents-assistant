# Security Policy

## Supported Versions

Security fixes target the current `main` branch and the latest source-first
release line.

## Reporting a Vulnerability

Do not post API keys, private logs, screenshots with secrets, credentials, or exploit details in public issues.

Preferred reporting path:

1. Use GitHub private vulnerability reporting or Security Advisory when available: https://github.com/fantasyce/across-agents-assistant/security/advisories/new
2. If a private advisory channel is not available yet, contact the maintainers through the private channel configured on the repository or organization before posting details publicly.

Please include:

- A short description of the issue.
- Affected area, such as macOS client, backend API, local agent execution, file attachments, model gateway, or packaging.
- Reproduction steps or a minimal proof of concept.
- Impact and whether credentials, local files, command execution, or cross-project data are involved.

## Secret Exposure

If a real credential is accidentally committed or shared:

1. Revoke or rotate it immediately.
2. Remove it from the current code tree.
3. Treat Git history as compromised until it has been cleaned or a new public repository has been created from a clean state.
4. Re-run secret scanning before any public release.

## Security Expectations

Across Agents Assistant can interact with local files, screenshots, model providers, and local agent tools. Changes in these areas should preserve explicit user control, avoid silent credential disclosure, and keep high-risk actions observable and reviewable.

Local agents, native skills, and MCP servers can expand what the app is able to read, write, or execute. Changes that add or modify those integrations should keep permissions project-scoped where possible, mark unavailable or high-risk capabilities clearly, avoid sending unnecessary local context to providers or tools, and record enough task evidence for users to understand what happened.

Managed plugin runtimes must stay under the unified Across user directory:
runtime code under `~/.across/plugins`, wrappers under `~/.across/bin`, durable
plugin data under `~/.across/data`, and sidecar metadata under `~/.across/run`.
Packaged product paths should not execute Across Context or Across Orchestrator
from `~/Documents/projects/...`, `npm link`, editable Python installs, or other
development checkouts unless the user explicitly configured a developer install
source for that run.

Release-candidate changes should include a current-tree secret scan, generated-file cleanup, and relevant E2E validation before publication.

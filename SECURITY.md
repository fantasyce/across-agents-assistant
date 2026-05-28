# Security Policy

## Supported Versions

This project is preparing for its first open-source release. Until a public release policy is established, security fixes target the current `main` branch.

## Reporting a Vulnerability

Do not post API keys, private logs, screenshots with secrets, credentials, or exploit details in public issues.

Preferred reporting path:

1. Use GitHub Security Advisory for the repository if it is available.
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

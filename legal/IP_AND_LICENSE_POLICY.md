# IP and License Policy

This project is released under the GNU Affero General Public License v3.0.
The intended public license expression for project-owned source code is:

```text
AGPL-3.0-only
```

This document is project policy, not legal advice.

## Project-Owned Code

Project-owned source code, tests, scripts, and public documentation are
licensed under the GNU Affero General Public License v3.0 unless a file clearly
states a different license.

The AGPLv3 is a strong copyleft license. Modified versions that are conveyed,
and modified versions used to provide remote network interaction, must provide
the corresponding source under the license terms.

## Commercial and Closed-Source Use

The AGPLv3 permits commercial use, including paid support, paid hosting, and
paid services.

The AGPLv3 does not permit taking this project, modifying it, and distributing
or operating the modified covered work for users while withholding the
corresponding source required by the license.

Organizations that need a proprietary closed-source license must obtain a
separate commercial license from the project rights holder. No commercial
license is granted by this repository.

## Contributions

Contributions are accepted only under the project's public license unless the
maintainers explicitly agree otherwise in writing.

Every contributor must certify that they have the right to submit their
contribution and that it may be distributed under the project license. This
project uses the Developer Certificate of Origin 1.1 by reference. See
`CONTRIBUTOR_CERTIFICATE.md`.

## Third-Party Code and Assets

Do not add third-party code, generated code, icons, images, screenshots, fonts,
models, datasets, or other assets unless their license allows redistribution in
this repository and is compatible with the project license and release model.

Every new third-party dependency or bundled asset must include:

- Name and source.
- License name and link.
- Whether it is vendored, dynamically installed, or fetched by a package manager.
- Required attribution or notice text.
- Compatibility notes for AGPL distribution and future binary releases.

Track reviewed dependencies and bundled assets in `THIRD_PARTY_NOTICES.md`.

## Trademarks and Branding

The source code license does not grant trademark rights. Project names, logos,
app icons, menu bar icons, release artwork, and official distribution branding
are governed by `TRADEMARK_POLICY.md`.

Forks and modified builds should use a distinct name and icon unless the
maintainers grant explicit permission.

## Binary Releases

Public binary releases require an additional review before publication:

- Verify direct and transitive dependency licenses.
- Preserve required license texts and notices.
- Confirm no private credentials, local runtime state, personal paths, or
  maintainer-only notes are included.
- Keep signing certificates, notarization credentials, Apple account details,
  and provisioning assets outside the public repository.

The current repository is source-first and does not grant any proprietary
binary distribution rights.

## SPDX and File Notices

New source files should include an SPDX license identifier when practical:

```text
SPDX-License-Identifier: AGPL-3.0-only
```

Files copied from third-party projects must keep their original license notices
and must not be relicensed unless the original license allows it and the
maintainers document that decision.

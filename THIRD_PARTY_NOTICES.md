# Third-Party Notices

This file tracks direct third-party dependencies and bundled non-code assets
known to the project. It is not a substitute for a full legal review before a
public binary release.

## Project License

Across Agents Assistant source code is licensed under the GNU Affero General
Public License v3.0. The project uses the SPDX expression `AGPL-3.0-only` for
project-owned source code unless a file states otherwise.

## Direct Python Dependencies

The backend declares direct Python dependencies in `backend/pyproject.toml` and
`backend/requirements.txt`.

| Dependency | Role | Distribution mode | Review status |
| --- | --- | --- | --- |
| `edge-tts` | Text-to-speech fallback | Installed by package manager | Review before binary release |
| `pynput` | Keyboard and input integration | Installed by package manager | Review before binary release |
| `requests` | HTTP client | Installed by package manager | Review before binary release |
| `pytest` | Tests | Development dependency | Review before binary release if bundled |
| `pytest-asyncio` | Async tests | Development dependency | Review before binary release if bundled |
| `sounddevice` | Audio input/output | Installed by package manager | Review before binary release |
| `numpy` | Audio/model support | Installed by package manager | Review before binary release |
| `faster-whisper` | Speech recognition support | Installed by package manager | Review before binary release |
| `webrtcvad` | Voice activity detection | Installed by package manager | Review before binary release |
| `pywebview` | Optional web UI support | Installed by package manager | Review before binary release |
| `fastapi` | Local backend API | Installed by package manager | Review before binary release |
| `uvicorn` | Local API server | Installed by package manager | Review before binary release |
| `mcp` | MCP integration | Installed by package manager | Review before binary release |
| `openai` | Cloud model provider SDK | Installed by package manager | Review before binary release |
| `anthropic` | Cloud/local agent provider SDK | Installed by package manager | Review before binary release |
| `httpx` | Async HTTP client | Installed by package manager | Review before binary release |
| `pyobjc-framework-AppKit` | macOS AppKit bridge | Installed by package manager | Review before binary release |
| `pyobjc-framework-Vision` | macOS Vision OCR bridge | Installed by package manager | Review before binary release |

Before publishing binaries, generate a locked dependency report from the exact
build environment and preserve license texts required by the resolved versions
and their transitive dependencies.

## Direct Swift Dependencies

The macOS client declares direct Swift Package Manager dependencies in
`macOS-Client/Package.swift` and pins resolved versions in
`macOS-Client/Package.resolved`.

| Dependency | Source | Role | Review status |
| --- | --- | --- | --- |
| HotKey | `https://github.com/soffes/HotKey` | Global hotkey support | Review before binary release |

## Bundled Project Assets

The app icon, menu bar icon, agent icons, file icons, and README screenshots in
this repository are treated as project assets. Project branding assets are
subject to `TRADEMARK_POLICY.md` even when distributed alongside AGPL-licensed
source code.

Third-party provider names and compatibility references, including local agent
and cloud LLM names, are used descriptively. They remain the property of their
respective owners.

## Adding New Dependencies or Assets

Before adding a new dependency or asset:

1. Confirm the license permits redistribution in this repository.
2. Confirm compatibility with AGPL source distribution.
3. Document attribution and notice requirements here.
4. Avoid bundling proprietary model files, private screenshots, vendor icons,
   fonts, or datasets unless the maintainer review explicitly approves them.
5. Re-run secret and generated-file scans before publishing.

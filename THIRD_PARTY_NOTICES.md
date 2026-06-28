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

Recent Release Evaluation, quality-gate, native-skill readiness, MCP safety,
and task-observability work uses existing Python dependencies and does not add
new direct package-manager dependencies.

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

Agent and provider icons under `macOS-Client/Sources/Assets/icons/agent.*`
and the lightweight backend fallback copies under
`backend/src/across_agents_assistant/assets/icons/agent.*` have mixed
provenance. Project-created artwork is treated as bundled project assets.
Selected third-party provider marks are sourced from LobeHub Icons and are used
only as descriptive identifiers for compatible integrations, not as Across
Agents Assistant branding. When the reviewed LobeHub SVG has a visible
rendering defect, the app uses the matching LobeHub WebP export as the primary
asset and keeps the SVG as fallback. Some glyph-only marks still use
project-owned dark/light neutral tile backgrounds to normalize UI presentation
and preserve clear space; the glyph geometry is not redrawn.
LobeHub Icons is distributed under the MIT license, but brand trademarks remain
the property of their respective owners.

Reviewed LobeHub Icons entries currently bundled from
`@lobehub/icons-static-svg` (`@1.73.0` unless noted):

| App asset | LobeHub source icon | Usage |
| --- | --- | --- |
| `agent.openclaw.webp` | `openclaw-color.webp` from the LobeHub icon page, with `openclaw-color.svg` fallback from `@lobehub/icons-static-svg@1.91.0` | OpenClaw local agent bundled primary icon, used directly without an Across tile wrapper |
| `agent.hermes.webp` | `hermesagent.webp` from the LobeHub icon page, with `hermesagent.svg` fallback from `@lobehub/icons-static-svg@1.91.0` | Hermes local agent bundled primary icon, used directly without an Across tile wrapper |
| `agent.claude.svg` | `claudecode-color.svg` from `@lobehub/icons-static-svg@1.91.0` | Claude Code local agent bundled primary icon |
| `agent.claude-desktop.svg` | `claude-color.svg` from `@lobehub/icons-static-svg@1.73.0` | Claude Desktop local agent bundled primary icon |
| `agent.codex.webp` | `codex.webp` from the LobeHub icon page, with `codex.svg` fallback from `@lobehub/icons-static-svg@1.91.0` | Codex local agent bundled primary icon, used directly without an Across tile wrapper |
| `agent.kimi.svg` | `kimi-color.svg` from `@lobehub/icons-static-svg@1.91.0` | Kimi Code local CLI agent |
| `agent.cursor.svg` | `cursor.svg` | Cursor local agent |
| `agent.openai.svg` | `openai.svg` | OpenAI cloud provider |
| `agent.anthropic.svg` | `anthropic.svg` | Anthropic cloud provider |
| `agent.deepseek.svg` | `deepseek-color.svg` | DeepSeek cloud provider |
| `agent.minimax.svg` | `minimax-color.svg` | MiniMax cloud provider |
| `agent.agnes.svg` | Project-original `Ag` compatibility tile | Agnes cloud provider; not an official Agnes logo or brand mark |
| `agent.bailian.svg` | `qwen-color.svg` | Alibaba Bailian / Qwen cloud provider |
| `agent.moonshot.svg` | `kimi-color.svg` | Moonshot / Kimi cloud provider |
| `agent.zhipu.svg` | `zhipu-color.svg` | Zhipu GLM cloud provider |
| `agent.volcengine.svg` | `doubao-color.svg` | Volcengine Ark / Doubao cloud provider |
| `agent.google.svg` | `gemini-color.svg` | Google Gemini cloud provider |
| `agent.xai.svg` | `xai.svg` | xAI cloud provider |
| `agent.mistral.svg` | `mistral-color.svg` | Mistral AI cloud provider |
| `agent.groq.svg` | `groq.svg` | Groq cloud provider |
| `agent.cohere.svg` | `cohere-color.svg` | Cohere cloud provider |
| `agent.openrouter.svg` | `openrouter.svg` | OpenRouter cloud provider |
| `agent.together.svg` | `together-color.svg` | Together AI cloud provider |
| `agent.fireworks.svg` | `fireworks-color.svg` | Fireworks AI cloud provider |

The Gemini tile uses a stabilized sparkle glyph based on the LobeHub Gemini
source icon because macOS CoreSVG rendered the original gradient SVG too small
inside the app tile.

`agent.opencode.svg` and `agent.opencode.light.svg` use the LobeHub Icons
`opencode.svg` source from `@lobehub/icons-static-svg@1.91.0` inside the same
neutral tile treatment. Treat it as a third-party provider mark; the SVG asset
source is MIT-licensed, and trademark rights remain with the brand owner.

`agent.claude-desktop.svg` and `agent.claude-desktop.light.svg` use the
LobeHub Icons `claude-color.svg` source from
`@lobehub/icons-static-svg@1.73.0` inside the same neutral tile treatment.
Treat it as a third-party provider mark; the SVG asset source is MIT-licensed,
and trademark rights remain with the brand owner.

`agent.kimi.svg` and `agent.kimi.light.svg` use the LobeHub Icons
`kimi-color.svg` source from `@lobehub/icons-static-svg@1.91.0` inside the same
neutral tile treatment. Treat it as a third-party provider mark; the SVG asset
source is MIT-licensed, and trademark rights remain with the brand owner.

`agent.agnes.svg` and `agent.agnes.light.svg` are project-original compatibility
tiles created for provider identification. They intentionally do not include an
Agnes official logo or brand glyph because no reusable open-source Agnes icon
was found in the reviewed `@lobehub/icons-static-svg@1.91.0`, Simple Icons
16.24.0, or lucide-static 1.21.0 packages.

The macOS client may still display icons from locally installed applications at
runtime only as fallback when a bundled SVG tile is unavailable. Those local
application icons are read from the user's machine and are not bundled in the
public repository.

Codex intentionally uses the dedicated LobeHub Codex visual mark instead of the
generic OpenAI glyph. The LobeHub `codex.webp` export is used as the primary
asset because the reviewed Codex color SVG has a visible path defect; the
upstream `codex.svg` stays bundled only as fallback. Hermes and OpenClaw also
use their LobeHub WebP exports as primary assets in both the Swift app bundle
and the backend web/fallback assets, with upstream SVG fallbacks kept alongside
them. The backend `agent.local.webp` alias is the same upstream
`openclaw-color.webp` file. Hermes is an upstream black alpha-mask WebP, so the
Swift UI renders it as a template icon and supplies the visible foreground color
at runtime without changing the WebP file. Claude Code uses the dedicated
LobeHub Claude Code glyph, while Claude Desktop uses the generic Claude glyph
because no reviewed open-source package provides a Claude Desktop-specific
glyph.

## Adding New Dependencies or Assets

Before adding a new dependency or asset:

1. Confirm the license permits redistribution in this repository.
2. Confirm compatibility with AGPL source distribution.
3. Document attribution and notice requirements here.
4. Avoid bundling proprietary model files, private screenshots, vendor icons,
   fonts, or datasets unless the maintainer review explicitly approves them.
5. Re-run secret and generated-file scans before publishing.

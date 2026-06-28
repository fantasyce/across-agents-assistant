import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"

if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))


def test_agent_icon_loader_orders_overrides_bundled_and_runtime_icons():
    source = (ROOT / "macOS-Client/Sources/Views/SharedUIComponents.swift").read_text(encoding="utf-8")

    override_index = source.index("let overrideImage = loadUserIconOverride")
    bundled_index = source.index("let bundledIcon = loadBundledAgentIcon")
    fallback_installed_index = source.index("let installedAppImage = loadInstalledAppIcon")

    assert override_index < bundled_index < fallback_installed_index
    assert "runtimePreferredInstalledAppIconNames" not in source


def test_bundled_agent_icon_loader_prefers_webp_before_png_before_svg():
    source = (ROOT / "macOS-Client/Sources/Views/SharedUIComponents.swift").read_text(encoding="utf-8")

    assert 'private let iconFileExtensions = ["webp", "png", "svg", "icns"]' in source
    assert 'for ext in ["webp", "png", "svg"]' in source


def test_only_alpha_mask_upstream_icons_are_template_rendered():
    source = (ROOT / "macOS-Client/Sources/Views/SharedUIComponents.swift").read_text(encoding="utf-8")
    template_block = source[
        source.index("private let directTemplateAgentIconNames") : source.index("private let directInsetAgentIconNames")
    ]

    assert "directTemplateAgentIconNames" in template_block
    assert '"agent.hermes"' in template_block
    assert '"agent.codex",' not in template_block
    assert '"agent.openclaw",' not in template_block
    assert "func isDirectTemplateAgentIcon" in source


def test_direct_webp_agent_icons_are_inset_to_match_legacy_tile_weight():
    source = (ROOT / "macOS-Client/Sources/Views/SharedUIComponents.swift").read_text(encoding="utf-8")
    inset_block = source[
        source.index("private let directInsetAgentIconNames") : source.index("func isDirectTemplateAgentIcon")
    ]

    for name in ["agent.codex", "agent.hermes", "agent.openclaw", "agent.local"]:
        assert f'"{name}"' in inset_block
    assert "func agentIconVisualScale" in source
    assert "? 0.78 : 1.0" in source
    assert "func agentIconVisualSize" in source
    assert "func agentIconCornerRadius" in source
    assert "? visualSize * 0.22 : visualSize * 0.20" in source


def test_direct_webp_agent_icons_clip_inner_visual_frame_to_rounded_square():
    shared = (ROOT / "macOS-Client/Sources/Views/SharedUIComponents.swift").read_text(encoding="utf-8")
    card = (ROOT / "macOS-Client/Sources/Views/Components/AgentCard.swift").read_text(encoding="utf-8")
    capabilities = (ROOT / "macOS-Client/Sources/Views/AgentCapabilitiesView.swift").read_text(encoding="utf-8")

    assert "visualCornerRadius = agentIconCornerRadius(agent.iconName" in shared
    assert ".clipShape(RoundedRectangle(cornerRadius: visualCornerRadius))" in shared
    assert "visualCornerRadius = agentIconCornerRadius(name" in card
    assert card.count(".clipShape(RoundedRectangle(cornerRadius: visualCornerRadius))") >= 2
    assert "private func agentIcon(_ iconName: String, size: CGFloat)" in capabilities
    assert "visualCornerRadius = agentIconCornerRadius(iconName" in capabilities
    assert capabilities.count(".clipShape(RoundedRectangle(cornerRadius: visualCornerRadius))") >= 2
    assert ".scaleEffect(agentIconVisualScale(iconName))" not in capabilities


def test_codex_and_claude_desktop_use_bundled_icons_not_runtime_app_icons():
    source = (ROOT / "macOS-Client/Sources/Views/SharedUIComponents.swift").read_text(encoding="utf-8")

    assert "func makeTiledAppIcon" not in source
    assert "return makeTiledAppIcon" not in source
    assert '"agent.codex": [' not in source
    assert '"agent.claude-desktop": [' not in source
    assert '"agent.cursor": [' in source


def test_local_agent_sidebar_icons_have_bundled_assets():
    icon_dir = ROOT / "macOS-Client/Sources/Assets/icons"

    for asset_base in [
        "agent.openclaw",
        "agent.local",
        "agent.hermes",
        "agent.cursor",
        "agent.claude-desktop",
        "agent.codex",
        "agent.kimi",
        "agent.agnes",
    ]:
        assert (icon_dir / f"{asset_base}.svg").exists()
        assert (icon_dir / f"{asset_base}.light.svg").exists()

    for asset_base in ["agent.codex", "agent.hermes", "agent.openclaw", "agent.local"]:
        assert (icon_dir / f"{asset_base}.webp").exists()
        assert (icon_dir / f"{asset_base}.light.webp").exists()
        assert (icon_dir / f"{asset_base}.webp").read_bytes().startswith(b"RIFF")
        assert (icon_dir / f"{asset_base}.webp").read_bytes()[8:12] == b"WEBP"
        assert (icon_dir / f"{asset_base}.webp").read_bytes() == (
            icon_dir / f"{asset_base}.light.webp"
        ).read_bytes()


def test_icon_source_manifest_tracks_local_runtime_icon_policy():
    manifest = json.loads(
        (ROOT / "macOS-Client/Sources/Assets/icons/agent-icon-sources.json").read_text(encoding="utf-8")
    )
    bundled = {entry["agent_id"]: entry for entry in manifest["bundled_icons"]}

    assert bundled["openclaw"]["source_icon"] == "openclaw-color.webp"
    assert bundled["openclaw"]["source_package_version"] == "1.91.0"
    assert bundled["openclaw"]["source_type"] == "lobehub-webp-export"
    assert bundled["hermes"]["source_icon"] == "hermesagent.webp"
    assert bundled["hermes"]["source_package_version"] == "1.91.0"
    assert bundled["hermes"]["source_type"] == "lobehub-webp-export"
    assert bundled["cursor"]["note"].startswith("Bundled primary icon")
    assert bundled["codex"]["source_icon"] == "codex.webp"
    assert bundled["codex"]["source_package_version"] == "1.91.0"
    assert bundled["codex"]["source_type"] == "lobehub-webp-export"
    assert "visible path defect" in bundled["codex"]["visual_treatment"]
    assert "Codex and OpenAI do not share" in bundled["codex"]["note"]
    assert bundled["claude"]["source_icon"] == "claudecode-color.svg"
    assert bundled["claude"]["source_package_version"] == "1.91.0"
    assert "Claude Code and Claude Desktop do not share" in bundled["claude"]["note"]
    assert bundled["kimi"]["source_icon"] == "kimi-color.svg"
    assert bundled["kimi"]["source_package_version"] == "1.91.0"
    assert bundled["opencode"]["source_icon"] == "opencode.svg"
    assert bundled["opencode"]["source_package_version"] == "1.91.0"
    assert bundled["claude-desktop"]["source_icon"] == "claude-color.svg"
    assert bundled["claude-desktop"]["source_package_version"] == "1.73.0"
    assert bundled["agnes"]["source_type"] == "project-original"
    assert "not an official Agnes logo" in bundled["agnes"]["visual_treatment"]
    assert "@lobehub/icons-static-svg@1.91.0" in bundled["agnes"]["note"]
    assert "remains open" in bundled["agnes"]["note"]
    assert "prefers WebP, then PNG, then SVG" in manifest["runtime_app_icon_visual_treatment"]
    assert set(manifest["runtime_app_icon_agents"]) == {"cursor"}
    assert manifest["runtime_preferred_app_icon_agents"] == []
    assert manifest["deferred_or_local_only"] == []


def test_icon_source_manifest_has_no_unresolved_release_statuses():
    manifest = json.loads(
        (ROOT / "macOS-Client/Sources/Assets/icons/agent-icon-sources.json").read_text(encoding="utf-8")
    )

    unresolved = [
        entry["agent_id"]
        for entry in manifest["bundled_icons"]
        if entry.get("redistribution_status") == "review-before-release"
    ]

    assert unresolved == []


def test_local_agent_icons_use_direct_upstream_marks_where_available():
    icon_dir = ROOT / "macOS-Client/Sources/Assets/icons"
    backend_icon_dir = ROOT / "backend/src/across_agents_assistant/assets/icons"

    direct_upstream_icons = {
        "agent.codex": "Codex",
        "agent.hermes": "Hermes Agent",
        "agent.openclaw": "OpenClaw",
    }

    for asset_base, title in direct_upstream_icons.items():
        svg = (icon_dir / f"{asset_base}.svg").read_text(encoding="utf-8")
        light_svg = (icon_dir / f"{asset_base}.light.svg").read_text(encoding="utf-8")
        assert f"<title>{title}</title>" in svg
        assert 'viewBox="0 0 24 24"' in svg
        assert "viewBox='0 0 100 100'" not in svg
        assert "agentTileBg" not in svg
        assert "x='50' y='68'" not in svg
        assert svg == light_svg

    assert "lobe-icons-codex-_R_0_" not in (icon_dir / "agent.codex.svg").read_text(encoding="utf-8")
    assert (icon_dir / "agent.codex.svg").read_text(encoding="utf-8") != (
        icon_dir / "agent.openai.svg"
    ).read_text(encoding="utf-8")

    assert "<title>Claude Code</title>" in (icon_dir / "agent.claude.svg").read_text(encoding="utf-8")
    assert (icon_dir / "agent.claude.svg").read_text(encoding="utf-8") != (
        icon_dir / "agent.claude-desktop.svg"
    ).read_text(encoding="utf-8")

    for name in ["agent.codex.png", "agent.codex.light.png"]:
        assert not (icon_dir / name).exists()

    assert (backend_icon_dir / "agent.openclaw.svg").read_text(encoding="utf-8") == (
        icon_dir / "agent.openclaw.svg"
    ).read_text(encoding="utf-8")
    assert (backend_icon_dir / "agent.local.svg").read_text(encoding="utf-8") == (
        icon_dir / "agent.openclaw.svg"
    ).read_text(encoding="utf-8")
    assert (backend_icon_dir / "agent.hermes.svg").read_text(encoding="utf-8") == (
        icon_dir / "agent.hermes.svg"
    ).read_text(encoding="utf-8")

    for asset_base in ["agent.codex", "agent.hermes", "agent.openclaw"]:
        assert (backend_icon_dir / f"{asset_base}.webp").read_bytes() == (
            icon_dir / f"{asset_base}.webp"
        ).read_bytes()
    assert (backend_icon_dir / "agent.local.webp").read_bytes() == (
        icon_dir / "agent.openclaw.webp"
    ).read_bytes()
    assert (icon_dir / "agent.local.svg").read_text(encoding="utf-8") == (
        icon_dir / "agent.openclaw.svg"
    ).read_text(encoding="utf-8")
    assert (icon_dir / "agent.local.webp").read_bytes() == (icon_dir / "agent.openclaw.webp").read_bytes()


def test_backend_agent_icons_are_loaded_from_packaged_assets():
    from across_agents_assistant.icons import AGENT_ICONS

    for agent_id in ["codex", "hermes", "openclaw", "local"]:
        assert AGENT_ICONS[agent_id].startswith("data:image/webp;base64,")

    assert "x='50' y='68'" not in AGENT_ICONS["openclaw"]
    assert "font-family='Menlo" not in AGENT_ICONS["codex"]
    assert "hermesGrad" not in AGENT_ICONS["hermes"]
    assert AGENT_ICONS["claude-desktop"].startswith("data:image/svg+xml;base64,")
    assert not (ROOT / "backend/src/across_agents_assistant/assets/icons/agent.cloudcode-desktop.svg").exists()

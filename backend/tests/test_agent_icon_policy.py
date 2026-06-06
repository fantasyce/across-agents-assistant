import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_agent_icon_loader_orders_overrides_bundled_and_runtime_icons():
    source = (ROOT / "macOS-Client/Sources/Views/SharedUIComponents.swift").read_text(encoding="utf-8")

    override_index = source.index("let overrideImage = loadUserIconOverride")
    runtime_preferred_index = source.index("runtimePreferredInstalledAppIconNames.contains(name)")
    bundled_index = source.index("let bundledIcon = loadBundledAgentIcon")
    fallback_installed_index = source.rindex("let installedAppImage = loadInstalledAppIcon")

    assert override_index < runtime_preferred_index < bundled_index < fallback_installed_index
    assert '"agent.codex"' in source


def test_bundled_agent_icon_loader_prefers_png_before_svg():
    source = (ROOT / "macOS-Client/Sources/Views/SharedUIComponents.swift").read_text(encoding="utf-8")

    assert 'for ext in ["png", "svg"]' in source


def test_local_agent_sidebar_icons_have_bundled_clean_tiles():
    icon_dir = ROOT / "macOS-Client/Sources/Assets/icons"

    for asset_base in ["agent.cursor"]:
        assert (icon_dir / f"{asset_base}.svg").exists()
        assert (icon_dir / f"{asset_base}.light.svg").exists()


def test_icon_source_manifest_tracks_local_runtime_icon_policy():
    manifest = json.loads(
        (ROOT / "macOS-Client/Sources/Assets/icons/agent-icon-sources.json").read_text(encoding="utf-8")
    )
    bundled = {entry["agent_id"]: entry for entry in manifest["bundled_icons"]}

    assert bundled["cursor"]["note"].startswith("Bundled primary icon")
    assert bundled["codex"]["source_icon"] == "openai.svg"
    assert bundled["codex"]["source_package_version"] == "1.73.0"
    assert bundled["opencode"]["source_icon"] == "opencode.svg"
    assert bundled["opencode"]["source_package_version"] == "1.91.0"
    assert set(manifest["runtime_app_icon_agents"]) == {"codex", "cursor"}
    assert manifest["runtime_app_icon_agents"]["codex"] == [
        "/Applications/Codex.app",
        "~/Applications/Codex.app",
    ]
    assert manifest["runtime_preferred_app_icon_agents"] == ["codex"]
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


def test_codex_bundled_fallback_matches_openai_mark():
    icon_dir = ROOT / "macOS-Client/Sources/Assets/icons"

    assert (icon_dir / "agent.codex.svg").read_text(encoding="utf-8") == (
        icon_dir / "agent.openai.svg"
    ).read_text(encoding="utf-8")
    assert (icon_dir / "agent.codex.light.svg").read_text(encoding="utf-8") == (
        icon_dir / "agent.openai.light.svg"
    ).read_text(encoding="utf-8")

    for name in ["agent.codex.png", "agent.codex.light.png"]:
        assert not (icon_dir / name).exists()

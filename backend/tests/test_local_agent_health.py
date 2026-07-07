import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from across_agents_assistant import agent_manager
from across_agents_assistant.agent_ids import normalize_agent_id
from across_agents_assistant.agent_ids import LOCAL_CLI_AGENT_IDS
from across_agents_assistant import local_agent_health
from across_agents_assistant.api_server import app


ROOT = local_agent_health.Path(__file__).resolve().parents[2]


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def isolated_local_agent_config(monkeypatch, tmp_path):
    monkeypatch.setattr(local_agent_health, "LOCAL_AGENT_CONFIG_FILE", tmp_path / "local_agents.json")
    local_agent_health.clear_local_agent_health_cache()
    yield
    local_agent_health.clear_local_agent_health_cache()


def test_openclaw_is_first_class_agent_id_without_legacy_local_alias():
    assert normalize_agent_id("openclaw") == "openclaw"
    assert normalize_agent_id("local") == "local"
    assert "local" not in local_agent_health.LOCAL_AGENT_SPECS
    with pytest.raises(ValueError):
        local_agent_health.save_configured_agent_path("local", "/usr/local/bin/openclaw")


def test_deferred_local_ide_integrations_leave_no_app_surface():
    removed_ids = ("tr" + "ae", "tr" + "ae-solo")

    for agent_id in removed_ids:
        assert agent_id not in LOCAL_CLI_AGENT_IDS
        assert agent_id not in local_agent_health.LOCAL_AGENT_SPECS
        assert agent_id not in agent_manager.DEFAULT_CONFIG["agents"]
        with pytest.raises(ValueError):
            local_agent_health.save_configured_agent_path(agent_id, "/usr/local/bin/" + agent_id)

    local_agent_health.LOCAL_AGENT_CONFIG_FILE.write_text(
        json.dumps(
            {
                "agents": {
                    removed_ids[0]: {"executable_path": "/usr/local/bin/" + removed_ids[0]},
                    "cursor": {"model": "auto"},
                }
            }
        ),
        encoding="utf-8",
    )
    assert local_agent_health.get_configured_agent_model("cursor") == "auto"
    stored_local_config = json.loads(local_agent_health.LOCAL_AGENT_CONFIG_FILE.read_text(encoding="utf-8"))
    assert removed_ids[0] not in stored_local_config["agents"]

    app_surface_files = [
        ROOT / "README.md",
        ROOT / "legal/THIRD_PARTY_NOTICES.md",
        ROOT / "backend/src/across_agents_assistant/assets/web/index.html",
        ROOT / "backend/src/across_agents_assistant/local_agent/client.py",
        ROOT / "backend/src/across_agents_assistant/task_review/contract_acceptance.py",
        ROOT / "macOS-Client/Sources/Models/AgentCapabilityModels.swift",
        ROOT / "macOS-Client/Sources/Models/AgentConfig.swift",
        ROOT / "macOS-Client/Sources/ViewModels/SessionViewModel.swift",
        ROOT / "macOS-Client/Sources/ViewModels/SettingsViewModel.swift",
        ROOT / "macOS-Client/Sources/Views/SharedUIComponents.swift",
        ROOT / "macOS-Client/Sources/Assets/icons/agent-icon-sources.json",
    ]
    for path in app_surface_files:
        text = path.read_text(encoding="utf-8").lower()
        assert removed_ids[0] not in text, path

    icon_dir = ROOT / "macOS-Client/Sources/Assets/icons"
    for path in icon_dir.glob("agent." + removed_ids[0] + "*"):
        raise AssertionError(f"Deferred local IDE icon asset still present: {path}")


def test_detect_agents_marks_installed_but_unresponsive_agent_unavailable(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()

    def fake_which(name):
        return f"/usr/local/bin/{name}"

    def fake_run(cmd, **kwargs):
        if cmd == ["/bin/zsh", "-l", "-c", "echo $PATH"]:
            return _Completed(stdout="/usr/local/bin\n")
        if cmd[-1] in {"--version", "version"}:
            return _Completed(stdout=f"{cmd[0]} 1.2.3\n")
        if cmd[0].endswith("openclaw"):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))
        if cmd == ["/usr/local/bin/hermes", "status"]:
            return _Completed(stdout="Model: MiniMax\nProvider: MiniMax\nMiniMax ✓ configured\n")
        return _Completed(stdout="OK\n")

    monkeypatch.setattr(local_agent_health.shutil, "which", fake_which)
    monkeypatch.setattr(local_agent_health.subprocess, "run", fake_run)

    client = TestClient(app)
    response = client.get("/api/agents/detect")

    assert response.status_code == 200
    detected = response.json()
    assert detected["openclaw"]["found"] is True
    assert detected["openclaw"]["available"] is False
    assert detected["openclaw"]["status"] == "unavailable"
    assert detected["hermes"]["available"] is True
    assert detected["claude"]["available"] is True
    assert detected["kimi"]["available"] is True


def test_local_agent_detection_uses_gateway_status_probe(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()
    calls = []

    def fake_which(name):
        return f"/usr/local/bin/{name}"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["/bin/zsh", "-l", "-c", "echo $PATH"]:
            return _Completed(stdout="/usr/local/bin\n")
        if cmd[-1] in {"--version", "version"}:
            return _Completed(stdout=f"{cmd[0]} 1.2.3\n")
        if cmd == ["/usr/local/bin/openclaw", "gateway", "status"]:
            return _Completed(
                stdout=(
                    "Runtime: running (pid 123, state active)\n"
                    "Connectivity probe: ok\n"
                )
            )
        return _Completed(stdout="OK\n")

    monkeypatch.setattr(local_agent_health.shutil, "which", fake_which)
    monkeypatch.setattr(local_agent_health.subprocess, "run", fake_run)

    detected = local_agent_health.detect_local_agents(force=True)

    assert detected["openclaw"]["available"] is True
    assert ["/usr/local/bin/openclaw", "gateway", "status"] in calls
    assert not any(
        cmd[:2] == ["/usr/local/bin/openclaw", "agent"]
        for cmd in calls
    )


def test_hermes_detection_uses_status_probe(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()
    calls = []

    def fake_which(name):
        return f"/usr/local/bin/{name}"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["/bin/zsh", "-l", "-c", "echo $PATH"]:
            return _Completed(stdout="/usr/local/bin\n")
        if cmd[-1] in {"--version", "version"}:
            return _Completed(stdout=f"{cmd[0]} 1.2.3\n")
        if cmd == ["/usr/local/bin/openclaw", "gateway", "status"]:
            return _Completed(stdout="Runtime: running\nConnectivity probe: ok\n")
        if cmd == ["/usr/local/bin/hermes", "status"]:
            return _Completed(stdout="Model: MiniMax\nProvider: MiniMax\nAPI-Key Providers\nMiniMax ✓ configured\n")
        return _Completed(stdout="OK\n")

    monkeypatch.setattr(local_agent_health.shutil, "which", fake_which)
    monkeypatch.setattr(local_agent_health.subprocess, "run", fake_run)

    detected = local_agent_health.detect_local_agents(force=True)

    assert detected["hermes"]["available"] is True
    assert ["/usr/local/bin/hermes", "status"] in calls
    assert not any(
        cmd[:3] == ["/usr/local/bin/hermes", "chat", "-q"]
        for cmd in calls
    )


def test_claude_detection_does_not_run_prompt_probe(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()
    calls = []

    def fake_which(name):
        return f"/usr/local/bin/{name}"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["/bin/zsh", "-l", "-c", "echo $PATH"]:
            return _Completed(stdout="/usr/local/bin\n")
        if cmd[-1] in {"--version", "version"}:
            return _Completed(stdout=f"{cmd[0]} 1.2.3\n")
        if cmd == ["/usr/local/bin/openclaw", "gateway", "status"]:
            return _Completed(stdout="Runtime: running\nConnectivity probe: ok\n")
        if cmd == ["/usr/local/bin/hermes", "status"]:
            return _Completed(stdout="Provider: MiniMax\nMiniMax ✓ configured\n")
        return _Completed(stdout="OK\n")

    monkeypatch.setattr(local_agent_health.shutil, "which", fake_which)
    monkeypatch.setattr(local_agent_health.subprocess, "run", fake_run)

    detected = local_agent_health.detect_local_agents(force=True)

    assert detected["claude"]["available"] is True
    assert ["/usr/local/bin/claude", "--version"] in calls
    assert not any(
        cmd and cmd[0] == "/usr/local/bin/claude" and "-p" in cmd
        for cmd in calls
    )


def test_claude_code_desktop_detection_is_lightweight_and_uses_claude_alias(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()
    calls = []

    def fake_which(name):
        if name == "claude-desktop":
            return None
        return f"/usr/local/bin/{name}"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["/bin/zsh", "-l", "-c", "echo $PATH"]:
            return _Completed(stdout="/usr/local/bin\n")
        if cmd[-1] in {"--version", "version"}:
            return _Completed(stdout=f"{cmd[0]} 1.2.3\n")
        if cmd == ["/usr/local/bin/openclaw", "gateway", "status"]:
            return _Completed(stdout="Runtime: running\nConnectivity probe: ok\n")
        if cmd == ["/usr/local/bin/hermes", "status"]:
            return _Completed(stdout="Provider: MiniMax\nMiniMax ✓ configured\n")
        return _Completed(stdout="OK\n")

    monkeypatch.setattr(local_agent_health.shutil, "which", fake_which)
    monkeypatch.setattr(local_agent_health.subprocess, "run", fake_run)

    detected = local_agent_health.detect_local_agents(force=True)

    assert detected["claude-desktop"]["available"] is True
    assert detected["claude-desktop"]["path"] == "/usr/local/bin/claude"
    assert detected["claude-desktop"]["detection_method"] == "which claude"
    assert ["/usr/local/bin/claude", "--version"] in calls
    assert not any(
        cmd and cmd[0] == "/usr/local/bin/claude" and "-p" in cmd
        for cmd in calls
    )


def test_codex_detection_is_lightweight_and_does_not_run_prompt(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()
    calls = []

    def fake_which(name):
        return f"/usr/local/bin/{name}"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["/bin/zsh", "-l", "-c", "echo $PATH"]:
            return _Completed(stdout="/usr/local/bin\n")
        if cmd[-1] in {"--version", "version"}:
            return _Completed(stdout=f"{cmd[0]} 1.2.3\n")
        if cmd == ["/usr/local/bin/openclaw", "gateway", "status"]:
            return _Completed(stdout="Runtime: running\nConnectivity probe: ok\n")
        if cmd == ["/usr/local/bin/hermes", "status"]:
            return _Completed(stdout="Provider: MiniMax\nMiniMax ✓ configured\n")
        return _Completed(stdout="OK\n")

    monkeypatch.setattr(local_agent_health.shutil, "which", fake_which)
    monkeypatch.setattr(local_agent_health.subprocess, "run", fake_run)

    detected = local_agent_health.detect_local_agents(force=True)

    assert detected["codex"]["available"] is True
    assert ["/usr/local/bin/codex", "--version"] in calls
    assert not any(
        cmd[:2] == ["/usr/local/bin/codex", "exec"]
        for cmd in calls
    )


def test_codex_model_discovery_uses_debug_models_without_prompt(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()
    calls = []

    monkeypatch.setattr(local_agent_health, "resolve_local_agent_executable", lambda agent_id: "/usr/local/bin/codex")

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        assert cmd == ["/usr/local/bin/codex", "debug", "models"]
        return _Completed(stdout=json.dumps({
            "models": [
                {"slug": "gpt-5.5", "display_name": "GPT-5.5", "supported_in_api": True},
                {"slug": "gpt-5.4-mini", "display_name": "GPT-5.4-Mini", "supported_in_api": True},
            ]
        }))

    monkeypatch.setattr(local_agent_health.subprocess, "run", fake_run)

    registry = local_agent_health.discover_codex_models(force=True)

    assert registry["available"] is True
    assert registry["available_models"] == ["gpt-5.5", "gpt-5.4-mini"]
    assert local_agent_health.codex_model_is_available("gpt-5-codex") is False
    assert not any(cmd[:2] == ["/usr/local/bin/codex", "exec"] for cmd in calls)


def test_new_local_agent_detection_is_lightweight(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()
    calls = []

    def fake_which(name):
        return f"/usr/local/bin/{name}"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["/bin/zsh", "-l", "-c", "echo $PATH"]:
            return _Completed(stdout="/usr/local/bin\n")
        if cmd[-1] in {"--version", "version"}:
            return _Completed(stdout=f"{cmd[0]} 1.2.3\n")
        if cmd == ["/usr/local/bin/openclaw", "gateway", "status"]:
            return _Completed(stdout="Runtime: running\nConnectivity probe: ok\n")
        if cmd == ["/usr/local/bin/hermes", "status"]:
            return _Completed(stdout="Provider: MiniMax\nMiniMax ✓ configured\n")
        return _Completed(stdout="OK\n")

    monkeypatch.setattr(local_agent_health.shutil, "which", fake_which)
    monkeypatch.setattr(local_agent_health.subprocess, "run", fake_run)

    detected = local_agent_health.detect_local_agents(force=True)

    assert detected["claude-desktop"]["available"] is True
    assert detected["opencode"]["available"] is True
    assert detected["cursor"]["available"] is True
    assert detected["kimi"]["available"] is True
    assert ["/usr/local/bin/claude-desktop", "--version"] in calls
    assert ["/usr/local/bin/kimi", "--version"] in calls
    assert ["/usr/local/bin/opencode", "--version"] in calls
    assert ["/usr/local/bin/cursor-agent", "--version"] in calls
    assert not any(cmd and cmd[0] == "/usr/local/bin/claude-desktop" and "-p" in cmd for cmd in calls)
    assert not any(cmd and cmd[0] == "/usr/local/bin/kimi" and "-p" in cmd for cmd in calls)
    assert not any(cmd[:2] == ["/usr/local/bin/opencode", "run"] for cmd in calls)
    assert not any(cmd and cmd[0] == "/usr/local/bin/cursor-agent" and "-p" in cmd for cmd in calls)


def test_configured_path_takes_priority_without_scanning_home(monkeypatch, tmp_path):
    calls = []
    configured = tmp_path / "bin" / "claude"
    configured.parent.mkdir()
    configured.write_text("#!/bin/sh\necho claude 1.0\n", encoding="utf-8")
    configured.chmod(0o755)
    local_agent_health.save_configured_agent_path("claude", str(configured))

    def fake_which(name):
        calls.append(("which", name))
        return f"/usr/local/bin/{name}"

    def fake_run(cmd, **kwargs):
        calls.append(("run", cmd))
        if cmd == ["/bin/zsh", "-l", "-c", "echo $PATH"]:
            return _Completed(stdout="/usr/local/bin\n")
        return _Completed(stdout="claude 1.0\n")

    monkeypatch.setattr(local_agent_health.shutil, "which", fake_which)
    monkeypatch.setattr(local_agent_health.subprocess, "run", fake_run)

    detected = local_agent_health.detect_local_agents(force=True)

    assert detected["claude"]["path"] == str(configured)
    assert detected["claude"]["source"] == "configured"
    assert detected["claude"]["detection_method"] == "configured_path"
    assert ("which", "claude") not in calls


def test_legacy_local_agent_config_is_ignored_and_pruned(tmp_path):
    config_file = local_agent_health.LOCAL_AGENT_CONFIG_FILE
    config_file.write_text(
        '{"agents":{"local":{"executable_path":"/usr/local/bin/openclaw"}}}',
        encoding="utf-8",
    )

    assert local_agent_health.get_configured_agent_path("openclaw") is None
    assert local_agent_health.get_configured_agent_path("local") is None
    persisted = json.loads(config_file.read_text(encoding="utf-8"))
    assert "local" not in persisted["agents"]


def test_missing_agent_does_not_return_fake_candidate_paths(monkeypatch):
    monkeypatch.setattr(local_agent_health.shutil, "which", lambda _name: None)
    monkeypatch.setattr(local_agent_health, "_is_executable_file", lambda _path: False)
    monkeypatch.setattr(
        local_agent_health.subprocess,
        "run",
        lambda *args, **kwargs: _Completed(stdout="/usr/local/bin\n"),
    )

    detected = local_agent_health.detect_local_agents(force=True)

    assert detected["openclaw"]["found"] is False
    assert detected["openclaw"]["status"] == "not_found"
    assert detected["openclaw"]["path"] is None
    assert detected["openclaw"]["candidate_paths"] == []

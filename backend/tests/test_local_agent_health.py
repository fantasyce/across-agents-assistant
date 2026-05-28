import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from across_agents_assistant.agent_ids import normalize_agent_id
from across_agents_assistant import local_agent_health
from across_agents_assistant.api_server import app
from across_agents_assistant.task_manager.dispatcher import TaskDispatcher
from across_agents_assistant.task_manager.orchestration.owner_agent import OwnerAgent
from across_agents_assistant.task_manager.state import TaskState


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


def test_openclaw_is_first_class_agent_id_and_local_is_legacy_alias():
    assert normalize_agent_id("openclaw") == "openclaw"
    assert normalize_agent_id("local") == "openclaw"


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


def test_legacy_local_agent_config_migrates_to_openclaw(tmp_path):
    config_file = local_agent_health.LOCAL_AGENT_CONFIG_FILE
    config_file.write_text(
        '{"agents":{"local":{"executable_path":"/usr/local/bin/openclaw"}}}',
        encoding="utf-8",
    )

    assert local_agent_health.get_configured_agent_path("openclaw") == "/usr/local/bin/openclaw"
    assert local_agent_health.get_configured_agent_path("local") == "/usr/local/bin/openclaw"
    migrated = json.loads(config_file.read_text(encoding="utf-8"))
    assert "openclaw" in migrated["agents"]
    assert "local" not in migrated["agents"]


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


def test_dispatcher_valid_agents_excludes_unresponsive_local_agent(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()
    monkeypatch.setattr(
        local_agent_health,
        "detect_local_agents",
        lambda: {
            "openclaw": {
                "found": True,
                "available": False,
                "status": "unavailable",
                "path": "/usr/local/bin/openclaw",
                "version": "Local Agent 1.0",
            },
            "hermes": {
                "found": True,
                "available": True,
                "status": "available",
                "path": "/usr/local/bin/hermes",
                "version": "Hermes 1.0",
            },
            "claude": {
                "found": False,
                "available": False,
                "status": "not_found",
                "path": None,
                "version": None,
            },
        },
    )

    dispatcher = TaskDispatcher(TaskState(), local_agent_client=object())

    assert "openclaw" not in dispatcher._get_valid_agents()
    assert "hermes" in dispatcher._get_valid_agents()


def test_owner_agent_available_agents_excludes_unresponsive_local_agent(monkeypatch):
    local_agent_health.clear_local_agent_health_cache()
    monkeypatch.setattr(
        local_agent_health,
        "is_local_agent_available",
        lambda agent_id: agent_id == "hermes",
    )

    owner = OwnerAgent(lambda *_args, **_kwargs: None, TaskState())

    assert owner._is_agent_available("hermes") is True
    assert owner._is_agent_available("openclaw") is False
    assert owner._is_agent_available("local") is False

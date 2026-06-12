import importlib
from pathlib import Path


def test_llm_config_uses_across_agents_home_and_migrates_legacy(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / "Library/Application Support/AcrossAgentsAssistant/llm_config.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        '{"providers": [], "primary_provider": "legacy", "fallback_providers": []}',
        encoding="utf-8",
    )

    import across_agents_assistant.llm_gateway.config as config_mod

    config_mod = importlib.reload(config_mod)

    assert config_mod.CONFIG_FILE == tmp_path / ".across/data/across-agents-assistant/llm_config.json"
    assert config_mod.load_llm_config().primary_provider == "legacy"
    assert config_mod.CONFIG_FILE.exists()


def test_agent_manager_uses_across_agents_home_and_migrates_legacy(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / "Library/Application Support/AcrossAgentsAssistant/llm_agents.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        '{"active_agent": "legacy-agent", "agents": {}}',
        encoding="utf-8",
    )

    import across_agents_assistant.agent_manager as manager_mod

    manager_mod = importlib.reload(manager_mod)
    manager = manager_mod.AgentManager()

    assert manager_mod.AGENTS_CONFIG_FILE == tmp_path / ".across/data/across-agents-assistant/llm_agents.json"
    assert manager.get_active_agent() == "legacy-agent"
    assert manager_mod.AGENTS_CONFIG_FILE.exists()


def test_agent_manager_prunes_removed_local_cli_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = tmp_path / ".across/data/across-agents-assistant/llm_agents.json"
    config_file.parent.mkdir(parents=True)
    removed_local_id = "deferred-local-ide"
    retained_cloud_id = "custom-cloud"
    config_file.write_text(
        (
            '{"active_agent": "%s", "agents": {'
            '"%s": {"type": "local_cli", "model": ""},'
            '"%s": {"type": "openai_compatible", "model": "custom"}}}'
        )
        % (removed_local_id, removed_local_id, retained_cloud_id),
        encoding="utf-8",
    )

    import across_agents_assistant.agent_manager as manager_mod

    manager_mod = importlib.reload(manager_mod)
    manager = manager_mod.AgentManager()

    assert removed_local_id not in manager.config["agents"]
    assert retained_cloud_id in manager.config["agents"]
    assert manager.get_active_agent() == manager_mod.DEFAULT_CONFIG["active_agent"]


def test_local_agent_default_workspace_uses_across_agents_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    from across_agents_assistant.local_agent.client import default_local_agent_workspace

    assert default_local_agent_workspace() == Path(tmp_path) / ".across/data/across-agents-assistant/workspace"


def test_local_kb_default_dir_uses_across_data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    import across_agents_assistant.paths as paths
    import across_agents_assistant.mcp_servers.local_kb as local_kb

    importlib.reload(paths)
    local_kb = importlib.reload(local_kb)

    assert local_kb.default_kb_dir() == str(
        tmp_path / ".across/data/across-agents-assistant/local-knowledge"
    )
    assert "Documents" not in local_kb.default_kb_dir()


def test_runtime_paths_are_under_across_agents_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    import across_agents_assistant.paths as paths

    paths = importlib.reload(paths)

    assert paths.log_dir() == tmp_path / ".across/logs/across-agents-assistant"
    assert paths.run_dir() == tmp_path / ".across/run/across-agents-assistant"
    assert paths.tmp_dir() == tmp_path / ".across/cache/across-agents-assistant/tmp"
    assert paths.backend_socket_path() == str(tmp_path / ".across/run/across-agents-assistant/across-agents.sock")
    assert paths.speech_socket_path() == str(tmp_path / ".across/run/across-agents-assistant/speech_cli.sock")


def test_across_agents_home_override_controls_runtime_paths(monkeypatch, tmp_path):
    custom_home = tmp_path / "custom-app-home"
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(custom_home))

    import across_agents_assistant.paths as paths

    paths = importlib.reload(paths)

    assert paths.data_file("assistant.db") == custom_home / "assistant.db"
    assert paths.log_dir() == custom_home / "logs"
    assert paths.backend_socket_path() == str(custom_home / "run/across-agents.sock")

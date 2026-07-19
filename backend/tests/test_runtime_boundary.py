import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

import across_agents_assistant.orchestrator_plugin as orchestrator_plugin
import across_agents_assistant.tools.mcp_client as mcp_client_module
from across_agents_assistant import api_server
from across_agents_assistant.paths import ecosystem_home
from across_agents_assistant import runtime_boundary
from across_agents_assistant.orchestrator_plugin import (
    DEFAULT_ORCHESTRATOR_INSTALL_SOURCE,
    OrchestratorPluginConfig,
    OrchestratorPluginManager,
)
from across_agents_assistant.plugin_runtime import (
    _install_source,
    _known_plugin,
    _resolve_command,
    _run_checked,
    _safe_plugin_env,
    inspect_across_plugin,
)
from across_agents_assistant.tools.mcp_client import MCPClientManager


def _write_context_command(across_home: Path) -> Path:
    command = across_home / "bin" / "across-context"
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  plugin-manifest) printf '{\"id\":\"across-context\",\"displayName\":\"Across Context\",\"kind\":\"memory-provider\",\"version\":\"9.9.9\"}\\n' ;;\n"
        "  plugin-status) printf '{\"status\":\"installed\",\"installed\":true,\"available\":true}\\n' ;;\n"
        "  *) printf '{}\\n' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    command.chmod(command.stat().st_mode | stat.S_IXUSR)
    (across_home / "plugins" / "across-context").mkdir(parents=True, exist_ok=True)
    (across_home / "plugins" / "across-context" / "manifest.json").write_text(
        json.dumps({"id": "across-context", "displayName": "Across Context", "kind": "memory-provider"}),
        encoding="utf-8",
    )
    return command


def _write_python_shim(path: Path) -> Path:
    path.write_text("#!/bin/sh\nprintf 'Python 3.11.9\\n'\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_product_runtime_env_ignores_protected_ecosystem_overrides(tmp_path):
    home = tmp_path / "home"
    protected = home / "Documents" / "projects" / "runtime"
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "ACROSS_HOME": str(protected / "across"),
        "ACROSS_PLUGIN_HOME": str(protected / "plugins"),
        "ACROSS_BIN_HOME": str(protected / "bin"),
        "ACROSS_CONTEXT_HOME": str(protected / "context-data"),
        "ACROSS_ORCHESTRATOR_HOME": str(protected / "orchestrator-data"),
        "ACROSS_AGENTS_DB_PATH": str(protected / "assistant.db"),
    }

    safe_env, issues = runtime_boundary.sanitized_product_runtime_env(env)

    assert safe_env["ACROSS_HOME"] == str(home / ".across")
    assert safe_env["ACROSS_PLUGIN_HOME"] == str(home / ".across" / "plugins")
    assert safe_env["ACROSS_BIN_HOME"] == str(home / ".across" / "bin")
    assert "ACROSS_CONTEXT_HOME" not in safe_env
    assert "ACROSS_ORCHESTRATOR_HOME" not in safe_env
    assert "ACROSS_AGENTS_DB_PATH" not in safe_env
    assert safe_env["ACROSS_CONTEXT_PRODUCT_MODE"] == "1"
    assert {issue["name"] for issue in issues} == {
        "ACROSS_HOME",
        "ACROSS_PLUGIN_HOME",
        "ACROSS_BIN_HOME",
        "ACROSS_CONTEXT_HOME",
        "ACROSS_ORCHESTRATOR_HOME",
        "ACROSS_AGENTS_DB_PATH",
    }


def test_product_runtime_env_preserves_similarly_named_user_directories(tmp_path):
    home = tmp_path / "home"
    adjacent = home / "DocumentsArchive" / "runtime"
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "ACROSS_HOME": str(adjacent / "across"),
    }

    safe_env, issues = runtime_boundary.sanitized_product_runtime_env(env)

    assert safe_env["ACROSS_HOME"] == str(adjacent / "across")
    assert issues == []


def test_runtime_paths_expand_tilde_with_passed_home(tmp_path):
    home = tmp_path / "home"
    env = {
        "HOME": str(home),
        "ACROSS_HOME": "~/custom-across",
    }

    assert ecosystem_home(env) == (home / "custom-across").resolve()


@pytest.mark.parametrize("product_flag", ["ACROSS_CONTEXT_PRODUCT_MODE", "ACROSS_ORCHESTRATOR_PRODUCT_MODE"])
def test_plugin_product_mode_flags_sanitize_protected_runtime_overrides(tmp_path, product_flag):
    home = tmp_path / "home"
    protected = home / "Documents" / "projects" / "runtime"
    env = {
        "HOME": str(home),
        product_flag: "1",
        "ACROSS_HOME": str(protected / "across"),
    }

    safe_env, issues = runtime_boundary.sanitized_product_runtime_env(env)

    assert safe_env["ACROSS_HOME"] == str(home / ".across")
    assert safe_env["ACROSS_AGENTS_PRODUCT_MODE"] == "1"
    assert safe_env["ACROSS_CONTEXT_PRODUCT_MODE"] == "1"
    assert safe_env["ACROSS_ORCHESTRATOR_PRODUCT_MODE"] == "1"
    assert [issue["name"] for issue in issues] == ["ACROSS_HOME"]


@pytest.mark.parametrize("developer_flag", ["ACROSS_CONTEXT_DEVELOPER_MODE", "ACROSS_ORCHESTRATOR_DEVELOPER_MODE"])
def test_plugin_developer_mode_flags_preserve_protected_runtime_overrides(tmp_path, developer_flag):
    home = tmp_path / "home"
    protected = home / "Documents" / "projects" / "runtime"
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        developer_flag: "1",
        "ACROSS_HOME": str(protected / "across"),
    }

    safe_env, issues = runtime_boundary.sanitized_product_runtime_env(env)

    assert safe_env["ACROSS_HOME"] == str(protected / "across")
    assert safe_env["ACROSS_CONTEXT_DEVELOPER_MODE"] == "1"
    assert safe_env["ACROSS_ORCHESTRATOR_DEVELOPER_MODE"] == "1"
    assert issues == []


def test_developer_mode_preserves_protected_ecosystem_overrides(tmp_path):
    home = tmp_path / "home"
    protected = home / "Documents" / "projects" / "runtime"
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "ACROSS_AGENTS_DEVELOPER_MODE": "1",
        "ACROSS_HOME": str(protected / "across"),
        "ACROSS_PLUGIN_HOME": str(protected / "plugins"),
        "ACROSS_BIN_HOME": str(protected / "bin"),
        "ACROSS_CONTEXT_HOME": str(protected / "context-data"),
        "ACROSS_ORCHESTRATOR_HOME": str(protected / "orchestrator-data"),
        "ACROSS_AGENTS_DB_PATH": str(protected / "assistant.db"),
    }

    safe_env, issues = runtime_boundary.sanitized_product_runtime_env(env)

    assert safe_env["ACROSS_HOME"] == str(protected / "across")
    assert safe_env["ACROSS_PLUGIN_HOME"] == str(protected / "plugins")
    assert safe_env["ACROSS_BIN_HOME"] == str(protected / "bin")
    assert safe_env["ACROSS_CONTEXT_HOME"] == str(protected / "context-data")
    assert safe_env["ACROSS_ORCHESTRATOR_HOME"] == str(protected / "orchestrator-data")
    assert safe_env["ACROSS_AGENTS_DB_PATH"] == str(protected / "assistant.db")
    assert safe_env["ACROSS_CONTEXT_DEVELOPER_MODE"] == "1"
    assert issues == []


def test_product_runtime_env_ignores_protected_plugin_install_sources(tmp_path):
    home = tmp_path / "home"
    context_source = home / "Documents" / "projects" / "across-context"
    orchestrator_source = home / "Documents" / "projects" / "across-orchestrator"
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE": str(context_source),
        "ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE": orchestrator_source.as_uri(),
    }

    safe_env, issues = runtime_boundary.sanitized_product_runtime_env(env)

    assert "ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE" not in safe_env
    assert "ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE" not in safe_env
    assert {issue["name"] for issue in issues} == {
        "ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE",
        "ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE",
    }
    assert _install_source(_known_plugin("across-context"), safe_env) == "git+https://github.com/fantasyce/across-context.git#v0.11.0"
    assert _install_source(_known_plugin("across-orchestrator"), safe_env) == "git+https://github.com/fantasyce/across-orchestrator.git@v0.10.3"
    assert _install_source(_known_plugin("across-autopilot"), safe_env) == "git+https://github.com/fantasyce/across-autopilot.git#v0.5.0"
    assert DEFAULT_ORCHESTRATOR_INSTALL_SOURCE == "git+https://github.com/fantasyce/across-orchestrator.git@v0.10.3"


def test_developer_mode_preserves_protected_plugin_install_sources(tmp_path):
    home = tmp_path / "home"
    context_source = home / "Documents" / "projects" / "across-context"
    orchestrator_source = home / "Documents" / "projects" / "across-orchestrator"
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "ACROSS_AGENTS_DEVELOPER_MODE": "1",
        "ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE": str(context_source),
        "ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE": orchestrator_source.as_uri(),
    }

    safe_env, issues = runtime_boundary.sanitized_product_runtime_env(env)

    assert safe_env["ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE"] == str(context_source)
    assert safe_env["ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE"] == orchestrator_source.as_uri()
    assert issues == []


def test_orchestrator_config_uses_default_install_source_when_product_override_is_protected(monkeypatch, tmp_path):
    home = tmp_path / "home"
    protected_source = home / "Documents" / "projects" / "across-orchestrator"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_AGENTS_PRODUCT_MODE", "1")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE", protected_source.as_uri())

    config = OrchestratorPluginConfig.from_env()

    assert config.install_source == DEFAULT_ORCHESTRATOR_INSTALL_SOURCE


def test_orchestrator_config_preserves_protected_install_source_in_developer_mode(monkeypatch, tmp_path):
    home = tmp_path / "home"
    protected_source = home / "Documents" / "projects" / "across-orchestrator"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_AGENTS_PRODUCT_MODE", "1")
    monkeypatch.setenv("ACROSS_AGENTS_DEVELOPER_MODE", "1")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE", protected_source.as_uri())

    config = OrchestratorPluginConfig.from_env()

    assert config.install_source == protected_source.as_uri()


def test_plugin_inspection_uses_managed_home_when_product_env_is_polluted(tmp_path):
    home = tmp_path / "home"
    managed_home = home / ".across"
    command = _write_context_command(managed_home)
    protected = home / "Documents" / "projects" / "across"
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "ACROSS_HOME": str(protected),
        "PATH": "",
    }

    context = inspect_across_plugin("across-context", env=env, probe=True)

    assert context["available"] is True
    assert context["paths"]["home"] == str(managed_home)
    assert context["command"] == str(command)
    assert "Documents" not in json.dumps(context["paths"])
    assert context["runtime_boundary_issues"][0]["name"] == "ACROSS_HOME"


def test_mcp_across_context_registration_uses_managed_product_home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_AGENTS_PRODUCT_MODE", "1")
    monkeypatch.setenv("ACROSS_HOME", str(home / "Documents" / "projects" / "across"))

    manager = MCPClientManager()
    manager.register_server("across_context", "across-context", ["mcp"], env={})

    params = manager.server_configs["across_context"]
    assert params.env["ACROSS_HOME"] == str(home / ".across")
    assert params.env["ACROSS_PLUGIN_HOME"] == str(home / ".across" / "plugins")
    assert params.env["ACROSS_BIN_HOME"] == str(home / ".across" / "bin")


def test_mcp_across_context_registration_uses_passed_home_for_search_path(tmp_path):
    home = tmp_path / "home"
    manager = MCPClientManager()
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "ACROSS_HOME": str(home / "Documents" / "projects" / "across"),
        "PATH": "/usr/bin",
    }

    manager.register_server("across_context", "across-context", ["mcp"], env=env)

    params = manager.server_configs["across_context"]
    paths = str((params.env or {})["PATH"]).split(os.pathsep)
    assert paths[0] == str(home / ".across" / "bin")
    assert params.env["ACROSS_HOME"] == str(home / ".across")


def test_mcp_npm_global_bin_uses_passed_environment(monkeypatch, tmp_path):
    home = tmp_path / "home"
    manager = MCPClientManager()
    captured_env: dict[str, str] = {}

    monkeypatch.setattr(manager, "_which_in_paths", lambda command, paths, env: "/usr/bin/npm")

    def fake_run(args, **kwargs):
        captured_env.update(kwargs["env"])
        return subprocess.CompletedProcess(args, 0, stdout=str(home / ".npm-global") + "\n", stderr="")

    monkeypatch.setattr(mcp_client_module.subprocess, "run", fake_run)

    search_path = manager._command_search_path(
        "/usr/bin",
        {"HOME": str(home), "ACROSS_AGENTS_PRODUCT_MODE": "1", "PATH": "/usr/bin"},
    )

    assert captured_env["HOME"] == str(home)
    assert str(home / ".npm-global" / "bin") in search_path.split(os.pathsep)


def test_mcp_command_resolution_expands_tilde_path_with_passed_home_in_developer_mode(tmp_path):
    home = tmp_path / "home"
    command = home / "tools" / "across-context"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(command.stat().st_mode | stat.S_IXUSR)
    manager = MCPClientManager()
    env = {
        "HOME": str(home),
        "ACROSS_CONTEXT_PRODUCT_MODE": "1",
        "ACROSS_AGENTS_DEVELOPER_MODE": "1",
        "PATH": "~/tools",
    }

    assert manager._resolve_command_path(
        "across-context",
        env,
        block_protected_product_path=True,
    ) == str(command)


def test_mcp_product_mode_rejects_direct_unmanaged_context_command(tmp_path):
    home = tmp_path / "home"
    command = home / "tools" / "across-context"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(command.stat().st_mode | stat.S_IXUSR)
    manager = MCPClientManager()
    env = {
        "HOME": str(home),
        "ACROSS_CONTEXT_PRODUCT_MODE": "1",
        "PATH": "",
    }

    assert manager._resolve_command_path(
        str(command),
        env,
        block_protected_product_path=True,
    ) is None


def test_mcp_product_mode_allows_direct_managed_context_command(tmp_path):
    home = tmp_path / "home"
    command = home / ".across" / "bin" / "across-context"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(command.stat().st_mode | stat.S_IXUSR)
    manager = MCPClientManager()
    env = {
        "HOME": str(home),
        "ACROSS_CONTEXT_PRODUCT_MODE": "1",
        "PATH": "",
    }

    assert manager._resolve_command_path(
        str(command),
        env,
        block_protected_product_path=True,
    ) == str(command)


def test_plugin_inspection_ignores_protected_command_on_path_in_product_mode(tmp_path):
    home = tmp_path / "home"
    dev_bin = home / "Documents" / "projects" / "across-context" / "bin"
    dev_command = dev_bin / "across-context"
    dev_bin.mkdir(parents=True, exist_ok=True)
    dev_command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    dev_command.chmod(dev_command.stat().st_mode | stat.S_IXUSR)
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "PATH": str(dev_bin),
    }

    command = _resolve_command("across-context", env)
    context = inspect_across_plugin("across-context", env=env, probe=True)

    assert command == home / ".across" / "bin" / "across-context"
    assert context["available"] is False
    assert context["command"] == str(home / ".across" / "bin" / "across-context")
    assert "Documents" not in json.dumps(context)


def test_plugin_command_resolution_skips_protected_path_before_file_probe(monkeypatch, tmp_path):
    home = tmp_path / "home"
    protected_bin = home / "Documents" / "projects" / "across-context" / "bin"
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "PATH": str(protected_bin),
    }
    original_exists = Path.exists

    def guarded_exists(path):
        if "Documents" in str(path):
            raise AssertionError("protected path was probed")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", guarded_exists)

    assert _resolve_command("across-context", env) == home / ".across" / "bin" / "across-context"


def test_plugin_command_resolution_expands_tilde_path_with_passed_home(tmp_path):
    home = tmp_path / "home"
    command = home / "tools" / "across-context"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(command.stat().st_mode | stat.S_IXUSR)
    env = {
        "HOME": str(home),
        "PATH": "~/tools",
    }

    assert _resolve_command("across-context", env) == command


def test_mcp_across_context_connect_ignores_protected_command_on_path_in_product_mode(monkeypatch, tmp_path):
    home = tmp_path / "home"
    dev_bin = home / "Documents" / "projects" / "across-context" / "bin"
    dev_command = dev_bin / "across-context"
    dev_bin.mkdir(parents=True, exist_ok=True)
    dev_command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    dev_command.chmod(dev_command.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_AGENTS_PRODUCT_MODE", "1")

    manager = MCPClientManager()
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "PATH": str(dev_bin),
    }
    manager.register_server("across_context", "across-context", ["mcp"], env=env)
    monkeypatch.setattr(manager, "_command_search_path", lambda current_path, merged_env: str(dev_bin))
    manager.register_server("across_context", "across-context", ["mcp"], env=env)
    params = manager.server_configs["across_context"]

    assert params.command == "across-context"
    assert manager._resolve_command_path(
        str(params.command),
        params.env or {},
        block_protected_product_path=True,
    ) is None


def test_mcp_command_resolution_skips_protected_path_before_which(monkeypatch, tmp_path):
    home = tmp_path / "home"
    protected_bin = home / "Documents" / "projects" / "across-context" / "bin"
    env = {
        "HOME": str(home),
        "ACROSS_CONTEXT_PRODUCT_MODE": "1",
        "PATH": str(protected_bin),
    }
    manager = MCPClientManager()

    def blocked_which(*args, **kwargs):
        raise AssertionError("protected PATH was passed to shutil.which")

    monkeypatch.setattr(mcp_client_module.shutil, "which", blocked_which)

    assert manager._resolve_command_path(
        "across-context",
        env,
        block_protected_product_path=True,
    ) is None


def test_developer_mode_preserves_protected_command_on_path_for_plugin_inspection(tmp_path):
    home = tmp_path / "home"
    dev_bin = home / "Documents" / "projects" / "across-context" / "bin"
    dev_command = dev_bin / "across-context"
    dev_bin.mkdir(parents=True, exist_ok=True)
    dev_command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    dev_command.chmod(dev_command.stat().st_mode | stat.S_IXUSR)
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
        "ACROSS_AGENTS_DEVELOPER_MODE": "1",
        "PATH": str(dev_bin),
    }

    assert _resolve_command("across-context", env) == dev_command


def test_plugin_child_env_removes_polluted_context_command(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_CONTEXT_COMMAND", f"node {home}/Documents/projects/across-context/src/cli.js")
    env = {
        "HOME": str(home),
        "ACROSS_AGENTS_PRODUCT_MODE": "1",
    }

    safe_env = _safe_plugin_env(env)

    assert "ACROSS_CONTEXT_COMMAND" not in safe_env


def test_plugin_lifecycle_runner_removes_polluted_context_command(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_CONTEXT_COMMAND", f"node {home}/Documents/projects/across-context/src/cli.js")
    captured_env: dict[str, str] = {}

    def runner(args, **kwargs):
        captured_env.update(kwargs["env"])
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    _run_checked(["noop"], {"HOME": str(home), "ACROSS_AGENTS_PRODUCT_MODE": "1"}, runner=runner)

    assert "ACROSS_CONTEXT_COMMAND" not in captured_env


def test_orchestrator_sidecar_env_replaces_polluted_context_command(monkeypatch, tmp_path):
    home = tmp_path / "home"
    python = _write_python_shim(tmp_path / "python3.11")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_AGENTS_PRODUCT_MODE", "1")
    monkeypatch.setenv("ACROSS_HOME", str(home / "Documents" / "projects" / "across"))
    monkeypatch.setenv("ACROSS_CONTEXT_COMMAND", f"node {home}/Documents/projects/across-context/src/cli.js")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_PYTHON", str(python))

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command=str(tmp_path / "missing-across-orchestrator"),
            registry_path=tmp_path / "tasks.json",
            plugin_home=tmp_path / "plugins",
        )
    )

    env = manager._env()

    assert env["ACROSS_HOME"] == str(home / ".across")
    assert env["ACROSS_CONTEXT_COMMAND"] == str(home / ".across" / "bin" / "across-context")
    assert "Documents" not in env["ACROSS_CONTEXT_COMMAND"]


def test_orchestrator_development_command_escape_requires_developer_mode(monkeypatch, tmp_path):
    home = tmp_path / "home"
    python = _write_python_shim(tmp_path / "python3.11")
    protected_command = home / "Documents" / "projects" / "across-orchestrator" / "bin" / "across-orchestrator"
    protected_command.parent.mkdir(parents=True, exist_ok=True)
    protected_command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    protected_command.chmod(protected_command.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_AGENTS_PRODUCT_MODE", "1")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_ALLOW_DEVELOPMENT_COMMAND", "1")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_PYTHON", str(python))

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command=str(protected_command),
            registry_path=tmp_path / "tasks.json",
            plugin_home=tmp_path / "plugins",
        )
    )

    assert manager._resolve_command() is None

    monkeypatch.setenv("ACROSS_AGENTS_DEVELOPER_MODE", "1")

    assert manager._resolve_command() == str(protected_command)


def test_orchestrator_status_fallback_sanitizes_protected_command(monkeypatch, tmp_path):
    home = tmp_path / "home"
    protected_command = home / "Documents" / "projects" / "across-orchestrator" / "bin" / "across-orchestrator"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_AGENTS_PRODUCT_MODE", "1")
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_COMMAND", str(protected_command))

    def broken_manager():
        raise RuntimeError("boom")

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", broken_manager)

    status = api_server._orchestrator_plugin_status(probe=False)

    assert status["command"] == "across-orchestrator"
    assert "Documents" not in json.dumps(status)


def test_orchestrator_command_lookup_expands_tilde_path_with_passed_home(tmp_path):
    home = tmp_path / "home"
    command = home / "tools" / "across-orchestrator"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(command.stat().st_mode | stat.S_IXUSR)

    resolved = orchestrator_plugin._which_executable(
        "across-orchestrator",
        "~/tools",
        {"HOME": str(home)},
    )

    assert resolved == str(command)


def test_python_resolver_rejects_python310_for_orchestrator_plugin(tmp_path):
    python310 = tmp_path / "python3.10"
    python310.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python310.chmod(python310.stat().st_mode | stat.S_IXUSR)

    assert orchestrator_plugin.SUPPORTED_PYTHON_MIN_VERSION == (3, 11)
    assert orchestrator_plugin._is_supported_python_executable(str(python310)) is False


def test_orchestrator_python_override_allows_protected_path_only_in_developer_mode(monkeypatch, tmp_path):
    home = tmp_path / "home"
    python311 = home / "Documents" / "projects" / "venv" / "bin" / "python3.11"
    python311.parent.mkdir(parents=True, exist_ok=True)
    python311.write_text("#!/bin/sh\nprintf 'Python 3.11.9\\n'\n", encoding="utf-8")
    python311.chmod(python311.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_AGENTS_PRODUCT_MODE", "1")

    assert orchestrator_plugin._is_supported_python_executable(str(python311)) is False

    monkeypatch.setenv("ACROSS_AGENTS_DEVELOPER_MODE", "1")

    assert orchestrator_plugin._is_supported_python_executable(str(python311)) is True


def test_orchestrator_python_override_skips_protected_path_before_file_probe(monkeypatch, tmp_path):
    home = tmp_path / "home"
    protected_python = home / "Documents" / "projects" / "venv" / "bin" / "python3.11"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_AGENTS_PRODUCT_MODE", "1")

    def blocked_probe(path):
        raise AssertionError(f"protected Python path was probed: {path}")

    monkeypatch.setattr(orchestrator_plugin, "_is_executable_file", blocked_probe)

    assert orchestrator_plugin._is_supported_python_executable(str(protected_python)) is False


def test_stale_non_running_sidecar_metadata_is_removed(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACROSS_HOME", str(home / ".across"))
    run_root = home / ".across" / "run" / "across-orchestrator"
    run_root.mkdir(parents=True)
    stale = run_root / "manual-debug.json"
    stale.write_text(
        json.dumps(
            {
                "componentId": "across-orchestrator",
                "runtimeId": "manual-debug",
                "pid": 99999999,
                "endpoint": "http://127.0.0.1:1",
            }
        ),
        encoding="utf-8",
    )

    manager = OrchestratorPluginManager(
        OrchestratorPluginConfig(
            mode="external",
            command=str(tmp_path / "missing-across-orchestrator"),
            registry_path=tmp_path / "tasks.json",
            plugin_home=tmp_path / "plugins",
        )
    )

    manager._cleanup_stale_aaa_sidecars()

    assert not stale.exists()

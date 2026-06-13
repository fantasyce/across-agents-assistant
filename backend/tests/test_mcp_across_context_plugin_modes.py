import os
import json
import textwrap
from pathlib import Path

import pytest

from across_agents_assistant.tools.mcp_client import MCPClientManager


@pytest.mark.asyncio
async def test_across_context_prefers_external_mcp_plugin_when_available(tmp_path):
    command = _write_fake_across_context_server(tmp_path)
    capture_file = tmp_path / "child-env.json"
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(command),
        ["mcp"],
        env={
            "ACROSS_CONTEXT_CAPTURE_FILE": str(capture_file),
            "ACROSS_CONTEXT_HOME": str(tmp_path / "vault"),
        },
    )

    ok, error = await manager.connect_server("across_context")
    assert ok, error

    try:
        child_env = json.loads(capture_file.read_text(encoding="utf-8"))
        assert child_env["cwd"] == "/"
        assert child_env["pwd"] == "/"
        assert child_env["oldpwd"] == "/"
        assert child_env["init_cwd"] is None
        assert manager.get_server_implementation("across_context") == "external"
        tools = manager.get_all_tools_schema()
        remember = next(tool for tool in tools if tool["name"] == "across_context__remember_context")
        assert remember["description"] == "External Across Context MCP write"

        result = await manager.call_tool(
            "across_context",
            "remember_context",
            {"text": "External plugin should handle this memory."},
        )
        assert "external mcp result" in result
    finally:
        await manager.disconnect_server("across_context")


@pytest.mark.asyncio
async def test_across_context_default_mode_requires_external_plugin(tmp_path):
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(tmp_path / "missing" / "across-context"),
        ["mcp"],
        env={"ACROSS_CONTEXT_HOME": str(tmp_path / "vault")},
    )

    ok, error = await manager.connect_server("across_context")

    assert not ok
    assert "external Across Context MCP server is required" in error
    assert manager.get_server_implementation("across_context") is None


@pytest.mark.asyncio
async def test_across_context_explicit_auto_mode_still_requires_external_plugin(tmp_path):
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(tmp_path / "missing" / "across-context"),
        ["mcp"],
        env={
            "ACROSS_CONTEXT_HOME": str(tmp_path / "vault"),
            "ACROSS_AGENTS_ACROSS_CONTEXT_MODE": "auto",
        },
    )

    ok, error = await manager.connect_server("across_context")

    assert not ok
    assert "external Across Context MCP server is required" in error
    assert manager.get_server_implementation("across_context") is None


@pytest.mark.asyncio
async def test_across_context_external_mode_does_not_hide_install_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_ACROSS_CONTEXT_MODE", "external")
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(tmp_path / "missing" / "across-context"),
        ["mcp"],
        env={"ACROSS_CONTEXT_HOME": str(tmp_path / "vault")},
    )

    ok, error = await manager.connect_server("across_context")

    assert not ok
    assert "external Across Context MCP server is required" in error
    assert manager.get_server_implementation("across_context") is None


@pytest.mark.asyncio
async def test_across_context_external_mode_rejects_wrapper_referencing_documents(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_ACROSS_CONTEXT_MODE", "external")
    marker_path = tmp_path / "wrapper-ran"
    wrapper = tmp_path / "across-context"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"touch {marker_path}\n"
        "exec /usr/bin/env node 'file:///Users/example/Documents/projects/across-context/src/cli.js' \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(wrapper),
        ["mcp"],
        env={"ACROSS_CONTEXT_HOME": str(tmp_path / "vault")},
    )

    ok, error = await manager.connect_server("across_context")

    assert not ok
    assert "must be repaired" in error
    assert manager.get_server_implementation("across_context") is None
    assert not marker_path.exists()


@pytest.mark.asyncio
async def test_across_context_explicit_auto_mode_rejects_unsafe_wrapper_without_fallback(tmp_path):
    marker_path = tmp_path / "wrapper-ran"
    wrapper = tmp_path / "across-context"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"touch {marker_path}\n"
        "exec /usr/bin/env node 'file:///Users/example/Documents/projects/across-context/src/cli.js' \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(wrapper),
        ["mcp"],
        env={
            "ACROSS_CONTEXT_HOME": str(tmp_path / "vault"),
            "ACROSS_AGENTS_ACROSS_CONTEXT_MODE": "auto",
        },
    )

    ok, error = await manager.connect_server("across_context")

    assert not ok
    assert "must be repaired" in error
    assert manager.get_server_implementation("across_context") is None
    assert not marker_path.exists()


@pytest.mark.parametrize("legacy_mode", ["auto", "builtin", "native", "builtin_compatibility"])
@pytest.mark.asyncio
async def test_across_context_legacy_modes_do_not_enable_host_builtin_runtime(tmp_path, legacy_mode):
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(tmp_path / "missing" / "across-context"),
        ["mcp"],
        env={
            "ACROSS_CONTEXT_HOME": str(tmp_path / "vault"),
            "ACROSS_AGENTS_ACROSS_CONTEXT_MODE": legacy_mode,
        },
    )

    ok, error = await manager.connect_server("across_context")

    assert not ok
    assert "external Across Context MCP server is required" in error
    assert manager.get_server_implementation("across_context") is None


def test_across_context_builtin_runtime_is_not_packaged_in_host_source_tree():
    source_root = Path(__file__).resolve().parents[1] / "src" / "across_agents_assistant" / "tools"

    assert not (source_root / "across_context_native.py").exists()
    assert "across_context_native" not in (source_root / "mcp_client.py").read_text(encoding="utf-8")


def test_across_context_registration_scrubs_shell_working_directory(monkeypatch, tmp_path):
    project_path = tmp_path / "private" / "projects" / "across-agents-assistant"
    monkeypatch.setenv("PWD", str(project_path))
    monkeypatch.setenv("OLDPWD", str(project_path))
    monkeypatch.setenv("INIT_CWD", str(project_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key-should-not-be-forwarded")
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", "/Applications/Across Agents Assistant.app/Contents/Resources/backend/backend")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-should-not-be-forwarded")

    command = _write_fake_across_context_server(tmp_path)
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(command),
        ["mcp"],
        env={"ACROSS_CONTEXT_HOME": str(tmp_path / "vault")},
    )

    params = manager.server_configs["across_context"]
    assert params.env["PWD"] == "/"
    assert params.env["OLDPWD"] == "/"
    assert "INIT_CWD" not in params.env
    assert "DEEPSEEK_API_KEY" not in params.env
    assert "_PYI_ARCHIVE_FILE" not in params.env
    assert "CODEX_THREAD_ID" not in params.env
    assert params.env["ACROSS_CONTEXT_HOME"] == str(tmp_path / "vault")


def test_across_context_plugin_bin_is_prioritized_in_command_search_path():
    manager = MCPClientManager()

    search_path = manager._command_search_path("/opt/homebrew/bin:/usr/bin")

    paths = search_path.split(os.pathsep)
    assert paths[0].endswith(".across/bin")
    assert not any(path.endswith(".across_agents/plugins/bin") for path in paths)


def test_command_resolution_uses_executable_search_semantics(tmp_path):
    manager = MCPClientManager()
    wrapper = tmp_path / "across-context"
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wrapper.chmod(0o755)
    plain_file = tmp_path / "not-executable"
    plain_file.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    env = {"PATH": str(tmp_path)}

    assert manager._resolve_command_path("across-context", env) == str(wrapper)
    assert manager._resolve_command_path(str(wrapper), env) == str(wrapper)
    assert manager._resolve_command_path(str(plain_file), env) is None


def _write_fake_across_context_server(tmp_path: Path) -> Path:
    command = tmp_path / "across-context"
    command.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            import sys

            capture = os.environ.get("ACROSS_CONTEXT_CAPTURE_FILE")
            if capture:
                with open(capture, "w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "cwd": os.getcwd(),
                            "pwd": os.environ.get("PWD"),
                            "oldpwd": os.environ.get("OLDPWD"),
                            "init_cwd": os.environ.get("INIT_CWD"),
                        },
                        handle,
                    )

            TOOL = {
                "name": "remember_context",
                "description": "External Across Context MCP write",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            }

            for line in sys.stdin:
                if not line.strip():
                    continue
                message = json.loads(line)
                method = message.get("method")
                message_id = message.get("id")
                if method == "initialize":
                    result = {
                        "protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "across-context", "version": "fake-external"},
                    }
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/list":
                    result = {"tools": [TOOL]}
                elif method == "tools/call":
                    result = {
                        "content": [{"type": "text", "text": "external mcp result"}],
                        "isError": False,
                    }
                else:
                    result = {}
                if message_id is not None:
                    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}) + "\\n")
                    sys.stdout.flush()
            """
        ),
        encoding="utf-8",
    )
    command.chmod(0o755)
    return command

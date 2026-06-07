import os
import textwrap
from pathlib import Path

import pytest

from across_agents_assistant.tools.mcp_client import MCPClientManager


@pytest.mark.asyncio
async def test_across_context_prefers_external_mcp_plugin_when_available(tmp_path):
    command = _write_fake_across_context_server(tmp_path)
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(command),
        ["mcp"],
        env={"ACROSS_CONTEXT_HOME": str(tmp_path / "vault")},
    )

    ok, error = await manager.connect_server("across_context")
    assert ok, error

    try:
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
async def test_across_context_falls_back_to_builtin_compatibility_when_external_missing(tmp_path):
    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        str(tmp_path / "missing" / "across-context"),
        ["mcp"],
        env={"ACROSS_CONTEXT_HOME": str(tmp_path / "vault")},
    )

    ok, error = await manager.connect_server("across_context")
    assert ok, error

    try:
        assert manager.get_server_implementation("across_context") == "builtin_compatibility"
        tools = {tool["name"] for tool in manager.get_all_tools_schema()}
        assert "across_context__remember_context" in tools
        result = await manager.call_tool(
            "across_context",
            "remember_context",
            {
                "text": "Fallback compatibility should preserve shared memory.",
                "scope": "global",
                "type": "preference",
                "auto": False,
            },
        )
        assert "Fallback compatibility" in result
    finally:
        await manager.disconnect_server("across_context")


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


def _write_fake_across_context_server(tmp_path: Path) -> Path:
    command = tmp_path / "across-context"
    command.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import sys

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

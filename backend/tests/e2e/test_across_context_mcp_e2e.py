import shutil

import pytest

from across_agents_assistant.tools.mcp_client import MCPClientManager


@pytest.mark.asyncio
async def test_across_context_mcp_shares_memory_between_agent_views(tmp_path, monkeypatch):
    if not shutil.which("across-context"):
        pytest.skip("across-context CLI is not installed on PATH")

    context_home = tmp_path / "across-context-home"
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("ACROSS_CONTEXT_HOME", str(context_home))

    token = "AAA_ACROSS_CONTEXT_SHARED_MEMORY_E2E"
    writer = MCPClientManager()
    writer.register_server(
        "across_context",
        "across-context",
        ["mcp"],
        env={"ACROSS_CONTEXT_HOME": str(context_home)},
    )
    writer_ok, writer_error = await writer.connect_server("across_context")
    assert writer_ok, writer_error

    try:
        writer_result = await writer.call_tool(
            "across_context",
            "remember_context",
            {
                "text": f"{token}: all configured agents should share this project memory.",
                "scope": "project",
                "projectRoot": str(project_root),
                "type": "decision",
                "tags": ["e2e", "shared-memory"],
                "auto": False,
            },
        )
        assert token in writer_result
    finally:
        await writer.disconnect_server("across_context")

    reader = MCPClientManager()
    reader.register_server(
        "across_context",
        "across-context",
        ["mcp"],
        env={"ACROSS_CONTEXT_HOME": str(context_home)},
    )
    reader_ok, reader_error = await reader.connect_server("across_context")
    assert reader_ok, reader_error

    try:
        tool_names = {tool["name"] for tool in reader.get_all_tools_schema()}
        assert "across_context__search_context" in tool_names
        assert "across_context__remember_context" in tool_names

        reader_result = await reader.call_tool(
            "across_context",
            "search_context",
            {
                "query": token,
                "projectRoot": str(project_root),
                "limit": 5,
                "mode": "hybrid",
            },
        )
        assert token in reader_result
    finally:
        await reader.disconnect_server("across_context")

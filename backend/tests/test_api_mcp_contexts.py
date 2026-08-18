import json
import textwrap
import asyncio

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app
from across_agents_assistant.tools.mcp_client import mcp_manager
from across_agents_assistant.tools.mcp_client import MCPClientManager


def test_mcp_manager_shutdown_closes_all_stdio_stacks_and_clears_runtime_state():
    closed = []

    class FakeStack:
        def __init__(self, server_id):
            self.server_id = server_id

        async def aclose(self):
            closed.append(self.server_id)

    manager = MCPClientManager()
    manager.sessions = {"filesystem": object(), "sqlite": object()}
    manager._exit_stacks = {
        "filesystem": FakeStack("filesystem"),
        "sqlite": FakeStack("sqlite"),
    }
    manager.server_tools = {"filesystem": [], "sqlite": []}
    manager._connecting = {"local_kb"}

    asyncio.run(manager.shutdown())

    assert set(closed) == {"filesystem", "sqlite"}
    assert manager.sessions == {}
    assert manager._exit_stacks == {}
    assert manager.server_tools == {}
    assert manager._connecting == set()


def test_mcp_contexts_report_across_context_implementation(tmp_path):
    client = TestClient(app)
    server_id = "across_context"
    command = tmp_path / "across-context"
    command.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import sys

            for line in sys.stdin:
                if not line.strip():
                    continue
                message = json.loads(line)
                method = message.get("method")
                message_id = message.get("id")
                if method == "initialize":
                    result = {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "across-context", "version": "fake-external"},
                    }
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/list":
                    result = {
                        "tools": [
                            {
                                "name": "remember_context",
                                "description": "External Across Context MCP write",
                                "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
                            }
                        ]
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

    response = client.post(
        "/api/mcp/connect",
        json={
            "server_id": server_id,
            "command": str(command),
            "args": ["mcp"],
            "env": {
                "ACROSS_CONTEXT_HOME": str(tmp_path / "vault"),
            },
            "readonly": False,
        },
    )

    try:
        assert response.status_code == 200, response.text
        assert response.json()["implementation"] == "external"

        contexts_response = client.get("/api/mcp/contexts")
        assert contexts_response.status_code == 200, contexts_response.text
        contexts = contexts_response.json()
        across_context = next(item for item in contexts if item["server_id"] == server_id)
        assert across_context["implementation"] == "external"
        assert across_context["connection_note"] == "External Across Context MCP server."
    finally:
        client.post("/api/mcp/disconnect", json={"server_id": server_id})
        mcp_manager.server_configs.pop(server_id, None)

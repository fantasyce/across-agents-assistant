import json
import textwrap
import asyncio

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app
from across_agents_assistant.tools.mcp_client import mcp_manager
from across_agents_assistant.tools.mcp_client import MCPClientManager


def _write_fake_mcp_server(path, tool_name):
    path.write_text(
        textwrap.dedent(
            f"""\
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
                    result = {{
                        "protocolVersion": "2024-11-05",
                        "capabilities": {{"tools": {{}}}},
                        "serverInfo": {{"name": "replacement-fixture", "version": "1"}},
                    }}
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/list":
                    result = {{
                        "tools": [{{
                            "name": "{tool_name}",
                            "description": "Replacement fixture tool",
                            "inputSchema": {{"type": "object", "properties": {{}}}},
                        }}]
                    }}
                else:
                    result = {{}}
                if message_id is not None:
                    sys.stdout.write(json.dumps({{"jsonrpc": "2.0", "id": message_id, "result": result}}) + "\\n")
                    sys.stdout.flush()
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


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


def test_forgetting_disconnected_plugin_removes_registered_runtime_configuration():
    manager = MCPClientManager()
    manager.register_server("removable", "/usr/bin/true", [], readonly=True)

    asyncio.run(manager.disconnect_server("removable", forget=True))

    assert "removable" not in manager.server_configs
    assert "removable" not in manager._sandbox_settings


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


def test_reconnecting_same_server_id_replaces_the_running_mcp_process(tmp_path):
    client = TestClient(app)
    server_id = "replacement-fixture"
    first = tmp_path / "first-mcp"
    second = tmp_path / "second-mcp"
    _write_fake_mcp_server(first, "first_tool")
    _write_fake_mcp_server(second, "second_tool")

    try:
        first_response = client.post(
            "/api/mcp/connect",
            json={"server_id": server_id, "command": str(first), "args": [], "readonly": True},
        )
        assert first_response.status_code == 200, first_response.text
        assert any(tool["name"] == f"{server_id}__first_tool" for tool in mcp_manager.get_all_tools_schema())

        second_response = client.post(
            "/api/mcp/connect",
            json={"server_id": server_id, "command": str(second), "args": [], "readonly": True},
        )
        assert second_response.status_code == 200, second_response.text
        names = {tool["name"] for tool in mcp_manager.get_all_tools_schema()}
        assert f"{server_id}__second_tool" in names
        assert f"{server_id}__first_tool" not in names
    finally:
        client.post("/api/mcp/disconnect", json={"server_id": server_id})
        mcp_manager.server_configs.pop(server_id, None)


def test_failed_same_id_replacement_restores_previous_runtime(tmp_path):
    client = TestClient(app)
    server_id = "replacement-rollback-fixture"
    first = tmp_path / "first-mcp"
    _write_fake_mcp_server(first, "first_tool")

    try:
        first_response = client.post(
            "/api/mcp/connect",
            json={"server_id": server_id, "command": str(first), "args": [], "readonly": True},
        )
        assert first_response.status_code == 200, first_response.text

        failed_response = client.post(
            "/api/mcp/connect",
            json={
                "server_id": server_id,
                "command": str(tmp_path / "missing-mcp"),
                "args": [],
                "readonly": True,
            },
        )

        assert failed_response.status_code == 500
        assert any(
            tool["name"] == f"{server_id}__first_tool"
            for tool in mcp_manager.get_all_tools_schema()
        )
        assert mcp_manager.server_configs[server_id].command == str(first)
        assert server_id in mcp_manager.sessions
    finally:
        client.post("/api/mcp/disconnect", json={"server_id": server_id, "forget": True})


def test_forget_waits_for_inflight_connect_and_wins_the_lifecycle_race():
    manager = MCPClientManager()

    async def exercise():
        connect_started = asyncio.Event()
        allow_connect = asyncio.Event()

        async def delayed_connect(server_id):
            connect_started.set()
            await allow_connect.wait()
            manager.sessions[server_id] = object()
            manager.server_tools[server_id] = []
            return True, None

        manager.connect_server = delayed_connect
        connect_task = asyncio.create_task(
            manager.register_and_connect_server(
                "remove-race",
                "/usr/bin/true",
                [],
                readonly=True,
            )
        )
        await connect_started.wait()
        forget_task = asyncio.create_task(manager.disconnect_and_forget_server("remove-race"))
        await asyncio.sleep(0)
        assert not forget_task.done()

        allow_connect.set()
        await connect_task
        await forget_task

    asyncio.run(exercise())

    assert "remove-race" not in manager.sessions
    assert "remove-race" not in manager.server_tools
    assert "remove-race" not in manager.server_configs
    assert "remove-race" not in manager._sandbox_settings


def test_connect_rejects_server_id_that_breaks_namespaced_tool_routing():
    client = TestClient(app)

    response = client.post(
        "/api/mcp/connect",
        json={"server_id": "bad__server", "command": "/usr/bin/true", "args": [], "readonly": True},
    )

    assert response.status_code == 422
    assert "bad__server" not in mcp_manager.server_configs

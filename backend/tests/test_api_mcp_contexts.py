import json
import textwrap

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app
from across_agents_assistant.tools.mcp_client import mcp_manager


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

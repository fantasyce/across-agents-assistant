from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app
from across_agents_assistant.tools.mcp_client import mcp_manager


def test_mcp_contexts_report_across_context_implementation(tmp_path):
    client = TestClient(app)
    server_id = "across_context"

    response = client.post(
        "/api/mcp/connect",
        json={
            "server_id": server_id,
            "command": str(tmp_path / "missing" / "across-context"),
            "args": ["mcp"],
            "env": {"ACROSS_CONTEXT_HOME": str(tmp_path / "vault")},
            "readonly": False,
        },
    )

    try:
        assert response.status_code == 200, response.text
        assert response.json()["implementation"] == "builtin_compatibility"

        contexts_response = client.get("/api/mcp/contexts")
        assert contexts_response.status_code == 200, contexts_response.text
        contexts = contexts_response.json()
        across_context = next(item for item in contexts if item["server_id"] == server_id)
        assert across_context["implementation"] == "builtin_compatibility"
        assert "compatibility" in across_context["connection_note"]
    finally:
        client.post("/api/mcp/disconnect", json={"server_id": server_id})
        mcp_manager.server_configs.pop(server_id, None)

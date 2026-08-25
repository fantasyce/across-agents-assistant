import json

from across_agents_assistant.agent_bridge.host_mcp_proxy import HostMCPToolProvider


def test_host_mcp_provider_uses_private_host_api_contract():
    requests = []

    def request_json(method, path, payload=None):
        requests.append((method, path, payload))
        if method == "GET":
            return [
                {
                    "name": "agent-runtime-proof__verify_local_runtime",
                    "description": "Verify without mutation.",
                    "parameters": {"type": "object", "properties": {}},
                    "risk_level": "low",
                    "source": "mcp",
                    "server_id": "agent-runtime-proof",
                    "original_name": "verify_local_runtime",
                    "requires_approval": False,
                    "safety_labels": ["mcp", "readonly"],
                    "sandbox": {"allowed_paths": [], "readonly": True},
                }
            ]
        assert json.loads(json.dumps(payload)) == {
            "tool_name": "agent-runtime-proof__verify_local_runtime",
            "arguments": {"binding_id": "codex.agent-runtime-proof"},
        }
        return {"output": "MATCHED proof_id=sha256:test", "metadata": {"source": "mcp"}}

    provider = HostMCPToolProvider(request_json=request_json)

    tools = provider.get_all_tools_schema()
    result = provider.call_tool(
        "agent-runtime-proof__verify_local_runtime",
        {"binding_id": "codex.agent-runtime-proof"},
    )

    assert [tool["name"] for tool in tools] == ["agent-runtime-proof__verify_local_runtime"]
    assert result["output"] == "MATCHED proof_id=sha256:test"
    assert requests == [
        ("GET", "/api/agent-bridge/mcp-tools", None),
        (
            "POST",
            "/api/agent-bridge/mcp-tools/call",
            {
                "tool_name": "agent-runtime-proof__verify_local_runtime",
                "arguments": {"binding_id": "codex.agent-runtime-proof"},
            },
        ),
    ]

import os
import tempfile
import pytest

os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from across_agents_assistant.persistence.permissions import ToolPermissionStore
from across_agents_assistant.tools.mcp_client import MCPClientManager


def test_permission_store_marks_tool_unavailable(tmp_path):
    store = ToolPermissionStore(str(tmp_path / "assistant.db"))

    assert store.set_permission("read_file", "unavailable")

    assert store.get_permission("read_file") == "unavailable"
    assert store.is_unavailable("read_file")
    assert not store.is_always_allowed("read_file")


def test_permission_store_ask_removes_persistent_rule(tmp_path):
    store = ToolPermissionStore(str(tmp_path / "assistant.db"))
    store.grant_always_allow("list_directory")

    assert store.set_permission("list_directory", "ask")

    assert store.get_permission("list_directory") is None
    assert not store.is_always_allowed("list_directory")


def test_unavailable_tools_are_filtered_from_agent_schemas(monkeypatch):
    import across_agents_assistant.api_server as srv

    class FakePermissionStore:
        def is_unavailable(self, tool_name):
            return tool_name == "read_file"

    class FakePersistence:
        permissions = FakePermissionStore()

    schemas = [
        {"name": "read_file", "description": "Read", "risk_level": "low"},
        {"name": "list_directory", "description": "List", "risk_level": "low"},
    ]

    monkeypatch.setattr(srv, "persistence", FakePersistence())

    assert srv._filter_unavailable_tool_schemas(schemas) == [schemas[1]]


@pytest.mark.asyncio
async def test_tools_endpoint_returns_runtime_schemas_without_mcp_duplicates(monkeypatch):
    import across_agents_assistant.api_server as srv

    class FakeRegistry:
        def get_all_tools_schema(self):
            return [
                {"name": "list_directory", "description": "List", "risk_level": "low"},
                {"name": "sqlite__sqlite_query", "description": "Query", "risk_level": "medium"},
            ]

    class FakeMCPManager:
        def get_all_tools_schema(self):
            return [
                {"name": "sqlite__sqlite_query", "description": "Query", "risk_level": "medium"},
            ]

    monkeypatch.setattr(srv, "registry", FakeRegistry())
    monkeypatch.setattr(srv, "mcp_manager", FakeMCPManager())

    schemas = await srv.get_tools()

    assert [schema["name"] for schema in schemas] == [
        "list_directory",
        "sqlite__sqlite_query",
    ]


@pytest.mark.asyncio
async def test_current_tools_endpoint_only_reports_resolvable_tools():
    import across_agents_assistant.api_server as srv

    schemas = await srv.get_tools()

    assert schemas
    for schema in schemas:
        assert srv._resolve_tool(schema["name"]), f"{schema['name']} should resolve before being shown"


@pytest.mark.asyncio
async def test_mcp_tool_approval_routes_to_matching_mcp_server(monkeypatch):
    import across_agents_assistant.api_server as srv

    calls = []

    class FakeRegistry:
        def get_tool(self, name):
            return None

    class FakeMCPManager:
        def get_all_tools_schema(self):
            return [
                {
                    "name": "sqlite__sqlite_query",
                    "description": "Query SQLite",
                    "risk_level": "medium",
                }
            ]

        async def call_tool(self, server_id, tool_name, arguments):
            calls.append((server_id, tool_name, arguments))
            return "rows"

    class FakePersistence:
        def __init__(self):
            self.audit_logs = []
            self.messages = []

        def add_audit_log(self, **kwargs):
            self.audit_logs.append(kwargs)

        def set_tool_authorization(self, tool_name, is_authorized):
            pass

        def add_message(self, **kwargs):
            self.messages.append(kwargs)

        def get_messages(self, session_id, limit=50):
            return [{"role": "user", "content": "query db"}]

    async def fake_chat_endpoint(req):
        return srv.ChatResponse(text="continued", session_id=req.session_id)

    monkeypatch.setattr(srv, "registry", FakeRegistry())
    monkeypatch.setattr(srv, "mcp_manager", FakeMCPManager())
    monkeypatch.setattr(srv, "persistence", FakePersistence())
    monkeypatch.setattr(srv, "_is_tool_unavailable", lambda tool_name: False)
    monkeypatch.setattr(srv, "chat_endpoint", fake_chat_endpoint)

    response = await srv.approve_tool_execution(
        srv.ApprovalDecision(
            session_id="s1",
            decision="approve",
            tool_name="sqlite__sqlite_query",
            tool_args={"query": "select 1"},
            agent_id="openclaw",
            tool_call_id="call-1",
        )
    )

    assert response.text == "continued"
    assert calls == [("sqlite", "sqlite_query", {"query": "select 1"})]


def test_mcp_path_allowlist_rejects_sibling_prefix_paths():
    manager = MCPClientManager()

    assert manager._is_path_allowed("/tmp/project/file.txt", ["/tmp/project"])
    assert not manager._is_path_allowed("/tmp/project-secrets/file.txt", ["/tmp/project"])


def test_mcp_tool_schemas_include_safety_metadata():
    manager = MCPClientManager()
    manager._sandbox_settings = {
        "filesystem": {"allowed_paths": ["/tmp/project"], "readonly": False}
    }
    manager.server_tools = {
        "filesystem": [
            {
                "name": "filesystem__write_file",
                "description": "Write a file",
                "parameters": {},
                "risk_level": "medium",
                "original_name": "write_file",
            }
        ]
    }

    schema = manager.get_all_tools_schema()[0]

    assert schema["source"] == "mcp"
    assert schema["server_id"] == "filesystem"
    assert schema["risk_level"] == "high"
    assert schema["requires_approval"] is True
    assert schema["sandbox"]["allowed_paths"] == ["/tmp/project"]
    assert "write-capable" in schema["safety_labels"]


def test_mcp_safety_report_summarizes_server_risk():
    manager = MCPClientManager()
    manager._sandbox_settings = {
        "filesystem": {"allowed_paths": ["/tmp/project"], "readonly": False},
        "readonly_notes": {"allowed_paths": [], "readonly": True},
    }
    manager.server_tools = {
        "filesystem": [
            {
                "name": "filesystem__read_file",
                "description": "Read a file",
                "parameters": {},
                "risk_level": "low",
                "original_name": "read_file",
            },
            {
                "name": "filesystem__write_file",
                "description": "Write a file",
                "parameters": {},
                "risk_level": "medium",
                "original_name": "write_file",
            },
        ],
        "readonly_notes": [
            {
                "name": "readonly_notes__create_note",
                "description": "Create a note",
                "parameters": {},
                "risk_level": "high",
                "original_name": "create_note",
            }
        ],
    }

    report = manager.get_safety_report()

    filesystem = next(item for item in report["servers"] if item["server_id"] == "filesystem")
    assert filesystem["tool_count"] == 2
    assert filesystem["highest_risk"] == "high"
    assert filesystem["write_capable_tool_count"] == 1
    assert filesystem["sandbox"]["allowed_paths"] == ["/tmp/project"]
    assert "High-risk MCP tools require approval." in filesystem["warnings"]

    readonly = next(item for item in report["servers"] if item["server_id"] == "readonly_notes")
    assert readonly["sandbox"]["readonly"] is True
    assert "Readonly mode blocks write-capable tools at call time." in readonly["warnings"]


@pytest.mark.asyncio
async def test_mcp_readonly_mode_blocks_write_tools_without_path_arguments():
    manager = MCPClientManager()
    manager._sandbox_settings = {"notes": {"allowed_paths": [], "readonly": True}}
    manager.sessions["notes"] = object()

    result = await manager.call_tool("notes", "create_note", {"title": "Demo"})

    assert result == "Error: This MCP server is in readonly mode. Write operations are not allowed."

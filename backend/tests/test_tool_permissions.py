import os
import tempfile
import pytest

os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from across_agents_assistant.persistence.permissions import ToolPermissionStore


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
            agent_id="local",
            tool_call_id="call-1",
        )
    )

    assert response.text == "continued"
    assert calls == [("sqlite", "sqlite_query", {"query": "select 1"})]

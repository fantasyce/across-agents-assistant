import os
import tempfile
import stat
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


def test_available_agent_tool_schemas_include_mcp_tools(monkeypatch):
    import across_agents_assistant.api_server as srv

    class FakePermissionStore:
        def is_unavailable(self, tool_name):
            return False

    class FakePersistence:
        permissions = FakePermissionStore()

    class FakeRegistry:
        def get_all_tools_schema(self):
            return [
                {"name": "list_directory", "description": "List", "risk_level": "low"},
            ]

    class FakeMCPManager:
        def get_all_tools_schema(self):
            return [
                {
                    "name": "across_context__remember_context",
                    "description": "Store shared memory",
                    "risk_level": "high",
                },
            ]

    monkeypatch.setattr(srv, "persistence", FakePersistence())
    monkeypatch.setattr(srv, "registry", FakeRegistry())
    monkeypatch.setattr(srv, "mcp_manager", FakeMCPManager())

    assert [schema["name"] for schema in srv._available_tool_schemas()] == [
        "list_directory",
        "across_context__remember_context",
    ]


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


@pytest.mark.asyncio
async def test_mcp_approval_adds_session_project_root_for_across_context(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as srv

    project_root = tmp_path / "project"
    project_root.mkdir()
    calls = []

    class FakeRegistry:
        def get_tool(self, name):
            return None

    class FakeMCPManager:
        def get_all_tools_schema(self):
            return [
                {
                    "name": "across_context__remember_context",
                    "description": "Store shared memory",
                    "risk_level": "high",
                }
            ]

        async def call_tool(self, server_id, tool_name, arguments):
            calls.append((server_id, tool_name, arguments))
            return "stored"

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
            return [{"role": "user", "content": "remember this"}]

        def get_session_project(self, session_id):
            return {"path": str(project_root)}

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
            tool_name="across_context__remember_context",
            tool_args={"text": "memory", "scope": "project"},
            agent_id="deepseek",
            tool_call_id="call-1",
        )
    )

    assert response.text == "continued"
    assert calls == [
        (
            "across_context",
            "remember_context",
            {"text": "memory", "scope": "project", "projectRoot": str(project_root)},
        )
    ]


def test_mcp_path_allowlist_rejects_sibling_prefix_paths():
    manager = MCPClientManager()

    assert manager._is_path_allowed("/tmp/project/file.txt", ["/tmp/project"])
    assert not manager._is_path_allowed("/tmp/project-secrets/file.txt", ["/tmp/project"])


def test_mcp_command_resolution_uses_npm_global_bin(monkeypatch, tmp_path):
    homebrew_bin = tmp_path / "homebrew" / "bin"
    npm_prefix = tmp_path / "cellar" / "node"
    npm_bin = npm_prefix / "bin"
    homebrew_bin.mkdir(parents=True)
    npm_bin.mkdir(parents=True)

    npm = homebrew_bin / "npm"
    npm.write_text(f"#!/bin/sh\nprintf '%s\\n' '{npm_prefix}'\n", encoding="utf-8")
    npm.chmod(npm.stat().st_mode | stat.S_IXUSR)

    across_context = npm_bin / "across-context"
    across_context.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    across_context.chmod(across_context.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("ACROSS_BIN_HOME", str(tmp_path / "empty-across-bin"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    manager = MCPClientManager()
    manager.register_server(
        "across_context",
        "across-context",
        ["mcp"],
        env={"PATH": str(homebrew_bin)},
    )

    assert manager.server_configs["across_context"].command == str(across_context)


@pytest.mark.asyncio
async def test_across_context_native_connect_exposes_standard_tools(tmp_path):
    across_context = tmp_path / "across-context"
    across_context.write_text("#!/bin/sh\nprintf 'Across Context test CLI\\n'\n", encoding="utf-8")
    across_context.chmod(across_context.stat().st_mode | stat.S_IXUSR)

    manager = MCPClientManager()
    manager.register_server("across_context", str(across_context), ["mcp"])

    success, error = await manager.connect_server("across_context")

    assert success, error
    assert "across_context" in manager.sessions
    assert "across_context" in manager._native_across_context_servers

    tool_names = {tool["name"] for tool in manager.get_all_tools_schema()}
    assert "across_context__remember_context" in tool_names
    assert "across_context__search_context" in tool_names
    assert "across_context__export_agent_instructions" in tool_names


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


def test_across_context_memory_write_tools_are_high_risk():
    manager = MCPClientManager()

    assert manager._infer_tool_risk_level(
        "across_context",
        "remember_context",
        "Store a durable memory in the local Across Context vault.",
    ) == "high"
    assert manager._infer_tool_risk_level(
        "across_context",
        "approve_memory",
        "Approve a pending memory so agents can use it as active context.",
    ) == "high"
    assert manager._infer_tool_risk_level(
        "across_context",
        "search_context",
        "Search global and project memory for relevant context.",
    ) == "medium"


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

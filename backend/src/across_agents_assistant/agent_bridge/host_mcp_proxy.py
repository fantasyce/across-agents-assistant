from __future__ import annotations

import asyncio
import http.client
import json
import socket
import sys
from pathlib import Path
from typing import Any, Callable

from mcp import types
from mcp.server import InitializationOptions, NotificationOptions, Server
from mcp.server.stdio import stdio_server

from ..paths import backend_socket_path


class _UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, *, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        connection.connect(self._socket_path)
        self.sock = connection


def _request_json(method: str, path: str, payload: Any = None) -> Any:
    connection = _UnixSocketHTTPConnection(backend_socket_path(), timeout=30.0)
    body = None if payload is None else json.dumps(payload, separators=(",", ":"))
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
    finally:
        connection.close()
    decoded = json.loads(raw.decode("utf-8")) if raw else None
    if response.status < 200 or response.status >= 300:
        detail = decoded.get("detail") if isinstance(decoded, dict) else None
        raise RuntimeError(str(detail or f"AAA host API returned HTTP {response.status}"))
    return decoded


class HostMCPToolProvider:
    def __init__(self, *, request_json: Callable[..., Any] | None = None):
        self._request_json = request_json or _request_json

    def get_all_tools_schema(self):
        try:
            payload = self._request_json("GET", "/api/agent-bridge/mcp-tools")
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            return []
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    def call_tool(self, tool_name, arguments):
        result = self._request_json(
            "POST",
            "/api/agent-bridge/mcp-tools/call",
            {"tool_name": tool_name, "arguments": dict(arguments or {})},
        )
        if not isinstance(result, dict) or "output" not in result:
            raise RuntimeError("AAA host API returned an invalid MCP tool result")
        return result


def host_mcp_proxy_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "host-mcp-proxy"]
    backend_main = Path(__file__).resolve().parents[3] / "main.py"
    source_root = backend_main.parent / "src"
    return [
        "/usr/bin/env",
        f"PYTHONPATH={source_root}",
        sys.executable,
        str(backend_main),
        "host-mcp-proxy",
    ]


class HostMCPStdioProxy:
    """Expose the host's fail-closed read-only MCP inventory over stdio."""

    def __init__(self, provider: HostMCPToolProvider | Any | None = None):
        self.provider = provider or HostMCPToolProvider()

    def list_tools(self) -> list[types.Tool]:
        tools: list[types.Tool] = []
        for schema in self.provider.get_all_tools_schema():
            annotations = dict(schema.get("annotations") or {})
            tools.append(
                types.Tool(
                    name=str(schema.get("name") or ""),
                    description=str(schema.get("description") or ""),
                    inputSchema=dict(schema.get("parameters") or {"type": "object", "properties": {}}),
                    annotations=types.ToolAnnotations(
                        readOnlyHint=annotations.get("readOnlyHint") is True,
                        destructiveHint=annotations.get("destructiveHint") is not False,
                        openWorldHint=annotations.get("openWorldHint") is not False,
                    ),
                )
            )
        return tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        result = self.provider.call_tool(tool_name, arguments)
        return str(result["output"])


async def _run_host_mcp_stdio_proxy() -> None:
    proxy = HostMCPStdioProxy()
    server = Server("across-agents-assistant-readonly-host-tools")

    @server.list_tools()
    async def list_tools():
        return proxy.list_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None):
        return [types.TextContent(type="text", text=proxy.call_tool(name, dict(arguments or {})))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="across-agents-assistant-readonly-host-tools",
                server_version="1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def run_host_mcp_stdio_proxy() -> int:
    asyncio.run(_run_host_mcp_stdio_proxy())
    return 0

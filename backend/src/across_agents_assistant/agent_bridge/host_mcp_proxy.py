from __future__ import annotations

import http.client
import json
import socket
from typing import Any, Callable

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

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("across_agents_assistant.mcp")

RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
HIGH_RISK_TOOL_KEYWORDS = [
    "write",
    "create",
    "delete",
    "remove",
    "move",
    "rename",
    "edit",
    "update",
    "save",
    "execute",
    "run",
    "shell",
    "terminal",
    "command",
    "install",
    "publish",
]


class MCPClientManager:
    """Manages connections to multiple MCP servers."""
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stacks = {}
        self.server_configs: Dict[str, StdioServerParameters] = {}
        self.server_tools: Dict[str, List[Dict[str, Any]]] = {}
        self._connecting: set = set()

    def register_server(self, server_id: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None,
                        allowed_paths: Optional[List[str]] = None, readonly: bool = False):
        """Register a new MCP server configuration."""
        import shutil
        import os

        # Merge with global os.environ to ensure PATH is included
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        # Try to resolve the command to its absolute path to prevent "command not found" errors
        resolved_command = shutil.which(command, path=merged_env.get("PATH"))
        if resolved_command:
            command = resolved_command
        else:
            logger.error(f"MCP command not found: {command}. PATH: {merged_env.get('PATH', 'not set')}")

        self.server_configs[server_id] = StdioServerParameters(
            command=command,
            args=args,
            env=merged_env
        )

        # Store sandbox settings
        if not hasattr(self, '_sandbox_settings'):
            self._sandbox_settings = {}
        self._sandbox_settings[server_id] = {
            'allowed_paths': allowed_paths or [],
            'readonly': readonly
        }

    async def connect_server(self, server_id: str):
        """Connect to an MCP server and fetch its tools.

        Returns:
            tuple: (success: bool, error_message: Optional[str])
        """
        if server_id not in self.server_configs:
            error_msg = f"MCP server {server_id} not registered."
            logger.error(error_msg)
            return False, error_msg

        if server_id in self.sessions:
            logger.info(f"Already connected to MCP server {server_id}.")
            return True, None

        if server_id in self._connecting:
            logger.info(f"Already connecting to MCP server {server_id}, ignoring duplicate request.")
            # We could wait for the connection to finish, but returning True simplifies things for now
            return True, None

        self._connecting.add(server_id)

        params = self.server_configs[server_id]
        logger.info(f"Connecting to MCP server {server_id} via {params.command} {' '.join(params.args)}")

        try:
            # We use AsyncExitStack manually to manage the context managers
            from contextlib import AsyncExitStack
            stack = AsyncExitStack()
            self._exit_stacks[server_id] = stack

            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            self.sessions[server_id] = session
            logger.info(f"Successfully connected and initialized MCP server {server_id}.")

            # Fetch tools
            tools_response = await session.list_tools()
            self.server_tools[server_id] = []
            for t in tools_response.tools:
                risk_level = self._infer_tool_risk_level(server_id, t.name, t.description or "")
                # Convert the tool definition to our internal format
                self.server_tools[server_id].append({
                    "name": f"{server_id}__{t.name}", # Prefix with server_id to avoid conflicts
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                    "risk_level": risk_level,
                    "original_name": t.name
                })
            logger.info(f"Fetched {len(self.server_tools[server_id])} tools from {server_id}.")
            self._connecting.remove(server_id)
            return True, None

        except Exception as e:
            error_msg = f"Failed to connect to MCP server {server_id}: {e}"
            logger.error(error_msg)
            if server_id in self._exit_stacks:
                await self._exit_stacks[server_id].aclose()
                del self._exit_stacks[server_id]
            if server_id in self._connecting:
                self._connecting.remove(server_id)
            return False, error_msg

    async def disconnect_server(self, server_id: str):
        """Disconnect from an MCP server."""
        if server_id in self.sessions:
            del self.sessions[server_id]
        if server_id in self._exit_stacks:
            await self._exit_stacks[server_id].aclose()
            del self._exit_stacks[server_id]
        if server_id in self.server_tools:
            del self.server_tools[server_id]
        logger.info(f"Disconnected from MCP server {server_id}.")

    async def call_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on a connected MCP server."""
        if server_id not in self.sessions:
            logger.error(f"Cannot call tool: not connected to {server_id}")
            return f"Error: Not connected to MCP server {server_id}"

        # Sandbox validation
        sandbox = getattr(self, '_sandbox_settings', {}).get(server_id, {})
        if sandbox.get('readonly') and self._is_write_operation(tool_name, arguments):
            return "Error: This MCP server is in readonly mode. Write operations are not allowed."
        if sandbox.get('allowed_paths'):
            file_args = self._extract_file_paths(arguments)
            for file_path in file_args:
                if not self._is_path_allowed(file_path, sandbox.get('allowed_paths', [])):
                    return f"Error: Access to path '{file_path}' is not allowed. Allowed paths: {sandbox['allowed_paths']}"

        session = self.sessions[server_id]
        logger.info(f"Calling MCP tool {tool_name} on {server_id} with args {arguments}")

        try:
            result = await session.call_tool(tool_name, arguments=arguments)
            # The result is a CallToolResult object which contains a list of contents
            texts = []
            for content in result.content:
                if content.type == "text":
                    texts.append(content.text)
                else:
                    texts.append(f"[{content.type} content]")

            # Echo the underlying command for debugging transparency
            echo_info = f"【执行的命令】\n工具: {tool_name}\n参数: {json.dumps(arguments, ensure_ascii=False, indent=2)}"
            result_text = "\n".join(texts)
            full_result = f"{echo_info}\n\n【执行结果】\n{result_text}"

            if result.isError:
                logger.warning(f"MCP tool {tool_name} returned error: {texts}")
                return f"Error from tool: {''.join(texts)}\n\n{echo_info}"

            return full_result
        except Exception as e:
            logger.error(f"Exception calling MCP tool {tool_name}: {e}")
            return f"Error executing tool: {e}"

    def _extract_file_paths(self, arguments: Dict[str, Any]) -> List[str]:
        """Extract file paths from tool arguments."""
        paths = []
        for value in arguments.values():
            if isinstance(value, str) and (value.startswith('/') or value.startswith('~')):
                paths.append(value)
        return paths

    def _is_path_allowed(self, path: str, allowed_paths: List[str]) -> bool:
        """Check if a path is within allowed_paths."""
        import os
        abs_path = os.path.abspath(os.path.expanduser(path))
        for allowed in allowed_paths:
            abs_allowed = os.path.abspath(os.path.expanduser(allowed))
            try:
                if os.path.commonpath([abs_path, abs_allowed]) == abs_allowed:
                    return True
            except ValueError:
                continue
            if abs_path == abs_allowed:
                return True
        return False

    def _is_write_operation(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Check if a tool call is a write operation."""
        tool_lower = tool_name.lower()
        for keyword in HIGH_RISK_TOOL_KEYWORDS:
            if keyword in tool_lower:
                return True
        return False

    def _normalize_risk_level(self, risk_level: Optional[str]) -> str:
        normalized = str(risk_level or "medium").strip().lower()
        return normalized if normalized in RISK_ORDER else "medium"

    def _higher_risk_level(self, first: Optional[str], second: Optional[str]) -> str:
        left = self._normalize_risk_level(first)
        right = self._normalize_risk_level(second)
        return left if RISK_ORDER[left] >= RISK_ORDER[right] else right

    def _infer_tool_risk_level(self, server_id: str, tool_name: str, description: str = "") -> str:
        text = f"{server_id} {tool_name} {description}".lower()
        if any(keyword in text for keyword in HIGH_RISK_TOOL_KEYWORDS):
            return "high"
        return "medium"

    def _tool_safety_labels(
        self,
        server_id: str,
        tool_name: str,
        risk_level: str,
        sandbox: Dict[str, Any],
    ) -> List[str]:
        labels = ["mcp"]
        if self._is_write_operation(tool_name, {}):
            labels.append("write-capable")
        if sandbox.get("readonly"):
            labels.append("readonly")
        if sandbox.get("allowed_paths"):
            labels.append("path-scoped")
        if risk_level != "low":
            labels.append("requires-approval")
        return labels

    def get_all_tools_schema(self) -> List[Dict[str, Any]]:
        """Get all tools from all connected servers in the format expected by the LLM."""
        all_tools = []
        for server_id, tools in self.server_tools.items():
            sandbox = getattr(self, "_sandbox_settings", {}).get(server_id, {})
            for t in tools:
                original_name = t.get("original_name") or t["name"].split("__", 1)[-1]
                risk_level = self._higher_risk_level(
                    t.get("risk_level"),
                    self._infer_tool_risk_level(server_id, original_name, t.get("description", "")),
                )
                all_tools.append({
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                    "risk_level": risk_level,
                    "source": "mcp",
                    "server_id": server_id,
                    "original_name": original_name,
                    "requires_approval": risk_level != "low",
                    "safety_labels": self._tool_safety_labels(server_id, original_name, risk_level, sandbox),
                    "sandbox": {
                        "allowed_paths": list(sandbox.get("allowed_paths") or []),
                        "readonly": bool(sandbox.get("readonly", False)),
                    },
                })
        return all_tools

# Global instance
mcp_manager = MCPClientManager()

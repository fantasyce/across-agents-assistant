import asyncio
import logging
import json
import os
import shutil
import subprocess
from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .across_context_native import call_across_context_tool
from ..paths import ecosystem_bin_dir, ecosystem_home, ecosystem_plugin_root

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
    "store",
    "remember",
    "approve",
    "archive",
    "expire",
    "forget",
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
        self._native_across_context_servers: set[str] = set()
        self._external_across_context_servers: set[str] = set()
        self._server_implementations: Dict[str, str] = {}
        self._server_connection_notes: Dict[str, str] = {}

    def register_server(self, server_id: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None,
                        allowed_paths: Optional[List[str]] = None, readonly: bool = False):
        """Register a new MCP server configuration."""
        # Merge with global os.environ to ensure PATH is included
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        merged_env["PATH"] = self._command_search_path(merged_env.get("PATH", ""))

        # Try to resolve the command to its absolute path to prevent "command not found" errors
        resolved_command = shutil.which(command, path=merged_env.get("PATH"))
        if resolved_command:
            command = resolved_command
        else:
            if self._is_across_context_command_name(command):
                logger.info(
                    "Across Context CLI not found on PATH; auto mode can use built-in "
                    "compatibility. PATH: %s",
                    merged_env.get("PATH", "not set"),
                )
            else:
                logger.error(f"MCP command not found: {command}. PATH: {merged_env.get('PATH', 'not set')}")

        if server_id == "across_context":
            merged_env = self._privacy_safe_across_context_env(merged_env)

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

    def _command_search_path(self, current_path: str) -> str:
        plugin_bin = str(ecosystem_bin_dir())
        legacy_plugin_bin = os.path.expanduser("~/.across_agents/plugins/bin")
        paths = [plugin_bin]
        if legacy_plugin_bin != plugin_bin:
            paths.append(legacy_plugin_bin)
        paths.extend(
            path
            for path in str(current_path or "").split(os.pathsep)
            if path and path not in paths
        )
        for path in [
            os.path.expanduser("~/.local/bin"),
            os.path.expanduser("~/.npm-global/bin"),
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/usr/local/bin",
            "/usr/local/sbin",
        ]:
            if path not in paths:
                paths.append(path)

        npm = self._which_in_paths("npm", paths)
        npm_global_bin = self._npm_global_bin(npm, paths)
        if npm_global_bin and npm_global_bin not in paths:
            paths.append(npm_global_bin)

        return os.pathsep.join(paths)

    def _privacy_safe_across_context_env(self, env: Dict[str, str]) -> Dict[str, str]:
        base_keys = {
            "HOME",
            "USER",
            "LOGNAME",
            "PATH",
            "SHELL",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "TERM",
            "NO_COLOR",
            "SSH_AUTH_SOCK",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
        }
        safe_env = {
            key: value
            for key, value in env.items()
            if key in base_keys
            or key.startswith("ACROSS_CONTEXT_")
            or key.startswith("ACROSS_AGENTS_ACROSS_CONTEXT_")
            or key in {"ACROSS_HOME", "ACROSS_BIN_HOME", "ACROSS_PLUGIN_HOME"}
        }
        safe_env["PWD"] = "/"
        safe_env["OLDPWD"] = "/"
        safe_env.setdefault("ACROSS_HOME", str(ecosystem_home()))
        safe_env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root()))
        safe_env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir()))
        safe_env.setdefault("ACROSS_CONTEXT_HOME", str(ecosystem_home() / "data" / "across-context"))
        return safe_env

    def _which_in_paths(self, command: str, paths: List[str]) -> Optional[str]:
        import shutil

        return shutil.which(command, path=os.pathsep.join(paths))

    def _npm_global_bin(self, npm_command: Optional[str], paths: List[str]) -> Optional[str]:
        if not npm_command:
            return None
        try:
            result = subprocess.run(
                [npm_command, "prefix", "-g"],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
                env={**os.environ, "PATH": os.pathsep.join(paths)},
            )
        except Exception as exc:
            logger.debug("Unable to resolve npm global prefix from %s: %s", npm_command, exc)
            return None
        prefix = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if not prefix:
            return None
        return os.path.join(prefix, "bin")

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
            if self._is_across_context_cli_server(server_id, params):
                return await self._connect_across_context(server_id, params)

            return await self._connect_stdio_server(server_id, params, implementation="standard_mcp")
        finally:
            self._connecting.discard(server_id)

    async def disconnect_server(self, server_id: str):
        """Disconnect from an MCP server."""
        if server_id in self.sessions:
            del self.sessions[server_id]
        self._native_across_context_servers.discard(server_id)
        self._external_across_context_servers.discard(server_id)
        self._server_implementations.pop(server_id, None)
        self._server_connection_notes.pop(server_id, None)
        if server_id in self._exit_stacks:
            await self._exit_stacks[server_id].aclose()
            del self._exit_stacks[server_id]
        if server_id in self.server_tools:
            del self.server_tools[server_id]
        logger.info(f"Disconnected from MCP server {server_id}.")

    def get_server_implementation(self, server_id: str) -> Optional[str]:
        return self._server_implementations.get(server_id)

    def get_server_connection_note(self, server_id: str) -> Optional[str]:
        return self._server_connection_notes.get(server_id)

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

        if server_id in self._native_across_context_servers:
            return await asyncio.to_thread(
                self._call_across_context_native_tool,
                server_id,
                tool_name,
                arguments,
            )

        if server_id in self._external_across_context_servers:
            return await asyncio.to_thread(
                self._call_across_context_external_tool,
                server_id,
                tool_name,
                arguments,
            )

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

    def _is_across_context_cli_server(self, server_id: str, params: StdioServerParameters) -> bool:
        command_name = os.path.basename(str(params.command))
        return server_id == "across_context" and command_name == "across-context"

    def _is_across_context_command_name(self, command: str) -> bool:
        return os.path.basename(str(command)) == "across-context"

    async def _connect_across_context(self, server_id: str, params: StdioServerParameters):
        mode = self._across_context_mode(params)
        if mode in {"builtin", "native", "builtin_compatibility"}:
            return self._connect_across_context_native(
                server_id,
                "Forced built-in Across Context compatibility mode.",
            )

        if not self._command_is_executable(str(params.command), params.env or {}):
            error = (
                "The external Across Context MCP server is required but the "
                "`across-context` command is not installed or executable."
            )
            if mode == "external":
                logger.error(error)
                return False, error
            return self._connect_across_context_native(
                server_id,
                "`across-context` command was not found; using built-in compatibility mode.",
            )

        ok, error = self._connect_across_context_external(server_id, params)
        if ok:
            logger.info("Connected Across Context through external MCP plugin.")
            return True, None

        external_error = error or "unknown external MCP connection failure"
        if mode == "external":
            message = f"The external Across Context MCP server is required but failed to start: {external_error}"
            logger.error(message)
            return False, message

        logger.warning(
            "External Across Context MCP connection failed; falling back to built-in compatibility: %s",
            external_error,
        )
        return self._connect_across_context_native(
            server_id,
            f"External Across Context MCP failed: {external_error}",
        )

    def _connect_across_context_external(self, server_id: str, params: StdioServerParameters):
        timeout = self._across_context_connect_timeout(params)
        try:
            result = self._run_across_context_jsonrpc(
                params,
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                ],
                expected_id=2,
                timeout=timeout,
            )
        except Exception as exc:
            error_msg = f"Failed to connect to MCP server {server_id}: {exc}"
            logger.error(error_msg)
            return False, error_msg

        tools = result.get("tools") or []
        self.sessions[server_id] = None  # type: ignore[assignment]
        self.server_tools[server_id] = []
        for t in tools:
            name = str(t.get("name") or "")
            if not name:
                continue
            description = str(t.get("description") or "")
            risk_level = self._infer_tool_risk_level(server_id, name, description)
            self.server_tools[server_id].append({
                "name": f"{server_id}__{name}",
                "description": description,
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
                "risk_level": risk_level,
                "original_name": name,
            })
        self._external_across_context_servers.add(server_id)
        self._server_implementations[server_id] = "external"
        self._server_connection_notes[server_id] = "External Across Context MCP server."
        logger.info(
            "Connected Across Context external MCP server; registered %s tools.",
            len(self.server_tools[server_id]),
        )
        return True, None

    async def _connect_stdio_server(
        self,
        server_id: str,
        params: StdioServerParameters,
        *,
        implementation: str,
        timeout: Optional[float] = None,
    ):
        async def connect_once():
            from contextlib import AsyncExitStack

            stack = AsyncExitStack()
            self._exit_stacks[server_id] = stack

            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            self.sessions[server_id] = session
            logger.info(f"Successfully connected and initialized MCP server {server_id}.")

            tools_response = await session.list_tools()
            self.server_tools[server_id] = []
            for t in tools_response.tools:
                risk_level = self._infer_tool_risk_level(server_id, t.name, t.description or "")
                self.server_tools[server_id].append({
                    "name": f"{server_id}__{t.name}",
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                    "risk_level": risk_level,
                    "original_name": t.name
                })
            self._server_implementations[server_id] = implementation
            self._server_connection_notes.pop(server_id, None)
            logger.info(f"Fetched {len(self.server_tools[server_id])} tools from {server_id}.")

        try:
            if timeout is not None:
                async with asyncio.timeout(timeout):
                    await connect_once()
            else:
                await connect_once()
            return True, None
        except Exception as e:
            error_msg = f"Failed to connect to MCP server {server_id}: {e}"
            logger.error(error_msg)
            await self._cleanup_failed_connection(server_id)
            return False, error_msg

    async def _cleanup_failed_connection(self, server_id: str) -> None:
        if server_id in self._exit_stacks:
            await self._exit_stacks[server_id].aclose()
            del self._exit_stacks[server_id]
        self.sessions.pop(server_id, None)
        self.server_tools.pop(server_id, None)
        self._native_across_context_servers.discard(server_id)
        self._external_across_context_servers.discard(server_id)
        self._server_implementations.pop(server_id, None)

    def _connect_across_context_native(self, server_id: str, note: str):
        self.sessions[server_id] = None  # type: ignore[assignment]
        self.server_tools[server_id] = self._across_context_tool_definitions(server_id)
        self._native_across_context_servers.add(server_id)
        self._server_implementations[server_id] = "builtin_compatibility"
        self._server_connection_notes[server_id] = note
        logger.info(
            "Connected Across Context through built-in compatibility mode; "
            "registered %s tools. Reason: %s",
            len(self.server_tools[server_id]),
            note,
        )
        return True, None

    def _across_context_mode(self, params: StdioServerParameters) -> str:
        env = params.env or {}
        raw = env.get("ACROSS_AGENTS_ACROSS_CONTEXT_MODE") or os.environ.get("ACROSS_AGENTS_ACROSS_CONTEXT_MODE") or "auto"
        mode = str(raw).strip().lower().replace("-", "_")
        if mode in {"auto", "external", "builtin", "native", "builtin_compatibility"}:
            return mode
        logger.warning("Unknown Across Context mode %r; using auto.", raw)
        return "auto"

    def _across_context_connect_timeout(self, params: StdioServerParameters) -> float:
        env = params.env or {}
        raw = env.get("ACROSS_AGENTS_ACROSS_CONTEXT_CONNECT_TIMEOUT") or os.environ.get("ACROSS_AGENTS_ACROSS_CONTEXT_CONNECT_TIMEOUT") or "5"
        try:
            return max(0.5, float(raw))
        except ValueError:
            return 5.0

    def _command_is_executable(self, command: str, env: Dict[str, str]) -> bool:
        if os.path.isabs(command) or os.sep in command:
            return os.path.isfile(command) and os.access(command, os.X_OK)
        return shutil.which(command, path=env.get("PATH")) is not None

    def _across_context_tool_definitions(self, server_id: str) -> List[Dict[str, Any]]:
        return [
            {
                "name": f"{server_id}__remember_context",
                "description": "Store a user preference, project decision, command, note, or session summary in the local Across Context vault.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "scope": {"type": "string", "enum": ["global", "project"], "default": "global"},
                        "type": {
                            "type": "string",
                            "enum": ["preference", "decision", "note", "command", "session"],
                            "default": "note",
                        },
                        "projectRoot": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "auto": {"type": "boolean", "default": True},
                        "visibility": {"type": "string", "enum": ["private", "team"], "default": "private"},
                    },
                    "required": ["text"],
                },
                "risk_level": "high",
                "original_name": "remember_context",
            },
            {
                "name": f"{server_id}__search_context",
                "description": "Search global and project memory for relevant context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "projectRoot": {"type": "string"},
                        "limit": {"type": "number", "default": 10},
                        "mode": {"type": "string", "enum": ["keyword", "semantic", "hybrid"], "default": "hybrid"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "active", "pinned", "archived", "expired"],
                        },
                    },
                    "required": ["query"],
                },
                "risk_level": "medium",
                "original_name": "search_context",
            },
            {
                "name": f"{server_id}__get_project_context",
                "description": "Return an AGENTS.md style context document for the current project.",
                "parameters": {
                    "type": "object",
                    "properties": {"projectRoot": {"type": "string"}},
                    "required": ["projectRoot"],
                },
                "risk_level": "medium",
                "original_name": "get_project_context",
            },
            {
                "name": f"{server_id}__review_pending_memories",
                "description": "List automatic memory writes that are pending user review.",
                "parameters": {
                    "type": "object",
                    "properties": {"projectRoot": {"type": "string"}},
                },
                "risk_level": "high",
                "original_name": "review_pending_memories",
            },
            {
                "name": f"{server_id}__approve_memory",
                "description": "Approve a pending memory by id so agents can use it as active context.",
                "parameters": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                },
                "risk_level": "high",
                "original_name": "approve_memory",
            },
            {
                "name": f"{server_id}__get_agent_card",
                "description": "Return the Across Context agent card for A2A-style discovery.",
                "parameters": {"type": "object", "properties": {}},
                "risk_level": "medium",
                "original_name": "get_agent_card",
            },
            {
                "name": f"{server_id}__export_agent_instructions",
                "description": "Write AGENTS.md, CLAUDE.md, Cursor rules, or Markdown context exports for a project.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "projectRoot": {"type": "string"},
                        "target": {
                            "type": "string",
                            "enum": ["agents", "claude", "cursor", "markdown"],
                            "default": "agents",
                        },
                    },
                    "required": ["projectRoot"],
                },
                "risk_level": "high",
                "original_name": "export_agent_instructions",
            },
        ]

    def _call_across_context_native_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        params = self.server_configs.get(server_id)
        if params is None:
            return f"Error: MCP server {server_id} not registered."

        echo_info = f"【执行的命令】\n工具: {tool_name}\n参数: {json.dumps(arguments, ensure_ascii=False, indent=2)}"
        logger.info("Calling Across Context native tool %s with args %s", tool_name, arguments)

        try:
            output = call_across_context_tool(tool_name, arguments, env=params.env)
        except Exception as exc:
            logger.error("Exception calling Across Context native tool %s: %s", tool_name, exc)
            return f"Error executing tool: {exc}"

        return f"{echo_info}\n\n【执行结果】\n{output}"

    def _call_across_context_external_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        params = self.server_configs.get(server_id)
        if params is None:
            return f"Error: MCP server {server_id} not registered."

        echo_info = f"【执行的命令】\n工具: {tool_name}\n参数: {json.dumps(arguments, ensure_ascii=False, indent=2)}"
        logger.info("Calling Across Context external MCP tool %s with args %s", tool_name, arguments)

        try:
            result = self._run_across_context_jsonrpc(
                params,
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": arguments},
                    },
                ],
                expected_id=2,
                timeout=self._across_context_connect_timeout(params),
            )
        except Exception as exc:
            logger.error("Exception calling Across Context external MCP tool %s: %s", tool_name, exc)
            return f"Error executing tool: {exc}"

        texts = []
        for content in result.get("content") or []:
            if content.get("type") == "text":
                texts.append(str(content.get("text") or ""))
            else:
                texts.append(f"[{content.get('type') or 'unknown'} content]")
        output = "\n".join(texts)
        if result.get("isError"):
            return f"Error from tool: {output}\n\n{echo_info}"
        return f"{echo_info}\n\n【执行结果】\n{output}"

    def _run_across_context_jsonrpc(
        self,
        params: StdioServerParameters,
        messages: List[Dict[str, Any]],
        *,
        expected_id: int,
        timeout: float,
    ) -> Dict[str, Any]:
        command = [str(params.command), *list(params.args or [])]
        payload = "".join(json.dumps(message, ensure_ascii=False) + "\n" for message in messages)
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=params.env,
                cwd="/",
            )
            stdout, stderr = process.communicate(payload, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout, stderr = process.communicate(timeout=2)
            detail = (stderr or stdout or "").strip()
            raise TimeoutError(f"{' '.join(command)} timed out after {timeout:g}s. {detail}".strip()) from exc

        if process.returncode not in (0, None):
            detail = (stderr or stdout or "").strip()
            raise RuntimeError(detail or f"{' '.join(command)} exited with {process.returncode}")

        for line in stdout.splitlines():
            if not line.strip():
                continue
            response = json.loads(line)
            if response.get("id") != expected_id:
                continue
            if response.get("error"):
                error = response["error"]
                raise RuntimeError(str(error.get("message") or error))
            result = response.get("result")
            if isinstance(result, dict):
                return result
            raise RuntimeError(f"Invalid MCP response for id {expected_id}: {response}")

        detail = (stderr or stdout or "").strip()
        raise RuntimeError(detail or f"No MCP response for id {expected_id}")

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

    def get_safety_report(self) -> Dict[str, Any]:
        """Return an auditable MCP server safety summary for UI and task context."""
        servers: List[Dict[str, Any]] = []
        sandbox_settings = getattr(self, "_sandbox_settings", {})
        for server_id in sorted(set(self.server_tools.keys()) | set(self.server_configs.keys()) | set(sandbox_settings.keys())):
            tools = list(self.server_tools.get(server_id) or [])
            sandbox = sandbox_settings.get(server_id, {})
            risk_counts = {"high": 0, "low": 0, "medium": 0, "unknown": 0}
            write_capable = 0
            highest_risk = "low"
            for tool in tools:
                original_name = tool.get("original_name") or str(tool.get("name") or "").split("__", 1)[-1]
                risk = self._higher_risk_level(
                    tool.get("risk_level"),
                    self._infer_tool_risk_level(server_id, original_name, tool.get("description", "")),
                )
                risk_counts[risk] = risk_counts.get(risk, 0) + 1
                highest_risk = self._higher_risk_level(highest_risk, risk)
                if self._is_write_operation(original_name, {}):
                    write_capable += 1

            warnings: List[str] = []
            if risk_counts.get("high", 0):
                warnings.append("High-risk MCP tools require approval.")
            if sandbox.get("readonly") and write_capable:
                warnings.append("Readonly mode blocks write-capable tools at call time.")
            if not sandbox.get("readonly") and write_capable and not sandbox.get("allowed_paths"):
                warnings.append("Write-capable MCP tools are not path-scoped.")

            servers.append({
                "server_id": server_id,
                "connected": server_id in self.sessions,
                "implementation": self.get_server_implementation(server_id),
                "connection_note": self.get_server_connection_note(server_id),
                "tool_count": len(tools),
                "write_capable_tool_count": write_capable,
                "risk_counts": risk_counts,
                "highest_risk": highest_risk if tools else "unknown",
                "requires_approval_count": risk_counts.get("high", 0) + risk_counts.get("medium", 0),
                "sandbox": {
                    "allowed_paths": list(sandbox.get("allowed_paths") or []),
                    "readonly": bool(sandbox.get("readonly", False)),
                },
                "warnings": warnings,
            })

        return {
            "servers": servers,
            "server_count": len(servers),
            "connected_server_count": sum(1 for item in servers if item["connected"]),
            "high_risk_tool_count": sum(item["risk_counts"].get("high", 0) for item in servers),
            "write_capable_tool_count": sum(item["write_capable_tool_count"] for item in servers),
        }

# Global instance
mcp_manager = MCPClientManager()

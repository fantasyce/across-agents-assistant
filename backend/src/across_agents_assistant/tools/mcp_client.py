import asyncio
import logging
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ..paths import ecosystem_bin_dir, ecosystem_home, ecosystem_plugin_root
from ..runtime_boundary import (
    contains_protected_user_reference,
    expand_user,
    is_developer_mode,
    is_product_mode,
    sanitized_product_runtime_env,
)

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


class _OwnedMCPConnection:
    """Keep an AnyIO-backed stdio session inside one asyncio owner task."""

    def __init__(self, params: StdioServerParameters):
        self._params = params
        self._commands: asyncio.Queue = asyncio.Queue()
        self._ready = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(self._run())

    async def start(self):
        return await self._ready

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
        if self._task.done():
            raise RuntimeError("MCP connection is closed")
        result = asyncio.get_running_loop().create_future()
        await self._commands.put(("call", tool_name, dict(arguments or {}), result))
        return await result

    async def aclose(self) -> None:
        if self._task.done():
            await self._task
            return
        closed = asyncio.get_running_loop().create_future()
        await self._commands.put(("close", "", {}, closed))
        await closed
        await self._task

    async def abort(self) -> None:
        """Cancel a connection that did not finish starting, and reap its task."""
        if not self._task.done():
            self._task.cancel()
        try:
            await self._task
        except BaseException:
            pass

    async def _run(self) -> None:
        close_waiter = None
        try:
            from contextlib import AsyncExitStack

            async with AsyncExitStack() as stack:
                read, write = await stack.enter_async_context(stdio_client(self._params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools_response = await session.list_tools()
                if not self._ready.done():
                    self._ready.set_result(tools_response)

                while True:
                    operation, tool_name, arguments, waiter = await self._commands.get()
                    if operation == "close":
                        close_waiter = waiter
                        break
                    try:
                        result = await session.call_tool(tool_name, arguments=arguments)
                    except Exception as exc:
                        if not waiter.done():
                            waiter.set_exception(exc)
                    else:
                        if not waiter.done():
                            waiter.set_result(result)
        except BaseException as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)
            if close_waiter is not None and not close_waiter.done():
                close_waiter.set_exception(exc)
            raise
        else:
            if close_waiter is not None and not close_waiter.done():
                close_waiter.set_result(None)


class MCPClientManager:
    """Manages connections to multiple MCP servers."""
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stacks = {}
        self.server_configs: Dict[str, StdioServerParameters] = {}
        self.server_tools: Dict[str, List[Dict[str, Any]]] = {}
        self._connecting: set = set()
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
        merged_env["PATH"] = self._command_search_path(merged_env.get("PATH", ""), merged_env)

        # Try to resolve the command to its absolute path to prevent "command not found" errors
        resolved_command = self._resolve_command_path(
            command,
            merged_env,
            block_protected_product_path=server_id == "across_context",
        )
        if resolved_command:
            command = resolved_command
        else:
            if self._is_across_context_command_name(command):
                logger.info(
                    "Across Context CLI not found on PATH; the external plugin runtime "
                    "must be installed under the Across ecosystem directory. PATH: %s",
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

    def _command_search_path(self, current_path: str, env: Optional[Dict[str, str]] = None) -> str:
        source = env if env is not None else os.environ
        plugin_bin = str(ecosystem_bin_dir(source))
        paths = [plugin_bin]
        paths.extend(
            expand_user(path, source)
            for path in str(current_path or "").split(os.pathsep)
            if path and expand_user(path, source) not in paths
        )
        for path in [
            expand_user("~/.local/bin", source),
            expand_user("~/.npm-global/bin", source),
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/usr/local/bin",
            "/usr/local/sbin",
        ]:
            if path not in paths:
                paths.append(path)

        npm = self._which_in_paths("npm", paths, source)
        npm_global_bin = self._npm_global_bin(npm, paths, source)
        if npm_global_bin and npm_global_bin not in paths:
            paths.append(npm_global_bin)

        return os.pathsep.join(paths)

    def _privacy_safe_across_context_env(self, env: Dict[str, str]) -> Dict[str, str]:
        env, _runtime_boundary_issues = sanitized_product_runtime_env(env)
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
        safe_env.setdefault("ACROSS_HOME", str(ecosystem_home(safe_env)))
        safe_env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root(safe_env)))
        safe_env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir(safe_env)))
        safe_env.setdefault("ACROSS_CONTEXT_HOME", str(ecosystem_home(safe_env) / "data" / "across-context"))
        return safe_env

    def _which_in_paths(self, command: str, paths: List[str], env: Dict[str, str]) -> Optional[str]:
        for path in paths:
            candidate = str(Path(path) / command)
            if self._is_blocked_product_path(candidate, env):
                continue
            resolved = shutil.which(command, path=path)
            if resolved:
                return resolved
        return None

    def _npm_global_bin(self, npm_command: Optional[str], paths: List[str], env: Dict[str, str]) -> Optional[str]:
        if not npm_command:
            return None
        try:
            result = subprocess.run(
                [npm_command, "prefix", "-g"],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
                env={**os.environ, **env, "PATH": os.pathsep.join(self._safe_lookup_paths(paths, env))},
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
        session = self.sessions.pop(server_id, None)
        exit_stack = self._exit_stacks.pop(server_id, None)
        try:
            if isinstance(session, _OwnedMCPConnection):
                await session.aclose()
            if exit_stack is not None:
                await exit_stack.aclose()
        finally:
            self._external_across_context_servers.discard(server_id)
            self._server_implementations.pop(server_id, None)
            self._server_connection_notes.pop(server_id, None)
            self.server_tools.pop(server_id, None)
            logger.info(f"Disconnected from MCP server {server_id}.")

    async def shutdown(self) -> None:
        """Close every live stdio transport before the host process exits."""
        server_ids = set(self.sessions) | set(self._exit_stacks) | set(self.server_tools)
        for server_id in list(server_ids):
            try:
                await self.disconnect_server(server_id)
            except Exception:
                logger.warning("Failed to disconnect MCP server %s during shutdown.", server_id, exc_info=True)
        self._connecting.clear()

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

            if self._mcp_result_is_error(result):
                logger.warning(f"MCP tool {tool_name} returned error: {texts}")
                return f"Error from tool: {''.join(texts)}\n\n{echo_info}"

            return full_result
        except Exception as e:
            logger.error(f"Exception calling MCP tool {tool_name}: {e}")
            return f"Error executing tool: {e}"

    def _is_across_context_cli_server(self, server_id: str, params: StdioServerParameters) -> bool:
        command_name = os.path.basename(str(params.command))
        return server_id == "across_context" and command_name == "across-context"

    @staticmethod
    def _mcp_tool_input_schema(tool: Any) -> Dict[str, Any]:
        schema = getattr(tool, "inputSchema", None)
        if schema is None:
            schema = getattr(tool, "input_schema", None)
        return dict(schema) if isinstance(schema, dict) else {"type": "object", "properties": {}}

    @staticmethod
    def _mcp_tool_annotations(tool: Any) -> Dict[str, Any]:
        annotations = getattr(tool, "annotations", None)
        if hasattr(annotations, "model_dump"):
            annotations = annotations.model_dump(by_alias=True, exclude_none=True)
        return dict(annotations) if isinstance(annotations, dict) else {}

    @staticmethod
    def _mcp_result_is_error(result: Any) -> bool:
        value = getattr(result, "isError", None)
        if value is None:
            value = getattr(result, "is_error", False)
        return bool(value)

    def _is_across_context_command_name(self, command: str) -> bool:
        return os.path.basename(str(command)) == "across-context"

    async def _connect_across_context(self, server_id: str, params: StdioServerParameters):
        self._across_context_mode(params)

        if not self._command_is_executable(
            str(params.command),
            params.env or {},
            block_protected_product_path=True,
        ):
            error = (
                "The external Across Context MCP server is required but the "
                "`across-context` command is not installed or executable."
            )
            logger.error(error)
            return False, error

        integrity_issues = self._across_context_command_integrity_issues(str(params.command), params.env or {})
        if integrity_issues:
            error = (
                "The external Across Context MCP server must be repaired because "
                "its command references a protected user directory."
            )
            logger.error("%s Issues: %s", error, integrity_issues)
            return False, error

        # The external CLI handshake uses subprocess communication. Running it
        # directly inside this coroutine stalls every Unix-socket API request
        # until the plugin answers, which made the entire App appear frozen at
        # launch. Keep the host event loop responsive while the optional MCP
        # capability starts in the background.
        ok, error = await asyncio.to_thread(
            self._connect_across_context_external,
            server_id,
            params,
        )
        if ok:
            logger.info("Connected Across Context through external MCP plugin.")
            return True, None

        external_error = error or "unknown external MCP connection failure"
        message = f"The external Across Context MCP server is required but failed to start: {external_error}"
        logger.error(message)
        return False, message

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
                "annotations": dict(t.get("annotations") or {}),
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
            connection = _OwnedMCPConnection(params)
            self.sessions[server_id] = connection
            try:
                tools_response = await connection.start()
            except BaseException:
                self.sessions.pop(server_id, None)
                await connection.abort()
                raise
            if self.sessions.get(server_id) is not connection:
                raise RuntimeError(f"MCP server {server_id} was closed during startup")
            logger.info(f"Successfully connected and initialized MCP server {server_id}.")

            self.server_tools[server_id] = []
            for t in tools_response.tools:
                risk_level = self._infer_tool_risk_level(server_id, t.name, t.description or "")
                self.server_tools[server_id].append({
                    "name": f"{server_id}__{t.name}",
                    "description": t.description or "",
                    "parameters": self._mcp_tool_input_schema(t),
                    "risk_level": risk_level,
                    "original_name": t.name,
                    "annotations": self._mcp_tool_annotations(t),
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
        self._external_across_context_servers.discard(server_id)
        self._server_implementations.pop(server_id, None)

    def _across_context_mode(self, params: StdioServerParameters) -> str:
        env = params.env or {}
        raw = env.get("ACROSS_AGENTS_ACROSS_CONTEXT_MODE") or os.environ.get("ACROSS_AGENTS_ACROSS_CONTEXT_MODE") or "external"
        mode = str(raw).strip().lower().replace("-", "_")
        if mode == "external":
            return "external"
        logger.warning(
            "Across Context mode %r is not supported in the host; using external plugin mode.",
            raw,
        )
        return "external"

    def _across_context_connect_timeout(self, params: StdioServerParameters) -> float:
        env = params.env or {}
        raw = env.get("ACROSS_AGENTS_ACROSS_CONTEXT_CONNECT_TIMEOUT") or os.environ.get("ACROSS_AGENTS_ACROSS_CONTEXT_CONNECT_TIMEOUT") or "5"
        try:
            return max(0.5, float(raw))
        except ValueError:
            return 5.0

    def _command_is_executable(
        self,
        command: str,
        env: Dict[str, str],
        *,
        block_protected_product_path: bool = False,
    ) -> bool:
        return self._resolve_command_path(
            command,
            env,
            block_protected_product_path=block_protected_product_path,
        ) is not None

    def _resolve_command_path(
        self,
        command: str,
        env: Dict[str, str],
        *,
        block_protected_product_path: bool = False,
    ) -> Optional[str]:
        if not block_protected_product_path:
            return shutil.which(command, path=env.get("PATH"))
        if os.path.isabs(command) or os.sep in command:
            return self._resolve_direct_command_path(command, env)
        for path in self._safe_lookup_paths(str(env.get("PATH") or "").split(os.pathsep), env):
            resolved = shutil.which(command, path=path)
            if resolved:
                return resolved
        return None

    def _resolve_direct_command_path(self, command: str, env: Dict[str, str]) -> Optional[str]:
        expanded = expand_user(command, env)
        if not expanded or self._is_blocked_product_path(expanded, env):
            return None
        directory, name = os.path.split(os.path.normpath(expanded))
        if not directory or not name:
            return None
        if self._is_product_mode(env) and not self._is_developer_mode(env):
            if not self._is_managed_product_command_path(expanded, env):
                return None
        return shutil.which(name, path=directory)

    def _is_managed_product_command_path(self, value: str, env: Dict[str, str]) -> bool:
        roots = (
            ecosystem_bin_dir(env),
            ecosystem_plugin_root(env),
        )
        return any(self._is_under_path(value, root) for root in roots)

    def _is_under_path(self, value: str, root: Path) -> bool:
        try:
            child = os.path.abspath(value)
            parent = os.path.abspath(str(root))
            return os.path.commonpath([child, parent]) == parent
        except ValueError:
            return False

    def _safe_lookup_paths(self, paths: List[str], env: Dict[str, str]) -> List[str]:
        safe_paths: List[str] = []
        for path in paths:
            expanded = expand_user(path, env)
            if expanded and not self._is_blocked_product_path(str(Path(expanded) / ".__across_probe__"), env):
                safe_paths.append(expanded)
        return safe_paths

    def _is_blocked_product_path(self, value: str, env: Dict[str, str]) -> bool:
        return (
            self._is_product_mode(env)
            and not self._is_developer_mode(env)
            and contains_protected_user_reference(value, env)
        )

    def _is_product_mode(self, env: Dict[str, str]) -> bool:
        return is_product_mode(env) or str(env.get("ACROSS_CONTEXT_PRODUCT_MODE") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "y",
        }

    def _is_developer_mode(self, env: Dict[str, str]) -> bool:
        return is_developer_mode(env) or str(env.get("ACROSS_CONTEXT_DEVELOPER_MODE") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "y",
        }

    def _across_context_command_integrity_issues(self, command: str, env: Dict[str, str]) -> List[str]:
        resolved = self._resolve_command_path(command, env, block_protected_product_path=True)
        if not resolved:
            return ["command is not executable"]
        issues: List[str] = []
        if self._contains_protected_user_reference(resolved):
            issues.append("command path references a protected user directory")
        path = Path(resolved)
        try:
            if path.stat().st_size <= 64 * 1024:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if self._contains_protected_user_reference(text):
                    issues.append("command wrapper references a protected user directory")
        except Exception:
            pass
        return issues

    def _contains_protected_user_reference(self, value: str) -> bool:
        return contains_protected_user_reference(value)

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
        tokenized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(tool_name or ""))
        tokens = set(re.findall(r"[a-z0-9]+", tokenized.lower()))
        return any(keyword in tokens for keyword in HIGH_RISK_TOOL_KEYWORDS)

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
        *,
        declared_readonly: bool = False,
    ) -> List[str]:
        labels = ["mcp"]
        if not declared_readonly and self._is_write_operation(tool_name, {}):
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
                annotations = dict(t.get("annotations") or {})
                declared_readonly = (
                    bool(sandbox.get("readonly"))
                    and annotations.get("readOnlyHint") is True
                    and annotations.get("destructiveHint") is False
                )
                risk_level = "low" if declared_readonly else self._higher_risk_level(
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
                    "safety_labels": self._tool_safety_labels(
                        server_id,
                        original_name,
                        risk_level,
                        sandbox,
                        declared_readonly=declared_readonly,
                    ),
                    "annotations": annotations,
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

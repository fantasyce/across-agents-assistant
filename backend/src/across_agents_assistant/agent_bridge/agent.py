from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any

from ..agent_loop import ChatToolLoop, LoopConfig, LLMGatewayAdapter
from ..approval.executor import ToolExecutor
from ..llm_gateway.provider_registry import get_default_provider_ids
from ..tools.tool_registry import ToolRegistry, ToolDefinition, registry as global_tool_registry
from ..workspace_hygiene import is_workspace_noise_path
from .protocol import AgentResponse, InvokeRequest
from .errors import AgentException, AgentError

logger = logging.getLogger("across_agents_assistant.agent_bridge")

# Cloud LLM agents that should be invoked via LLMGateway instead of local CLI
CLOUD_LLM_AGENTS = set(get_default_provider_ids())

class AgentSession:
    """
    Manages a session with a single agent.

    Handles lifecycle (initialize, heartbeat, shutdown) and
    provides invoke() method for agent communication.
    """

    def __init__(
        self,
        agent_id: str,
        client: Any,
        llm_gateway: Any = None,
        tool_executor: Any = None,
        host_tool_provider: Any = None,
    ):
        self.agent_id = agent_id
        self._client = client
        self._llm_gateway = llm_gateway
        self._tool_executor = tool_executor
        self._host_tool_provider = host_tool_provider
        self._is_initialized = False
        self._last_heartbeat: float = 0
        self._session_metadata: Dict[str, Any] = {}

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def initialize(self) -> None:
        """Initialize the agent session."""
        if self._is_initialized:
            return

        try:
            logger.info(f"Initializing agent session: {self.agent_id}")
            # For now, just mark as initialized
            # In future, could do capability negotiation here
            self._is_initialized = True
            self._last_heartbeat = time.time()
            self._session_metadata["initialized_at"] = self._last_heartbeat
        except Exception as e:
            logger.error(f"Failed to initialize agent {self.agent_id}: {e}")
            raise AgentException.from_response(
                AgentResponse(
                    message_id="",
                    request_id="",
                    success=False,
                    error=str(e),
                    agent_id=self.agent_id
                )
            )

    def _client_send_accepts_timeout(self) -> bool:
        try:
            import inspect

            parameters = inspect.signature(self._client.send).parameters
            return "timeout" in parameters or any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in parameters.values()
            )
        except (TypeError, ValueError, AttributeError):
            return False

    def invoke(self, message: str, context: Optional[Dict[str, Any]] = None, timeout: float = 120.0, project_dir: Optional[str] = None) -> AgentResponse:
        """
        Invoke the agent with a message.

        Returns AgentResponse with success=True/False.
        """
        # Auto-initialize if not already
        if not self._is_initialized:
            self.initialize()

        request_id = f"req-{int(time.time() * 1000)}"
        start_time = time.time()

        try:
            logger.info(f"Invoking agent {self.agent_id}: {message[:50]}...")

            if self.agent_id in CLOUD_LLM_AGENTS:
                # Cloud LLM agent: use LLMGateway
                return self._invoke_cloud_llm(message, context, timeout, request_id, start_time, project_dir=project_dir)
            else:
                # Local CLI agent: use UniversalAgentClient
                return self._invoke_local_agent(message, context, timeout, request_id, start_time, project_dir)

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Agent {self.agent_id} invocation failed: {e}")
            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=False,
                error=str(e),
                agent_id=self.agent_id,
                elapsed_sec=elapsed
            )

    def _invoke_local_agent(self, message: str, context: Optional[Dict[str, Any]], timeout: float, request_id: str, start_time: float, project_dir: Optional[str] = None) -> AgentResponse:
        """Invoke a local CLI agent via UniversalAgentClient."""
        try:
            send_kwargs = {
                "message": self._build_execution_prompt(message, project_dir, context=context),
                "session_id": None,
                "use_current": True,
                "target_agent": self.agent_id,
                "project_dir": project_dir,
            }
            if self._client_send_accepts_timeout():
                send_kwargs["timeout"] = timeout
            reply = self._client.send(**send_kwargs)

            elapsed = time.time() - start_time

            if not reply or not reply.text:
                return AgentResponse(
                    message_id=f"msg-{int(time.time() * 1000)}",
                    request_id=request_id,
                    success=False,
                    error="Agent returned empty response",
                    agent_id=self.agent_id,
                    elapsed_sec=elapsed
                )

            is_error = "未找到" in reply.text or "未配置" in reply.text or "超时" in reply.text or "失败" in reply.text
            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=not is_error,
                output=reply.text if not is_error else "",
                error=reply.text if is_error else None,
                agent_id=self.agent_id,
                elapsed_sec=elapsed
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error(f"Agent {self.agent_id} timed out after {elapsed:.1f}s")
            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=False,
                error=f"Timeout after {timeout}s",
                agent_id=self.agent_id,
                elapsed_sec=elapsed
            )

    def _invoke_cloud_llm(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
        timeout: float,
        request_id: str,
        start_time: float,
        project_dir: Optional[str] = None,
    ) -> AgentResponse:
        """Invoke a Cloud LLM agent via LLMGateway."""
        if not self._llm_gateway:
            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=False,
                error=f"Cloud LLM agent {self.agent_id} not configured: no LLMGateway provided",
                agent_id=self.agent_id,
                elapsed_sec=time.time() - start_time
            )

        try:
            import concurrent.futures

            # Use a longer timeout for Cloud LLM agents to account for network latency
            # and complex code generation tasks
            effective_timeout = timeout if timeout > 120 else 180.0

            def _run_llm():
                # Use a dedicated event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    if self._should_use_cloud_tool_mode(context, project_dir):
                        return loop.run_until_complete(
                            self._run_cloud_tool_agent(
                                message=message,
                                context=context or {},
                                project_dir=project_dir,
                            )
                        )
                    return loop.run_until_complete(self._llm_gateway.chat(
                        message=self._build_execution_prompt(message, project_dir),
                        system_prompt="You are a coding assistant. Help implement the requested task.",
                        temperature=0.7,
                        provider_id=self.agent_id,
                    ))
                finally:
                    loop.close()

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(_run_llm)
            try:
                response = future.result(timeout=effective_timeout)
            except concurrent.futures.TimeoutError:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            except Exception:
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            else:
                executor.shutdown(wait=False, cancel_futures=True)

            elapsed = time.time() - start_time

            if isinstance(response, AgentResponse):
                response.request_id = request_id
                response.elapsed_sec = elapsed
                return response

            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=True,
                output=response.text if response and response.text else "",
                agent_id=self.agent_id,
                elapsed_sec=elapsed
            )

        except concurrent.futures.TimeoutError:
            elapsed = time.time() - start_time
            logger.error(f"Cloud LLM {self.agent_id} timed out after {elapsed:.1f}s")
            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=False,
                error=f"Timeout after {effective_timeout}s",
                agent_id=self.agent_id,
                elapsed_sec=elapsed
            )
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Cloud LLM {self.agent_id} invocation failed: {e}")
            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=False,
                error=str(e),
                agent_id=self.agent_id,
                elapsed_sec=elapsed
            )

    def _should_use_cloud_tool_mode(self, context: Optional[Dict[str, Any]], project_dir: Optional[str]) -> bool:
        if not project_dir:
            return False
        if context and context.get("disable_cloud_tool_mode"):
            return False
        return True

    async def _run_cloud_tool_agent(
        self,
        message: str,
        context: Dict[str, Any],
        project_dir: str,
    ) -> AgentResponse:
        before_snapshot = self._snapshot_project_files(project_dir)
        allowed_writable_files = self._normalize_allowed_writable_files(
            context.get("allowed_writable_files") or []
        )
        llm_adapter = LLMGatewayAdapter(self._llm_gateway, provider_id=self.agent_id)
        tool_registry = self._build_workspace_tool_registry(
            project_dir,
            allowed_writable_files=allowed_writable_files,
        )
        tool_executor = ToolExecutor(tool_registry, approval_service=None)
        llm_adapter.set_tools(tool_registry)

        loop = ChatToolLoop(
            llm_client=llm_adapter,
            tool_registry=tool_registry,
            config=LoopConfig(max_iterations=8),
            tool_executor=tool_executor,
        )
        result = await loop.run(
            user_message=self._build_cloud_tool_prompt(
                message,
                project_dir,
                allowed_writable_files=allowed_writable_files,
            ),
            context={
                "task_id": context.get("task_id", ""),
                "subtask_id": context.get("subtask_id", ""),
                "agent_id": self.agent_id,
                "user_description": message,
                "plan_summary": "cloud_tool_agent_execution",
                "context_sources": [project_dir],
            },
        )
        tool_results = list(result.tool_results or [])
        created_files: list[str] = []
        modified_files: list[str] = []
        tool_failures: list[dict[str, Any]] = []
        for item in tool_results:
            metadata = dict(item.get("metadata", {}) or {})
            for candidate in metadata.get("created_files", []) or []:
                if candidate not in created_files:
                    created_files.append(candidate)
            for candidate in metadata.get("modified_files", []) or []:
                if candidate not in modified_files:
                    modified_files.append(candidate)
            if not item.get("success", False):
                tool_failures.append({
                    "tool_name": item.get("tool_name"),
                    "message": item.get("message"),
                })

        observed_created, observed_modified = self._diff_project_files(project_dir, before_snapshot)
        for candidate in observed_created:
            if candidate not in created_files:
                created_files.append(candidate)
        for candidate in observed_modified:
            if candidate not in modified_files:
                modified_files.append(candidate)

        final_success, final_error, final_output = self._resolve_cloud_tool_outcome(
            result=result,
            created_files=created_files,
            modified_files=modified_files,
            tool_failures=tool_failures,
        )

        return AgentResponse(
            message_id=f"msg-{int(time.time() * 1000)}",
            request_id="",
            success=final_success,
            output=final_output,
            error=final_error,
            agent_id=self.agent_id,
            metadata={
                "tool_call_count": len(result.tool_calls or []),
                "tool_result_count": len(tool_results),
                "created_files": created_files,
                "modified_files": modified_files,
                "tool_failures": tool_failures,
                "observed_created_files": observed_created,
                "observed_modified_files": observed_modified,
                "allowed_writable_files": allowed_writable_files,
            },
        )

    def _resolve_cloud_tool_outcome(
        self,
        result: Any,
        created_files: list[str],
        modified_files: list[str],
        tool_failures: list[dict[str, Any]],
    ) -> tuple[bool, Optional[str], str]:
        final_success = result.success
        final_error = result.error
        final_output = result.final_answer

        converged_with_artifacts = bool(created_files or modified_files)
        tolerable_artifact_error = final_error in {"tool_execution_failed", "max_iterations_exceeded"}
        if final_error and "review diff" in str(final_error).lower():
            tolerable_artifact_error = True
        if not final_success and tolerable_artifact_error and converged_with_artifacts:
            final_success = True
            final_error = None
            final_output = self._summarize_cloud_tool_artifacts(created_files, modified_files)

        if tool_failures and not (created_files or modified_files):
            final_success = False
            final_error = final_error or "cloud_tool_execution_failed"

        return final_success, final_error, final_output

    @staticmethod
    def _summarize_cloud_tool_artifacts(created_files: list[str], modified_files: list[str]) -> str:
        parts = []
        if created_files:
            parts.append("Created files: " + ", ".join(created_files))
        if modified_files:
            parts.append("Modified files: " + ", ".join(modified_files))
        return "\n".join(parts) if parts else "Cloud tool execution completed."

    @staticmethod
    def _snapshot_project_files(project_dir: str) -> dict[str, float]:
        workspace = Path(project_dir)
        if not workspace.exists():
            return {}
        snapshot: dict[str, float] = {}
        workspace_root = str(workspace.resolve())
        for path in workspace.rglob("*"):
            if path.is_file():
                try:
                    resolved = str(path.resolve())
                    if is_workspace_noise_path(resolved, workspace_root):
                        continue
                    snapshot[resolved] = path.stat().st_mtime
                except OSError:
                    continue
        return snapshot

    @classmethod
    def _diff_project_files(cls, project_dir: str, before_snapshot: dict[str, float]) -> tuple[list[str], list[str]]:
        after_snapshot = cls._snapshot_project_files(project_dir)
        created = sorted(path for path in after_snapshot if path not in before_snapshot)
        modified = sorted(
            path
            for path, mtime in after_snapshot.items()
            if path in before_snapshot and mtime > before_snapshot[path]
        )
        return created, modified

    def _build_workspace_tool_registry(
        self,
        project_dir: str,
        allowed_writable_files: Optional[list[str]] = None,
    ) -> ToolRegistry:
        workspace = os.path.abspath(os.path.expanduser(project_dir))
        allowed_writable_files = self._normalize_allowed_writable_files(allowed_writable_files or [])
        local_registry = ToolRegistry()
        for tool_name in ("list_directory", "search_files", "read_file", "write_file", "edit_file"):
            tool = global_tool_registry.get_tool(tool_name)
            if not tool:
                continue
            description = f"{tool.description} Restricted to project_dir: {workspace}"
            if tool.name in {"write_file", "edit_file"} and allowed_writable_files:
                description += (
                    " This subtask may only write or edit these project-relative files: "
                    + ", ".join(allowed_writable_files)
                    + ". Reading other project files is allowed, but writing any other path is rejected."
                )
            if tool.name == "write_file":
                description += (
                    " For large files, keep each content argument below about 6000 characters: "
                    "write the first chunk with append=false, then write remaining chunks with append=true. "
                    "Do not send a whole large HTML/JS file in one tool call."
                )
            local_registry.register(ToolDefinition(
                name=tool.name,
                description=description,
                parameters=tool.parameters,
                risk_level="low",
                handler=self._wrap_workspace_tool(
                    tool.handler,
                    workspace,
                    allowed_writable_files=allowed_writable_files,
                ),
            ))
        if self._host_tool_provider:
            for schema in self._host_tool_provider.get_all_tools_schema():
                if schema.get("source") != "mcp":
                    continue
                if schema.get("risk_level") != "low" or schema.get("requires_approval") is not False:
                    continue
                if not (schema.get("sandbox") or {}).get("readonly"):
                    continue
                tool_name = str(schema.get("name") or "")
                if not tool_name or local_registry.get_tool(tool_name):
                    continue

                def call_host_tool(_tool_name=tool_name, **params):
                    return self._host_tool_provider.call_tool(_tool_name, params)

                local_registry.register(ToolDefinition(
                    name=tool_name,
                    description=str(schema.get("description") or ""),
                    parameters=dict(schema.get("parameters") or {"type": "object", "properties": {}}),
                    risk_level="low",
                    handler=call_host_tool,
                ))
        return local_registry

    def _wrap_workspace_tool(
        self,
        handler: Any,
        workspace: str,
        allowed_writable_files: Optional[list[str]] = None,
    ):
        allowed_paths = self._absolute_allowed_writable_paths(workspace, allowed_writable_files or [])

        def wrapped(**params):
            if "raw_arguments" in params:
                raw_arguments = params.pop("raw_arguments")
                try:
                    reparsed = json.loads(raw_arguments)
                    if isinstance(reparsed, dict):
                        for key, value in reparsed.items():
                            params.setdefault(key, value)
                except Exception:
                    logger.warning(
                        "Ignoring unparseable raw_arguments for tool %s: %r",
                        getattr(handler, "__name__", "unknown"),
                        raw_arguments,
                    )
            metadata: Dict[str, Any] = {}
            original_path = params.get("path")
            if "path" in params:
                params["path"] = self._resolve_workspace_path(params["path"], workspace)
                if handler.__name__ in {"write_file", "edit_file"} and allowed_paths:
                    self._assert_writable_path_allowed(
                        params["path"],
                        allowed_paths,
                        original_path or params["path"],
                    )
            result = handler(**params)
            resolved_path = params.get("path")
            if resolved_path:
                if handler.__name__ == "write_file":
                    metadata["created_files"] = [resolved_path]
                elif handler.__name__ == "edit_file":
                    metadata["modified_files"] = [resolved_path]
                elif handler.__name__ == "read_file":
                    metadata["read_files"] = [resolved_path]
            if original_path and original_path != resolved_path:
                metadata["requested_path"] = original_path
            return {"output": str(result), "metadata": metadata}
        return wrapped

    def _resolve_workspace_path(self, candidate: str, workspace: str) -> str:
        expanded = os.path.expanduser(candidate)
        if os.path.isabs(expanded):
            resolved = os.path.abspath(expanded)
        else:
            resolved = os.path.abspath(os.path.join(workspace, expanded))
        if resolved != workspace and not resolved.startswith(workspace + os.sep):
            raise ValueError(f"Path outside project_dir is not allowed: {candidate}")
        return resolved

    @staticmethod
    def _normalize_allowed_writable_files(files: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in files or []:
            text = str(item or "").replace("\\", "/").strip()
            if not text or os.path.isabs(text):
                continue
            cleaned = os.path.normpath(text).replace("\\", "/").strip("/")
            if cleaned in {"", "."} or cleaned == ".." or cleaned.startswith("../"):
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @classmethod
    def _absolute_allowed_writable_paths(cls, workspace: str, files: list[str]) -> set[str]:
        workspace_root = os.path.abspath(os.path.expanduser(workspace))
        allowed: set[str] = set()
        for rel_path in cls._normalize_allowed_writable_files(files):
            resolved = os.path.abspath(os.path.join(workspace_root, rel_path))
            if resolved == workspace_root or resolved.startswith(workspace_root + os.sep):
                allowed.add(resolved)
        return allowed

    @staticmethod
    def _assert_writable_path_allowed(candidate: str, allowed_paths: set[str], original_path: Any) -> None:
        resolved = os.path.abspath(os.path.expanduser(candidate))
        if resolved not in allowed_paths:
            allowed_display = ", ".join(sorted(allowed_paths))
            raise ValueError(
                "Path is outside this subtask's writable file assignment: "
                f"{original_path}. Allowed files: {allowed_display}"
            )

    def _build_cloud_tool_prompt(
        self,
        message: str,
        project_dir: str,
        allowed_writable_files: Optional[list[str]] = None,
    ) -> str:
        allowed_writable_files = self._normalize_allowed_writable_files(allowed_writable_files or [])
        writable_scope = ""
        if allowed_writable_files:
            writable_scope = (
                "Writable file assignment:\n"
                + "\n".join(f"- {path}" for path in allowed_writable_files)
                + "\nDo not create or edit any other files for this subtask. "
                "If another file looks necessary, mention it in the final summary instead of writing it.\n\n"
            )
        return (
            "You are a coding agent that must use tools to complete the task.\n"
            f"Project directory: {project_dir}\n"
            f"{writable_scope}"
            "Rules:\n"
            "1. Use the available tools to inspect and modify files inside the project directory.\n"
            "2. Do not claim files were created unless a tool actually created or edited them.\n"
            "3. Stay within the project directory.\n"
            "4. Do not ask the user clarifying questions during task execution.\n"
            "5. If the task is slightly ambiguous, choose the most standard implementation consistent with the task and continue.\n"
            "6. Stay within the exact scope of this subtask. Do not preemptively complete downstream subtasks or create deliverables that belong to other waves.\n"
            "7. When finished, summarize the concrete files created or modified.\n"
            "8. When writing large files, split the content across multiple write_file calls. "
            "Use append=false for the first chunk and append=true for later chunks; keep each chunk small enough that tool arguments are not truncated.\n\n"
            f"Task:\n{message}"
        )

    def _build_execution_prompt(
        self,
        message: str,
        project_dir: Optional[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        lines = [
            "You are executing a subtask inside an orchestrated multi-agent workflow.",
            "You must produce a concrete deliverable for this subtask now.",
            "Do not ask the user clarifying questions during execution.",
            "If the task has minor ambiguity, choose the most standard implementation consistent with the request and continue.",
            "If you make assumptions, keep them minimal and state them briefly in the final summary instead of asking questions first.",
            "If a project directory is provided, create or modify files there and stay within it.",
            "Stay within the exact scope of this subtask. Do not preemptively complete downstream subtasks or create deliverables that belong to other waves.",
        ]
        if project_dir:
            lines.append(f"Project directory: {project_dir}")
        allowed_writable_files = self._normalize_allowed_writable_files(
            (context or {}).get("allowed_writable_files") or []
        )
        if allowed_writable_files:
            lines.extend([
                "",
                "Writable file assignment:",
                *[f"- {path}" for path in allowed_writable_files],
                "Do not create or edit any other files for this subtask. If another file looks necessary, mention it in the final summary instead of writing it.",
            ])
        lines.append("")
        lines.append("Subtask:")
        lines.append(message)
        return "\n".join(lines)

    def heartbeat(self) -> bool:
        """
        Check if the agent is still alive.

        Returns True if agent responds to heartbeat.
        """
        if not self._is_initialized:
            return False

        try:
            # Simple check - just verify session exists
            self._last_heartbeat = time.time()
            return True
        except Exception as e:
            logger.warning(f"Heartbeat failed for {self.agent_id}: {e}")
            return False

    def shutdown(self) -> None:
        """Shutdown the agent session gracefully."""
        logger.info(f"Shutting down agent session: {self.agent_id}")
        self._is_initialized = False
        self._last_heartbeat = 0

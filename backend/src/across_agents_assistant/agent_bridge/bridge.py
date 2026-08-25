from __future__ import annotations
import logging
import time
import uuid
from typing import Dict, List, Optional, Any

from .protocol import AgentResponse, InvokeRequest, MessageType, AgentMessage
from .agent import AgentSession
from .result import TaskResult, SubtaskResult, ResultStatus
from .errors import AgentException, AgentError
from ..agent_ids import LOCAL_CLI_AGENT_IDS, normalize_agent_id
from ..llm_gateway.provider_registry import get_default_provider_ids

logger = logging.getLogger("across_agents_assistant.agent_bridge")

# Default agents
DEFAULT_AGENTS = [*LOCAL_CLI_AGENT_IDS, *get_default_provider_ids()]

class AgentBridge:
    """
    Main interface for Agent Bridge.

    Provides:
    - invoke(): Single agent invocation
    - batch_invoke(): Multiple agents in parallel
    - Task result tracking and aggregation
    - Lifecycle management for agent sessions
    """

    def __init__(
        self,
        local_agent_client: Any,
        llm_gateway: Any = None,
        tool_executor: Any = None,
        host_tool_provider: Any = None,
    ):
        self._client = local_agent_client
        self._llm_gateway = llm_gateway
        self._tool_executor = tool_executor
        self._host_tool_provider = host_tool_provider
        self._sessions: Dict[str, AgentSession] = {}
        self._task_results: Dict[str, TaskResult] = {}
        self._initialize_sessions()

    def _initialize_sessions(self) -> None:
        """Initialize sessions for all known agents."""
        for agent_id in DEFAULT_AGENTS:
            self._sessions[agent_id] = AgentSession(
                agent_id=agent_id,
                client=self._client,
                llm_gateway=self._llm_gateway,
                tool_executor=self._tool_executor,
                host_tool_provider=self._host_tool_provider,
            )
        logger.info(f"Initialized AgentBridge with {len(self._sessions)} agents")

    def get_agent_ids(self) -> List[str]:
        """Get list of available agent IDs."""
        return list(self._sessions.keys())

    def is_agent_available(self, agent_id: str) -> bool:
        """Check if an agent is available."""
        return agent_id in self._sessions

    def get_session(self, agent_id: str) -> Optional[AgentSession]:
        """Get the session for an agent."""
        return self._sessions.get(agent_id)

    def invoke(self, agent_id: str, message: str, context: Optional[Dict[str, Any]] = None, timeout: float = 120.0, project_dir: Optional[str] = None) -> AgentResponse:
        """
        Invoke a single agent.

        Args:
            agent_id: Target agent (openclaw/hermes/claude)
            message: Message to send
            context: Optional context dict
            timeout: Timeout in seconds
            project_dir: Optional project directory for file operations

        Returns:
            AgentResponse with success=True/False
        """
        agent_id = normalize_agent_id(agent_id) or agent_id
        logger.info(f"AgentBridge.invoke: agent_id={agent_id}, message_len={len(message) if message else 0}, timeout={timeout}")
        if agent_id not in self._sessions:
            return AgentResponse(
                message_id=f"msg-{uuid.uuid4().hex[:8]}",
                request_id=f"req-{uuid.uuid4().hex[:8]}",
                success=False,
                error=f"Unknown agent: {agent_id}",
                agent_id=agent_id
            )

        session = self._sessions[agent_id]
        response = session.invoke(message, context, timeout, project_dir=project_dir)
        logger.info(f"AgentBridge.invoke: agent_id={agent_id} completed, success={response.is_success if response else False}")
        return response

    def batch_invoke(self, requests: List[InvokeRequest]) -> List[AgentResponse]:
        """
        Invoke multiple agents in parallel.

        Args:
            requests: List of InvokeRequest objects

        Returns:
            List of AgentResponse objects (in same order as requests)
        """
        import concurrent.futures

        if not requests:
            return []

        responses = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(requests)) as executor:
            future_to_req_id = {
                executor.submit(self.invoke, req.agent_id, req.message, req.context, req.timeout): req.request_id
                for req in requests
            }

            for future in future_to_req_id:
                req_id = future_to_req_id[future]
                try:
                    response = future.result()
                except Exception as e:
                    response = AgentResponse(
                        message_id=f"msg-{uuid.uuid4().hex[:8]}",
                        request_id=req_id,
                        success=False,
                        error=str(e),
                        agent_id="unknown"
                    )
                responses.append(response)

        return responses

    def create_task_result(self, task_id: str, total_subtasks: int = 0) -> TaskResult:
        """Create a new task result tracker."""
        result = TaskResult(task_id=task_id, total_subtasks=total_subtasks)
        self._task_results[task_id] = result
        return result

    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """Get a task result by ID."""
        return self._task_results.get(task_id)

    def add_subtask_result(self, task_result: TaskResult, subtask_result: SubtaskResult) -> None:
        """Add a subtask result to a task result."""
        task_result.add_subtask_result(subtask_result)

    def shutdown(self) -> None:
        """Shutdown all agent sessions."""
        logger.info("Shutting down AgentBridge")
        for session in self._sessions.values():
            try:
                session.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down session {session.agent_id}: {e}")
        self._sessions.clear()

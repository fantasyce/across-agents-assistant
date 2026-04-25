from __future__ import annotations
import logging
import time
import uuid
from typing import Dict, List, Optional, Any

from .protocol import AgentResponse, InvokeRequest, MessageType, AgentMessage
from .agent import AgentSession
from .result import TaskResult, SubtaskResult, ResultStatus
from .errors import AgentException, AgentError

logger = logging.getLogger("across_agents_assistant.agent_bridge")

# Default agents
DEFAULT_AGENTS = ["openclaw", "hermes", "claude"]

class AgentBridge:
    """
    Main interface for Agent Bridge.

    Provides:
    - invoke(): Single agent invocation
    - batch_invoke(): Multiple agents in parallel
    - Task result tracking and aggregation
    - Lifecycle management for agent sessions
    """

    def __init__(self, openclaw_client: Any):
        self._client = openclaw_client
        self._sessions: Dict[str, AgentSession] = {}
        self._task_results: Dict[str, TaskResult] = {}
        self._initialize_sessions()

    def _initialize_sessions(self) -> None:
        """Initialize sessions for all known agents."""
        for agent_id in DEFAULT_AGENTS:
            self._sessions[agent_id] = AgentSession(
                agent_id=agent_id,
                client=self._client
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

    def invoke(self, agent_id: str, message: str, context: Optional[Dict[str, Any]] = None, timeout: float = 120.0) -> AgentResponse:
        """
        Invoke a single agent.

        Args:
            agent_id: Target agent (openclaw/hermes/claude)
            message: Message to send
            context: Optional context dict
            timeout: Timeout in seconds

        Returns:
            AgentResponse with success=True/False
        """
        if agent_id not in self._sessions:
            return AgentResponse(
                message_id=f"msg-{uuid.uuid4().hex[:8]}",
                request_id=f"req-{uuid.uuid4().hex[:8]}",
                success=False,
                error=f"Unknown agent: {agent_id}",
                agent_id=agent_id
            )

        session = self._sessions[agent_id]
        return session.invoke(message, context, timeout)

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

        responses = [None] * len(requests)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(requests)) as executor:
            future_to_req_id = {
                executor.submit(self.invoke, req.agent_id, req.message, req.context, req.timeout): req.request_id
                for req in requests
            }

            futures = [
                executor.submit(self.invoke, req.agent_id, req.message, req.context, req.timeout)
                for req in requests
            ]

            for idx, (future, req) in enumerate(zip(futures, requests)):
                try:
                    responses[idx] = future.result(timeout=req.timeout)
                except Exception as e:
                    responses[idx] = AgentResponse(
                        message_id=f"msg-{uuid.uuid4().hex[:8]}",
                        request_id=req.request_id,
                        success=False,
                        error=str(e),
                        agent_id=req.agent_id
                    )

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
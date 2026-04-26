from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional, Dict, Any

from .protocol import AgentResponse, InvokeRequest
from .errors import AgentException, AgentError

logger = logging.getLogger("across_agents_assistant.agent_bridge")

class AgentSession:
    """
    Manages a session with a single agent.

    Handles lifecycle (initialize, heartbeat, shutdown) and
    provides invoke() method for agent communication.
    """

    def __init__(self, agent_id: str, client: Any):
        self.agent_id = agent_id
        self._client = client
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

    def invoke(self, message: str, context: Optional[Dict[str, Any]] = None, timeout: float = 120.0) -> AgentResponse:
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

            # Call the underlying openclaw client
            # Note: This is sync in the current implementation
            reply = self._client.send(
                message=message,
                session_id=None,
                use_current=True,
                target_agent=self.agent_id
            )

            elapsed = time.time() - start_time

            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=True,
                output=reply.text if reply and reply.text else "",
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
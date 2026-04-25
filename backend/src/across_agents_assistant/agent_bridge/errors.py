from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .protocol import AgentResponse

class AgentError(str, Enum):
    """Standardized agent error types."""
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"
    INVALID_RESPONSE = "invalid_response"
    PROTOCOL_ERROR = "protocol_error"
    UNKNOWN = "unknown"

@dataclass
class AgentException(Exception):
    """Exception raised when agent operations fail."""
    error: AgentError
    agent_id: str
    message: str
    details: Optional[str] = None

    def __str__(self) -> str:
        return f"[{self.error.value}] {self.agent_id}: {self.message}"

    @classmethod
    def from_response(cls, response: AgentResponse) -> AgentException:
        """Create exception from failed agent response."""
        if response.error:
            msg = response.error
        else:
            msg = "Unknown error"

        # Try to classify the error
        error_type = AgentError.UNKNOWN
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            error_type = AgentError.TIMEOUT
        elif "unavailable" in msg.lower() or "not ready" in msg.lower():
            error_type = AgentError.UNAVAILABLE
        elif "cancelled" in msg.lower() or "cancel" in msg.lower():
            error_type = AgentError.CANCELLED
        elif "invalid" in msg.lower() or "parse" in msg.lower():
            error_type = AgentError.INVALID_RESPONSE

        return cls(
            error=error_type,
            agent_id=response.agent_id,
            message=msg,
            details=response.metadata.get("raw_error") if response.metadata else None
        )

    @classmethod
    def timeout(cls, agent_id: str, timeout_sec: float) -> AgentException:
        timeout_str = str(int(timeout_sec)) if timeout_sec == int(timeout_sec) else str(timeout_sec)
        return cls(
            error=AgentError.TIMEOUT,
            agent_id=agent_id,
            message=f"Agent timed out after {timeout_str}s"
        )

    @classmethod
    def unavailable(cls, agent_id: str) -> AgentException:
        return cls(
            error=AgentError.UNAVAILABLE,
            agent_id=agent_id,
            message=f"Agent {agent_id} is not available"
        )

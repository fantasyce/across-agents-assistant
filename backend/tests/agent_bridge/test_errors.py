import pytest
from across_agents_assistant.agent_bridge.errors import AgentError, AgentException

def test_agent_error_enum():
    assert AgentError.TIMEOUT.value == "timeout"
    assert AgentError.UNAVAILABLE.value == "unavailable"
    assert AgentError.CANCELLED.value == "cancelled"
    assert AgentError.INVALID_RESPONSE.value == "invalid_response"
    assert AgentError.PROTOCOL_ERROR.value == "protocol_error"
    assert AgentError.UNKNOWN.value == "unknown"

def test_agent_exception_creation():
    exc = AgentException(
        error=AgentError.TIMEOUT,
        agent_id="openclaw",
        message="Agent timed out after 120s"
    )
    assert exc.error == AgentError.TIMEOUT
    assert exc.agent_id == "openclaw"
    assert "timed out" in exc.message

def test_agent_exception_str():
    exc = AgentException(
        error=AgentError.UNAVAILABLE,
        agent_id="claude",
        message="Agent not ready"
    )
    assert str(exc) == "[unavailable] claude: Agent not ready"

def test_agent_exception_from_response():
    from across_agents_assistant.agent_bridge.protocol import AgentResponse
    resp = AgentResponse(
        message_id="msg-1",
        request_id="req-1",
        success=False,
        error="Connection refused",
        agent_id="hermes"
    )
    exc = AgentException.from_response(resp)
    assert exc.error == AgentError.UNKNOWN
    assert exc.agent_id == "hermes"

def test_agent_exception_timeout_factory():
    exc = AgentException.timeout("openclaw", 120.0)
    assert exc.error == AgentError.TIMEOUT
    assert exc.agent_id == "openclaw"
    assert "120s" in exc.message

def test_agent_exception_unavailable_factory():
    exc = AgentException.unavailable("claude")
    assert exc.error == AgentError.UNAVAILABLE
    assert exc.agent_id == "claude"

def test_agent_exception_from_response_timeout():
    """Test timeout classification."""
    from across_agents_assistant.agent_bridge.protocol import AgentResponse
    resp = AgentResponse(
        message_id="msg-1",
        request_id="req-1",
        success=False,
        error="Connection timed out after 120s",
        agent_id="openclaw"
    )
    exc = AgentException.from_response(resp)
    assert exc.error == AgentError.TIMEOUT

def test_agent_exception_from_response_unavailable():
    """Test unavailable classification."""
    from across_agents_assistant.agent_bridge.protocol import AgentResponse
    resp = AgentResponse(
        message_id="msg-1",
        request_id="req-1",
        success=False,
        error="Agent not ready",
        agent_id="claude"
    )
    exc = AgentException.from_response(resp)
    assert exc.error == AgentError.UNAVAILABLE

def test_agent_exception_from_response_cancelled():
    """Test cancelled classification."""
    from across_agents_assistant.agent_bridge.protocol import AgentResponse
    resp = AgentResponse(
        message_id="msg-1",
        request_id="req-1",
        success=False,
        error="User cancelled request",
        agent_id="hermes"
    )
    exc = AgentException.from_response(resp)
    assert exc.error == AgentError.CANCELLED

def test_agent_exception_from_response_invalid():
    """Test invalid_response classification."""
    from across_agents_assistant.agent_bridge.protocol import AgentResponse
    resp = AgentResponse(
        message_id="msg-1",
        request_id="req-1",
        success=False,
        error="Invalid JSON response",
        agent_id="openclaw"
    )
    exc = AgentException.from_response(resp)
    assert exc.error == AgentError.INVALID_RESPONSE

def test_agent_exception_protocol_error():
    """Test protocol_error via factory."""
    exc = AgentException(
        error=AgentError.PROTOCOL_ERROR,
        agent_id="claude",
        message="Message schema mismatch"
    )
    assert exc.error == AgentError.PROTOCOL_ERROR
    assert str(exc) == "[protocol_error] claude: Message schema mismatch"

def test_agent_exception_with_details():
    """Test details field."""
    exc = AgentException(
        error=AgentError.TIMEOUT,
        agent_id="openclaw",
        message="Timed out",
        details="Connection closed at 120.5s"
    )
    assert exc.details == "Connection closed at 120.5s"

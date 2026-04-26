import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from across_agents_assistant.agent_bridge.agent import AgentSession

@pytest.fixture
def mock_openclaw_client():
    mock = MagicMock()
    mock.send = MagicMock(return_value=MagicMock(text="Agent response", session_id="sess-1"))
    return mock

def test_agent_session_creation():
    session = AgentSession(
        agent_id="openclaw",
        client=AsyncMock()
    )
    assert session.agent_id == "openclaw"
    assert session.is_initialized == False

def test_agent_session_initialize():
    session = AgentSession(
        agent_id="openclaw",
        client=AsyncMock()
    )
    session.initialize()
    assert session.is_initialized == True

def test_agent_session_invoke(mock_openclaw_client):
    session = AgentSession(
        agent_id="openclaw",
        client=mock_openclaw_client
    )
    session.initialize()
    response = session.invoke("帮我分析代码")
    assert response.success == True
    assert response.output == "Agent response"

def test_agent_session_invoke_before_init(mock_openclaw_client):
    session = AgentSession(
        agent_id="openclaw",
        client=mock_openclaw_client
    )
    # Should auto-initialize
    response = session.invoke("帮我分析代码")
    assert session.is_initialized == True
    assert response.success == True

def test_agent_session_invoke_error():
    mock_client = AsyncMock()
    mock_client.send = MagicMock(side_effect=Exception("Connection failed"))
    session = AgentSession(agent_id="claude", client=mock_client)
    session.initialize()
    response = session.invoke("分析代码")
    assert response.success == False
    assert "Connection failed" in response.error

def test_agent_session_heartbeat():
    mock_client = AsyncMock()
    session = AgentSession(agent_id="hermes", client=mock_client)
    session.initialize()
    is_alive = session.heartbeat()
    assert is_alive == True

def test_agent_session_shutdown():
    mock_client = AsyncMock()
    session = AgentSession(agent_id="openclaw", client=mock_client)
    session.initialize()
    session.shutdown()
    assert session.is_initialized == False
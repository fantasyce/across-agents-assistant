"""
Integration tests for AgentLoop with LLMGateway adapter and AuditLogger.

Run with: PYTHONPATH=backend/src:src pytest tests/integration/test_agent_loop.py -v
"""
import pytest

from unittest.mock import MagicMock, AsyncMock

from across_agents_assistant.agent_loop.agent_loop import AgentLoop, ChatMessage
from across_agents_assistant.agent_loop.adapter import LLMGatewayAdapter
from across_agents_assistant.agent_loop.config import LoopConfig, LoopResult
from across_agents_assistant.persistence.audit_logger import AuditLogger


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response."""
    return {
        'content': 'Hello! How can I help you?',
        'tool_calls': []
    }


@pytest.fixture
def mock_llm_with_tool_call():
    """Create a mock LLM that returns a tool call."""
    async def chat(*args, **kwargs):
        return {
            'content': '',
            'tool_calls': [
                {
                    'id': 'call-1',
                    'name': 'get_file_info',
                    'arguments': {'path': '/tmp/test.txt'}
                }
            ]
        }
    return AsyncMock(side_effect=chat)


@pytest.fixture
def mock_tools():
    """Create a mock tool registry."""
    tools = MagicMock()
    tools.get_tool.return_value = MagicMock(
        handler=lambda **kwargs: '{"size": 1024, "modified": "2024-01-01"}'
    )
    tools.get_all_tools_schema.return_value = [
        {
            'name': 'get_file_info',
            'description': 'Get file information',
            'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}}}
        }
    ]
    return tools


@pytest.fixture
def temp_db():
    """Create a temporary database for AuditLogger."""
    import tempfile
    import os
    fd, path = tempfile.mkstemp('.db')
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def audit_logger(temp_db):
    """Create an AuditLogger with temporary database."""
    return AuditLogger(temp_db)


def test_loop_config_defaults():
    """Test LoopConfig default values."""
    config = LoopConfig()
    assert config.max_iterations == 5
    assert config.iteration_timeout_sec == 120.0


def test_agent_loop_initialization(mock_llm_response, mock_tools):
    """Test AgentLoop initialization."""
    loop = AgentLoop(mock_llm_response, mock_tools)
    assert loop.llm == mock_llm_response
    assert loop.tools == mock_tools


def test_agent_loop_without_audit_logger(mock_llm_response, mock_tools):
    """Test AgentLoop works without AuditLogger."""
    loop = AgentLoop(mock_llm_response, mock_tools)
    assert loop._audit_logger is None


def test_agent_loop_with_audit_logger(mock_llm_response, mock_tools, audit_logger):
    """Test AgentLoop accepts AuditLogger parameter."""
    loop = AgentLoop(mock_llm_response, mock_tools, audit_logger=audit_logger)
    assert loop._audit_logger == audit_logger


@pytest.mark.asyncio
async def test_agent_loop_no_tool_calls(mock_llm_response, mock_tools):
    """Test AgentLoop when LLM returns no tool calls."""
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value=mock_llm_response)
    loop = AgentLoop(mock_llm, mock_tools)

    result = await loop.run("Hello!")

    assert result.success == True
    assert result.final_answer == "Hello! How can I help you?"
    assert result.iterations == 0


@pytest.mark.asyncio
async def test_agent_loop_with_tool_call(mock_llm_with_tool_call, mock_tools):
    """Test AgentLoop when LLM returns a tool call."""
    loop = AgentLoop(mock_llm_with_tool_call, mock_tools)

    result = await loop.run("Get file info")

    # First call returns tool call, need second call to return final answer
    assert result.iterations >= 1


def test_llm_gateway_adapter_basic():
    """Test LLMGatewayAdapter basic functionality."""
    mock_gateway = MagicMock()
    mock_gateway.chat = AsyncMock(return_value=MagicMock(
        text='Hello!',
        raw={'choices': [{'message': {'content': 'Hello!'}}]},
        model='test',
        provider='test'
    ))

    adapter = LLMGatewayAdapter(mock_gateway)

    messages = [{'role': 'user', 'content': 'Hi!'}]

    async def test():
        result = await adapter.chat(messages)
        assert result['content'] == 'Hello!'
        assert result['tool_calls'] == []

    import asyncio
    asyncio.run(test())


def test_llm_gateway_adapter_with_tools():
    """Test LLMGatewayAdapter with function calling."""
    mock_gateway = MagicMock()
    mock_gateway.chat = AsyncMock(return_value=MagicMock(
        text='',
        raw={
            'choices': [{
                'message': {
                    'tool_calls': [
                        {
                            'id': 'call-123',
                            'function': {
                                'name': 'get_file_info',
                                'arguments': '{"path": "/tmp"}'
                            }
                        }
                    ]
                }
            }]
        },
        model='test',
        provider='test'
    ))

    adapter = LLMGatewayAdapter(mock_gateway)

    messages = [{'role': 'user', 'content': 'Get file info'}]

    async def test():
        result = await adapter.chat(messages)
        assert result['content'] == ''
        assert len(result['tool_calls']) == 1
        assert result['tool_calls'][0]['name'] == 'get_file_info'

    import asyncio
    asyncio.run(test())


def test_chat_message_dataclass():
    """Test ChatMessage dataclass."""
    msg = ChatMessage(role='user', content='Hello')
    assert msg.role == 'user'
    assert msg.content == 'Hello'
    assert msg.name is None
    assert msg.tool_calls is None


def test_loop_result_dataclass():
    """Test LoopResult dataclass."""
    result = LoopResult(
        final_answer='Done',
        iterations=2,
        tool_calls=[{'id': '1', 'name': 'test', 'arguments': '{}'}],
        success=True
    )
    assert result.final_answer == 'Done'
    assert result.iterations == 2
    assert result.success == True
    assert result.error is None

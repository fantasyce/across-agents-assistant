import pytest
from unittest.mock import AsyncMock, MagicMock
from across_agents_assistant.agent_loop.agent_loop import AgentLoop, ChatMessage
from across_agents_assistant.agent_loop.config import LoopConfig, LoopResult

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value={
        'content': 'Hello!',
        'tool_calls': []
    })
    return llm

@pytest.fixture
def mock_tools():
    tools = MagicMock()
    tools.get_tool.return_value = MagicMock(handler=lambda **k: "tool result")
    tools.get_all_tools_schema.return_value = []
    return tools

def test_loop_config_defaults():
    config = LoopConfig()
    assert config.max_iterations == 5
    assert config.iteration_timeout_sec == 120.0

def test_agent_loop_initialization(mock_llm, mock_tools):
    loop = AgentLoop(mock_llm, mock_tools)
    assert loop.llm == mock_llm
    assert loop.tools == mock_tools
    assert loop.config.max_iterations == 5

@pytest.mark.asyncio
async def test_agent_loop_no_tool_calls(mock_llm, mock_tools):
    loop = AgentLoop(mock_llm, mock_tools)
    result = await loop.run("Hello")
    assert result.success == True
    assert result.final_answer == "Hello!"
    assert result.iterations == 0

@pytest.mark.asyncio
async def test_agent_loop_with_tool_call(mock_llm, mock_tools):
    # 第一次返回 tool_call，第二次返回普通回答
    mock_llm.chat = AsyncMock(side_effect=[
        {'content': '', 'tool_calls': [{'id': 'call-1', 'name': 'list_directory', 'arguments': {'path': '~'}}]},
        {'content': 'Done!', 'tool_calls': []}
    ])

    loop = AgentLoop(mock_llm, mock_tools)
    result = await loop.run("List files")
    assert result.success == True
    assert result.iterations == 1
    assert len(result.tool_calls) == 1

@pytest.mark.asyncio
async def test_agent_loop_max_iterations(mock_llm, mock_tools):
    # 一直返回 tool_call
    mock_llm.chat = AsyncMock(return_value={
        'content': '',
        'tool_calls': [{'id': 'call-1', 'name': 'list_directory', 'arguments': {'path': '~'}}]
    })

    loop = AgentLoop(mock_llm, mock_tools, LoopConfig(max_iterations=2))
    result = await loop.run("List files")
    assert result.success == False
    assert result.error == "max_iterations_exceeded"
    assert result.iterations == 2
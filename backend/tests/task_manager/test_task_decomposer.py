import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from across_agents_assistant.task_manager.task_decomposer import TaskDecomposer
from across_agents_assistant.task_manager.models import Task, TaskType
from across_agents_assistant.llm_gateway.base_adapter import LLMResponse

@pytest.fixture
def mock_gateway():
    """Create a mock LLM gateway that returns structured JSON."""
    mock = AsyncMock()
    return mock

def test_decomposer_initialization(mock_gateway):
    decomposer = TaskDecomposer(mock_gateway)
    assert decomposer._gateway is not None
    assert decomposer._default_agents == ["openclaw", "hermes", "claude"]

def test_parse_llm_response_research():
    decomposer = TaskDecomposer(AsyncMock())
    json_str = '''{
        "task_type": "research",
        "can_handle_directly": false,
        "subtasks": [
            {"description": "搜索相关信息", "agent": "openclaw", "priority": 1},
            {"description": "整理搜索结果", "agent": "claude", "priority": 2}
        ]
    }'''
    result = decomposer._parse_llm_response(json_str)
    assert result is not None
    assert result["task_type"] == "research"
    assert len(result["subtasks"]) == 2

def test_parse_llm_response_simple_qa():
    decomposer = TaskDecomposer(AsyncMock())
    json_str = '''{
        "task_type": "simple_qa",
        "can_handle_directly": true,
        "direct_response": "这是直接回答",
        "subtasks": []
    }'''
    result = decomposer._parse_llm_response(json_str)
    assert result is not None
    assert result["can_handle_directly"] == True
    assert result["direct_response"] == "这是直接回答"

def test_parse_invalid_json():
    decomposer = TaskDecomposer(AsyncMock())
    result = decomposer._parse_llm_response("not valid json")
    assert result is None

def test_apply_decomposition_to_task():
    decomposer = TaskDecomposer(AsyncMock())
    task = Task.new("分析这个项目")
    decomposition = {
        "task_type": "code_review",
        "can_handle_directly": False,
        "subtasks": [
            {"description": "分析代码结构", "agent": "claude", "priority": 1},
            {"description": "检查代码规范", "agent": "openclaw", "priority": 2}
        ]
    }
    decomposer._apply_decomposition(task, decomposition)
    assert len(task.subtasks) == 2
    assert task.task_type == TaskType.CODE_REVIEW
    assert task.can_handle_directly == False

def test_validate_agent():
    decomposer = TaskDecomposer(AsyncMock())
    assert decomposer._validate_agent("openclaw") == "openclaw"
    assert decomposer._validate_agent("claude") == "claude"
    assert decomposer._validate_agent("hermes") == "hermes"
    assert decomposer._validate_agent("unknown") == "openclaw"  # Default fallback

def test_decompose_calls_llm(mock_gateway):
    """Test that decompose() calls LLM and applies results to task."""
    # Setup mock response
    mock_response = LLMResponse(
        text='{"task_type":"research","can_handle_directly":false,"subtasks":[{"description":"搜索信息","agent":"openclaw","priority":1}]}',
        raw={},
        model="MiniMax-Text-01",
        provider="minimax",
        finish_reason="stop"
    )
    mock_gateway.chat = AsyncMock(return_value=mock_response)

    decomposer = TaskDecomposer(mock_gateway)
    task = Task.new("帮我搜索信息")

    result = asyncio.run(decomposer.decompose(task))

    # Verify LLM was called
    mock_gateway.chat.assert_called_once()

    # Verify task was updated
    assert result.task_type == TaskType.RESEARCH
    assert result.can_handle_directly == False
    assert len(result.subtasks) == 1
    assert result.subtasks[0].description == "搜索信息"
    assert result.subtasks[0].agent_id == "openclaw"
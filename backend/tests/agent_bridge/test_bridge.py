import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from across_agents_assistant.agent_bridge.bridge import AgentBridge
from across_agents_assistant.agent_bridge.protocol import InvokeRequest
from across_agents_assistant.agent_bridge.result import TaskResult, ResultStatus, SubtaskResult

@pytest.fixture
def mock_openclaw_client():
    mock = MagicMock()
    mock.send = MagicMock(return_value=MagicMock(text="Response", session_id="sess-1"))
    return mock

@pytest.fixture
def bridge(mock_openclaw_client):
    return AgentBridge(openclaw_client=mock_openclaw_client)

def test_bridge_initialization(bridge):
    assert bridge.get_agent_ids() == ["openclaw", "hermes", "claude"]
    assert bridge.is_agent_available("openclaw") == True

def test_bridge_get_agent_session(bridge):
    session = bridge.get_session("claude")
    assert session is not None
    assert session.agent_id == "claude"

def test_bridge_invoke_single(bridge):
    response = bridge.invoke("openclaw", "分析代码")
    assert response.success == True
    assert response.output == "Response"

def test_bridge_batch_invoke(bridge):
    requests = [
        InvokeRequest.new("openclaw", "任务1"),
        InvokeRequest.new("claude", "任务2"),
        InvokeRequest.new("hermes", "任务3"),
    ]
    responses = bridge.batch_invoke(requests)
    assert len(responses) == 3
    assert all(r.success for r in responses)

def test_bridge_invoke_unknown_agent(bridge):
    response = bridge.invoke("unknown_agent", "测试")
    assert response.success == False
    assert "unknown" in response.error.lower()

def test_bridge_task_result_tracking(bridge):
    result = bridge.create_task_result("task-1", 2)
    assert result.task_id == "task-1"
    assert result.is_complete == False

def test_bridge_add_result_to_task(bridge):
    result = bridge.create_task_result("task-1", 2)
    bridge.add_subtask_result(result, SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="完成"
    ))
    assert result.completed_count == 1
    assert result.is_complete == False
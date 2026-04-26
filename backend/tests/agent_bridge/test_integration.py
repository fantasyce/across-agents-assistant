import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from across_agents_assistant.agent_bridge.bridge import AgentBridge
from across_agents_assistant.agent_bridge.protocol import InvokeRequest
from across_agents_assistant.agent_bridge.result import TaskResult, ResultStatus, SubtaskResult

def test_bridge_full_invoke_flow():
    """Test complete flow: create request, invoke, get response."""
    mock_client = MagicMock()
    mock_client.send = MagicMock(return_value=MagicMock(text="Analysis complete", session_id="sess-1"))

    bridge = AgentBridge(openclaw_client=mock_client)

    # Invoke
    response = bridge.invoke("claude", "Analyze this code")

    # Verify
    assert response.success == True
    assert response.output == "Analysis complete"
    assert response.agent_id == "claude"

def test_bridge_batch_invoke_parallel():
    """Test batch invoke runs in parallel."""
    mock_client = MagicMock()
    mock_client.send = MagicMock(return_value=MagicMock(text="Done", session_id="sess-1"))

    bridge = AgentBridge(openclaw_client=mock_client)

    requests = [
        InvokeRequest.new("openclaw", "Task 1"),
        InvokeRequest.new("hermes", "Task 2"),
        InvokeRequest.new("claude", "Task 3"),
    ]

    responses = bridge.batch_invoke(requests)

    assert len(responses) == 3
    assert all(r.success for r in responses)

def test_bridge_task_result_tracking():
    """Test task result aggregation."""
    mock_client = MagicMock()
    mock_client.send = MagicMock(return_value=MagicMock(text="Done", session_id="sess-1"))

    bridge = AgentBridge(openclaw_client=mock_client)

    # Create task with 2 subtasks
    task_result = bridge.create_task_result("task-1", total_subtasks=2)

    # Add subtask results
    bridge.add_subtask_result(task_result, SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="Part 1 done"
    ))

    assert task_result.completed_count == 1
    assert task_result.is_complete == False

    bridge.add_subtask_result(task_result, SubtaskResult(
        subtask_id="st-2",
        agent_id="openclaw",
        status=ResultStatus.COMPLETED,
        output="Part 2 done"
    ))

    assert task_result.is_complete == True
    assert task_result.progress == 1.0
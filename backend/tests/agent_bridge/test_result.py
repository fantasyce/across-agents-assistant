# backend/tests/agent_bridge/test_result.py
import pytest
from across_agents_assistant.agent_bridge.result import TaskResult, SubtaskResult, ResultStatus

def test_result_status_enum():
    assert ResultStatus.PENDING.value == "pending"
    assert ResultStatus.RUNNING.value == "running"
    assert ResultStatus.COMPLETED.value == "completed"
    assert ResultStatus.FAILED.value == "failed"
    assert ResultStatus.CANCELLED.value == "cancelled"

def test_subtask_result_creation():
    result = SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="分析完成"
    )
    assert result.subtask_id == "st-1"
    assert result.output == "分析完成"

def test_task_result_initial_state():
    result = TaskResult(task_id="task-1")
    assert result.task_id == "task-1"
    assert result.is_complete == False
    assert len(result.subtask_results) == 0

def test_task_result_add_subtask():
    result = TaskResult(task_id="task-1")
    result.add_subtask_result(SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="第一步完成"
    ))
    assert len(result.subtask_results) == 1
    assert result.is_complete == False  # Only 1 of 2

def test_task_result_all_complete():
    result = TaskResult(task_id="task-1", total_subtasks=2)
    result.add_subtask_result(SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="第一步完成"
    ))
    result.add_subtask_result(SubtaskResult(
        subtask_id="st-2",
        agent_id="openclaw",
        status=ResultStatus.COMPLETED,
        output="第二步完成"
    ))
    assert result.is_complete == True

def test_task_result_any_failed():
    result = TaskResult(task_id="task-1", total_subtasks=2)
    result.add_subtask_result(SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.FAILED,
        error="执行失败"
    ))
    assert result.has_failures == True
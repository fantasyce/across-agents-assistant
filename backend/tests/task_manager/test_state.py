import pytest
from across_agents_assistant.task_manager.state import TaskState
from across_agents_assistant.task_manager.models import Task, SubTask, Job, JobResult, JobStatus, TaskType

def test_task_state_initialization():
    state = TaskState()
    assert len(state.get_all_tasks()) == 0
    assert len(state.get_all_jobs()) == 0

def test_create_task():
    state = TaskState()
    task = state.create_task("帮我重构这个项目")
    assert task.task_id.startswith("task-")
    assert task.description == "帮我重构这个项目"

def test_add_subtask():
    state = TaskState()
    task = state.create_task("分析项目")
    subtask = state.add_subtask(task.task_id, "分析代码结构", "claude", priority=1)
    assert subtask.subtask_id.startswith("st-")
    assert subtask.agent_id == "claude"

def test_get_task():
    state = TaskState()
    task = state.create_task("测试任务")
    found = state.get_task(task.task_id)
    assert found is not None
    assert found.task_id == task.task_id

def test_get_nonexistent_task():
    state = TaskState()
    found = state.get_task("nonexistent")
    assert found is None

def test_create_job():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行任务", "openclaw")
    job = state.create_job(subtask)
    assert job.job_id.startswith("job-")
    assert job.status == JobStatus.PENDING

def test_update_job_progress():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行任务", "openclaw")
    job = state.create_job(subtask)
    updated = state.update_job_progress(job.job_id, progress=0.5, log="正在进行中...")
    assert updated is not None
    assert updated.progress == 0.5

def test_complete_job():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行任务", "openclaw")
    job = state.create_job(subtask)
    state.update_job_status(job.job_id, JobStatus.RUNNING)
    result = state.complete_job(job.job_id, success=True, output="完成")
    assert result.success == True
    assert state.get_job(job.job_id).status == JobStatus.COMPLETED

def test_get_task_progress():
    state = TaskState()
    task = state.create_task("测试")
    state.add_subtask(task.task_id, "子任务1", "openclaw")
    state.add_subtask(task.task_id, "子任务2", "claude")
    progress = state.get_task_progress(task.task_id)
    assert progress == 0.0  # All pending

def test_cancel_task():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行", "openclaw")
    job = state.create_job(subtask)
    cancelled = state.cancel_task(task.task_id)
    assert cancelled == True
    assert state.get_job(job.job_id).status == JobStatus.CANCELLED
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

def test_update_subtask_status():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行", "openclaw")
    updated = state.update_subtask_status(task.task_id, subtask.subtask_id, JobStatus.RUNNING)
    assert updated == True
    # Verify via task
    task = state.get_task(task.task_id)
    assert task.subtasks[0].status == JobStatus.RUNNING

def test_get_job_by_subtask():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行", "openclaw")
    job = state.create_job(subtask)
    found = state.get_job_by_subtask(subtask.subtask_id)
    assert found is not None
    assert found.job_id == job.job_id

def test_get_ready_subtasks_with_dependencies():
    state = TaskState()
    task = state.create_task("测试")
    subtask1 = state.add_subtask(task.task_id, "第一步", "openclaw")
    subtask2 = state.add_subtask(task.task_id, "第二步", "claude", dependencies=[subtask1.subtask_id])
    # Initially only first is ready
    ready = state.get_ready_subtasks(task.task_id)
    assert len(ready) == 1
    assert ready[0].subtask_id == subtask1.subtask_id
    # Complete first task
    job1 = state.create_job(subtask1)
    state.complete_job(job1.job_id, success=True)
    # Now second should be ready
    ready = state.get_ready_subtasks(task.task_id)
    assert len(ready) == 1
    assert ready[0].subtask_id == subtask2.subtask_id

def test_complete_job_failure():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行", "openclaw")
    job = state.create_job(subtask)
    state.update_job_status(job.job_id, JobStatus.RUNNING)
    result = state.complete_job(job.job_id, success=False, error="执行失败")
    assert result.success == False
    assert result.error == "执行失败"
    assert state.get_job(job.job_id).status == JobStatus.FAILED

def test_update_nonexistent_job():
    state = TaskState()
    result = state.update_job_progress("nonexistent", 0.5)
    assert result is None
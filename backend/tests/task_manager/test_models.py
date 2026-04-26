import pytest
from dataclasses import dataclass
from across_agents_assistant.task_manager.models import (
    JobStatus, TaskType, SubTask, Task, Job, JobResult, ProgressUpdate
)

def test_job_status_enum():
    assert JobStatus.PENDING.value == "pending"
    assert JobStatus.RUNNING.value == "running"
    assert JobStatus.COMPLETED.value == "completed"
    assert JobStatus.FAILED.value == "failed"
    assert JobStatus.CANCELLED.value == "cancelled"

def test_task_type_enum():
    assert TaskType.RESEARCH.value == "research"
    assert TaskType.CODE_REVIEW.value == "code_review"
    assert TaskType.AUTOMATION.value == "automation"
    assert TaskType.SIMPLE_QA.value == "simple_qa"
    assert TaskType.UNKNOWN.value == "unknown"

def test_subtask_creation():
    st = SubTask(
        subtask_id="st-1",
        description="分析代码结构",
        agent_id="claude",
        priority=1
    )
    assert st.subtask_id == "st-1"
    assert st.agent_id == "claude"
    assert st.status == JobStatus.PENDING

def test_task_creation():
    task = Task(
        task_id="task-1",
        description="帮我重构这个项目",
        task_type=TaskType.CODE_REVIEW
    )
    assert task.task_id == "task-1"
    assert len(task.subtasks) == 0
    assert task.can_handle_directly == False

def test_job_creation():
    job = Job(
        job_id="job-1",
        subtask_id="st-1",
        agent_id="claude",
        task_description="分析代码结构"
    )
    assert job.job_id == "job-1"
    assert job.status == JobStatus.PENDING
    assert job.progress == 0.0

def test_job_result():
    result = JobResult(
        job_id="job-1",
        success=True,
        output="分析完成：项目结构良好"
    )
    assert result.success == True

def test_progress_update():
    update = ProgressUpdate(
        job_id="job-1",
        status=JobStatus.RUNNING,
        progress=0.5,
        log="Processing..."
    )
    assert update.job_id == "job-1"
    assert update.status == JobStatus.RUNNING
    assert update.progress == 0.5
    assert update.log == "Processing..."

def test_task_new():
    """Test Task.new() factory method"""
    task = Task.new("测试任务")
    assert task.task_id.startswith("task-")
    assert task.description == "测试任务"
    assert task.task_type == TaskType.UNKNOWN
    assert len(task.subtasks) == 0
    assert task.can_handle_directly == False
    assert task.created_at > 0

def test_task_new_with_type():
    """Test Task.new() with explicit task type"""
    task = Task.new("代码审查", task_type=TaskType.CODE_REVIEW)
    assert task.task_type == TaskType.CODE_REVIEW

def test_job_new():
    """Test Job.new() factory method"""
    subtask = SubTask(
        subtask_id="st-123",
        description="执行任务",
        agent_id="openclaw",
        priority=1
    )
    job = Job.new(subtask, "openclaw")
    assert job.job_id.startswith("job-")
    assert job.subtask_id == "st-123"
    assert job.agent_id == "openclaw"
    assert job.task_description == "执行任务"
    assert job.status == JobStatus.PENDING
    assert job.progress == 0.0

def test_progress_update_default():
    """Test ProgressUpdate with default log=None"""
    update = ProgressUpdate(
        job_id="job-1",
        status=JobStatus.COMPLETED,
        progress=1.0
    )
    assert update.log is None
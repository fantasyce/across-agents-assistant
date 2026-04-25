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
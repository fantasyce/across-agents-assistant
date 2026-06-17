"""Deprecated compatibility package for legacy_task_history."""

from across_agents_assistant.legacy_task_history.models import (
    JobStatus, TaskType, SubTask, Task, Job, JobResult, ProgressUpdate
)

__all__ = [
    "JobStatus", "TaskType", "SubTask", "Task", "Job", "JobResult", "ProgressUpdate"
]

"""Legacy task history models and state for AAA host-side task views.

AAA task execution is externalized to Across Orchestrator. This package keeps
historical task records, persisted task snapshots, quality review state, and
compatibility helpers used to render old and external task history.
"""

from .models import (
    JobStatus,
    TaskType,
    SubTask,
    Task,
    Job,
    JobResult,
    ProgressUpdate,
)

__all__ = [
    "JobStatus",
    "TaskType",
    "SubTask",
    "Task",
    "Job",
    "JobResult",
    "ProgressUpdate",
]

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
import uuid
import time

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(str, Enum):
    RESEARCH = "research"
    CODE_REVIEW = "code_review"
    AUTOMATION = "automation"
    SIMPLE_QA = "simple_qa"
    UNKNOWN = "unknown"

@dataclass
class SubTask:
    subtask_id: str
    description: str
    agent_id: str  # openclaw, hermes, claude
    priority: int = 1
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    dependencies: List[str] = field(default_factory=list)  # subtask_ids this depends on

@dataclass
class Task:
    task_id: str
    description: str
    task_type: TaskType = TaskType.UNKNOWN
    subtasks: List[SubTask] = field(default_factory=list)
    can_handle_directly: bool = False
    direct_response: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @staticmethod
    def new(description: str, task_type: TaskType = TaskType.UNKNOWN) -> Task:
        return Task(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            description=description,
            task_type=task_type
        )

@dataclass
class Job:
    job_id: str
    subtask_id: str
    agent_id: str
    task_description: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    logs: List[str] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @staticmethod
    def new(subtask: SubTask, agent_id: str) -> Job:
        return Job(
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            subtask_id=subtask.subtask_id,
            agent_id=agent_id,
            task_description=subtask.description
        )

@dataclass
class JobResult:
    job_id: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration_sec: Optional[float] = None

@dataclass
class ProgressUpdate:
    job_id: str
    status: JobStatus
    progress: float
    log: Optional[str] = None

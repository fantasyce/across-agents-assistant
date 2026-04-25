import threading
import time
import uuid
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .models import Task, SubTask, Job, JobResult, JobStatus, TaskType, ProgressUpdate

@dataclass
class TaskState:
    """
    Thread-safe in-memory task state management.

    All access is protected by a reentrant lock to support
    nested calls from the same thread.
    """
    _tasks: Dict[str, Task] = field(default_factory=dict)
    _jobs: Dict[str, Job] = field(default_factory=dict)
    _subtask_to_job: Dict[str, str] = field(default_factory=dict)  # subtask_id -> job_id
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def create_task(self, description: str, task_type: TaskType = TaskType.UNKNOWN) -> Task:
        with self._lock:
            task = Task.new(description=description, task_type=task_type)
            self._tasks[task.task_id] = task
            return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[Task]:
        with self._lock:
            return list(self._tasks.values())

    def add_subtask(self, task_id: str, description: str, agent_id: str, priority: int = 1, dependencies: List[str] = None) -> Optional[SubTask]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            subtask = SubTask(
                subtask_id=f"st-{uuid.uuid4().hex[:8]}",
                description=description,
                agent_id=agent_id,
                priority=priority,
                dependencies=dependencies or []
            )
            task.subtasks.append(subtask)
            task.updated_at = time.time()
            return subtask

    def update_subtask_status(self, task_id: str, subtask_id: str, status: JobStatus) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            for st in task.subtasks:
                if st.subtask_id == subtask_id:
                    st.status = status
                    task.updated_at = time.time()
                    return True
            return False

    def get_task_progress(self, task_id: str) -> float:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or not task.subtasks:
                return 0.0
            total = len(task.subtasks)
            completed = sum(1 for st in task.subtasks if st.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED))
            return completed / total

    def create_job(self, subtask: SubTask) -> Job:
        with self._lock:
            job = Job.new(subtask=subtask, agent_id=subtask.agent_id)
            self._jobs[job.job_id] = job
            self._subtask_to_job[subtask.subtask_id] = job.job_id
            return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def get_job_by_subtask(self, subtask_id: str) -> Optional[Job]:
        with self._lock:
            job_id = self._subtask_to_job.get(subtask_id)
            if job_id:
                return self._jobs.get(job_id)
            return None

    def get_all_jobs(self) -> List[Job]:
        with self._lock:
            return list(self._jobs.values())

    def update_job_progress(self, job_id: str, progress: float, log: Optional[str] = None) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.progress = min(1.0, max(0.0, progress))
            if log:
                job.logs.append(log)
            if job.status == JobStatus.PENDING and progress > 0:
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
            return job

    def update_job_status(self, job_id: str, status: JobStatus) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.status = status
            if status == JobStatus.RUNNING and job.started_at is None:
                job.started_at = time.time()
            return job

    def complete_job(self, job_id: str, success: bool, output: Optional[str] = None, error: Optional[str] = None) -> Optional[JobResult]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.status = JobStatus.COMPLETED if success else JobStatus.FAILED
            job.completed_at = time.time()
            job.result = output
            job.error = error
            job.progress = 1.0 if success else job.progress

            # Update subtask status
            for task in self._tasks.values():
                for st in task.subtasks:
                    if st.subtask_id == job.subtask_id:
                        st.status = job.status
                        st.progress = job.progress

            duration = None
            if job.started_at and job.completed_at:
                duration = job.completed_at - job.started_at

            return JobResult(
                job_id=job_id,
                success=success,
                output=output,
                error=error,
                duration_sec=duration
            )

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            for st in task.subtasks:
                st.status = JobStatus.CANCELLED
                job_id = self._subtask_to_job.get(st.subtask_id)
                if job_id:
                    job = self._jobs.get(job_id)
                    if job and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                        job.status = JobStatus.CANCELLED
                        job.completed_at = time.time()
            task.updated_at = time.time()
            return True

    def get_ready_subtasks(self, task_id: str) -> List[SubTask]:
        """Get subtasks that are ready to run (pending and dependencies satisfied)."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return []
            ready = []
            for st in task.subtasks:
                if st.status != JobStatus.PENDING:
                    continue
                # Check dependencies
                deps_satisfied = all(
                    self._get_subtask_status(task_id, dep) in (JobStatus.COMPLETED, JobStatus.CANCELLED)
                    for dep in st.dependencies
                )
                if deps_satisfied:
                    ready.append(st)
            return ready

    def _get_subtask_status(self, task_id: str, subtask_id: str) -> JobStatus:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return JobStatus.PENDING
            for st in task.subtasks:
                if st.subtask_id == subtask_id:
                    return st.status
            return JobStatus.PENDING
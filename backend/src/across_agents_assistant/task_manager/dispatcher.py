import asyncio
import logging
import threading
import time
from typing import Dict, List, Optional, Callable

from ..openclaw.client import UniversalAgentClient
from .models import Job, JobStatus, SubTask, Task, JobResult, ProgressUpdate
from .state import TaskState

logger = logging.getLogger("across_agents_assistant.task_manager")

class TaskDispatcher:
    """
    Dispatches subtasks to agents and manages job execution.

    Uses a thread pool to execute agent calls without blocking the main async loop.
    """

    def __init__(self, state: TaskState, openclaw_client: UniversalAgentClient):
        self._state = state
        self._openclaw = openclaw_client
        self._job_threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._progress_callbacks: List[Callable[[ProgressUpdate], None]] = []

    def add_progress_callback(self, callback: Callable[[ProgressUpdate], None]) -> None:
        """Add a callback for progress updates."""
        self._progress_callbacks.append(callback)

    def dispatch_subtask(self, subtask: SubTask) -> Optional[Job]:
        """
        Synchronously dispatch a subtask to the appropriate agent.

        Returns the created Job, or None if dispatch failed.
        """
        # Validate agent upfront
        if subtask.agent_id not in ("openclaw", "hermes", "claude"):
            return None

        job = self._state.create_job(subtask)

        def run_job():
            try:
                self._state.update_job_status(job.job_id, JobStatus.RUNNING)
                self._notify_progress(job.job_id, JobStatus.RUNNING, 0.0, "Started")

                # Execute based on agent type
                if subtask.agent_id in ("openclaw", "hermes", "claude"):
                    result = self._execute_agent_job(job, subtask, subtask.agent_id)
                else:
                    result = JobResult(job_id=job.job_id, success=False, error=f"Unknown agent: {subtask.agent_id}")

                if result.success:
                    self._state.complete_job(job.job_id, success=True, output=result.output)
                    self._notify_progress(job.job_id, JobStatus.COMPLETED, 1.0, "Completed")
                else:
                    self._state.complete_job(job.job_id, success=False, error=result.error)
                    self._notify_progress(job.job_id, JobStatus.FAILED, job.progress, f"Failed: {result.error}")

            except Exception as e:
                logger.error(f"Job {job.job_id} failed with exception: {e}")
                self._state.complete_job(job.job_id, success=False, error=str(e))
                self._notify_progress(job.job_id, JobStatus.FAILED, 0.0, f"Error: {e}")
            finally:
                with self._lock:
                    self._job_threads.pop(job.job_id, None)

        thread = threading.Thread(target=run_job, daemon=True)
        with self._lock:
            self._job_threads[job.job_id] = thread

        thread.start()
        return job

    def _execute_agent_job(self, job: Job, subtask: SubTask, target_agent: str) -> JobResult:
        """Execute a job using the specified agent."""
        try:
            self._state.update_job_progress(job.job_id, 0.1, f"Connecting to {target_agent} agent...")
            self._notify_progress(job.job_id, JobStatus.RUNNING, 0.1, "Connecting...")

            response = self._openclaw.send(
                message=subtask.description,
                session_id=None,
                use_current=True,
                target_agent=target_agent
            )

            self._state.update_job_progress(job.job_id, 0.9, "Processing response...")
            self._notify_progress(job.job_id, JobStatus.RUNNING, 0.9, "Processing...")

            output = response.text if response and response.text else ""
            return JobResult(job_id=job.job_id, success=True, output=output)

        except Exception as e:
            return JobResult(job_id=job.job_id, success=False, error=str(e))

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        job = self._state.get_job(job_id)
        if not job:
            return False
        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return False

        result = self._state.cancel_job(job_id, error="Cancelled by user")
        if result:
            self._notify_progress(job_id, JobStatus.CANCELLED, job.progress, "Cancelled")
            return True
        return False

    def get_active_jobs(self) -> List[Job]:
        """Get all currently running jobs."""
        jobs = self._state.get_all_jobs()
        return [j for j in jobs if j.status == JobStatus.RUNNING]

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a specific job by ID."""
        return self._state.get_job(job_id)

    def _notify_progress(self, job_id: str, status: JobStatus, progress: float, log: Optional[str] = None) -> None:
        """Notify all progress callbacks."""
        update = ProgressUpdate(job_id=job_id, status=status, progress=progress, log=log)
        for callback in self._progress_callbacks:
            try:
                callback(update)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")
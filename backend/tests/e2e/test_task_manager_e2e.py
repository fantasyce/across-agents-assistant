import pytest
import time
from across_agents_assistant.task_manager.models import (
    Task, SubTask, Job, JobStatus, JobResult, TaskType
)
from across_agents_assistant.task_manager.state import TaskState


class TestTaskState:
    """Test TaskState with DISPATCHED status and orphan recovery."""

    def test_create_job_has_pending_status(self):
        state = TaskState()
        subtask = SubTask(
            subtask_id="st-001",
            description="Test subtask",
            agent_id="openclaw"
        )
        job = state.create_job(subtask)
        assert job.status == JobStatus.PENDING
        assert job.attempt == 0
        assert job.pinned_session_id is None
        assert job.failure_reason is None

    def test_dispatched_status_exists(self):
        """Verify DISPATCHED status is available in JobStatus enum."""
        assert JobStatus.DISPATCHED == "dispatched"

    def test_job_status_transition_pending_to_dispatched(self):
        state = TaskState()
        subtask = SubTask(
            subtask_id="st-002",
            description="Test subtask",
            agent_id="openclaw"
        )
        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.DISPATCHED)

        updated = state.get_job(job.job_id)
        assert updated.status == JobStatus.DISPATCHED

    def test_job_status_transition_dispatched_to_running(self):
        state = TaskState()
        subtask = SubTask(
            subtask_id="st-003",
            description="Test subtask",
            agent_id="openclaw"
        )
        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.DISPATCHED)
        state.update_job_status(job.job_id, JobStatus.RUNNING)

        updated = state.get_job(job.job_id)
        assert updated.status == JobStatus.RUNNING
        assert updated.started_at is not None

    def test_dispatched_not_auto_transitioned_by_progress(self):
        """DISPATCHED jobs should NOT auto-transition to RUNNING on progress update."""
        state = TaskState()
        subtask = SubTask(
            subtask_id="st-004",
            description="Test subtask",
            agent_id="openclaw"
        )
        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.DISPATCHED)
        state.update_job_progress(job.job_id, 0.5, "Halfway")

        updated = state.get_job(job.job_id)
        assert updated.status == JobStatus.DISPATCHED
        assert updated.progress == 0.5

    def test_get_jobs_in_status(self):
        state = TaskState()
        subtask1 = SubTask(subtask_id="st-005", description="Task 1", agent_id="openclaw")
        subtask2 = SubTask(subtask_id="st-006", description="Task 2", agent_id="claude")

        job1 = state.create_job(subtask1)
        job2 = state.create_job(subtask2)

        state.update_job_status(job1.job_id, JobStatus.DISPATCHED)
        state.update_job_status(job2.job_id, JobStatus.RUNNING)

        dispatched = state.get_jobs_in_status([JobStatus.DISPATCHED])
        assert len(dispatched) == 1
        assert dispatched[0].job_id == job1.job_id

        running = state.get_jobs_in_status([JobStatus.RUNNING])
        assert len(running) == 1
        assert running[0].job_id == job2.job_id

        both = state.get_jobs_in_status([JobStatus.DISPATCHED, JobStatus.RUNNING])
        assert len(both) == 2

    def test_complete_job_from_dispatched(self):
        """A DISPATCHED job can be directly completed or failed."""
        state = TaskState()
        subtask = SubTask(
            subtask_id="st-007",
            description="Test subtask",
            agent_id="openclaw"
        )
        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.DISPATCHED)

        result = state.complete_job(job.job_id, success=False, error="orphan_recovery")
        assert result.success is False

        updated = state.get_job(job.job_id)
        assert updated.status == JobStatus.FAILED
        assert updated.error == "orphan_recovery"

    def test_job_fields_extended(self):
        """Verify Job has the new fields for orphan recovery."""
        job = Job(
            job_id="job-test",
            subtask_id="st-test",
            agent_id="openclaw",
            task_description="Test",
            attempt=2,
            pinned_session_id="sess-123",
            failure_reason="timeout"
        )
        assert job.attempt == 2
        assert job.pinned_session_id == "sess-123"
        assert job.failure_reason == "timeout"


class TestTaskLifecycle:
    """Test full task lifecycle with DISPATCHED state."""

    def test_full_lifecycle_pending_dispatched_running_completed(self):
        state = TaskState()
        task = state.create_task("Test task", TaskType.SIMPLE_QA)
        subtask = state.add_subtask(task.task_id, "Do something", "openclaw")

        job = state.create_job(subtask)
        assert job.status == JobStatus.PENDING

        # Dispatcher would call this before starting thread
        state.update_job_status(job.job_id, JobStatus.DISPATCHED)
        assert state.get_job(job.job_id).status == JobStatus.DISPATCHED

        # Thread starts, agent begins execution
        state.update_job_status(job.job_id, JobStatus.RUNNING)
        assert state.get_job(job.job_id).status == JobStatus.RUNNING

        # Job completes
        state.complete_job(job.job_id, success=True, output="Done")
        assert state.get_job(job.job_id).status == JobStatus.COMPLETED

    def test_task_dependencies_and_ready_subtasks(self):
        state = TaskState()
        task = state.create_task("Multi-step task", TaskType.AUTOMATION)

        subtask1 = state.add_subtask(task.task_id, "Step 1", "openclaw")
        subtask2 = state.add_subtask(
            task.task_id, "Step 2", "claude",
            dependencies=[subtask1.subtask_id]
        )

        # Initially both are pending
        ready = state.get_ready_subtasks(task.task_id)
        assert len(ready) == 1
        assert ready[0].subtask_id == subtask1.subtask_id

        # Complete subtask1
        job1 = state.create_job(subtask1)
        state.complete_job(job1.job_id, success=True)

        # Now subtask2 should be ready
        ready = state.get_ready_subtasks(task.task_id)
        assert len(ready) == 1
        assert ready[0].subtask_id == subtask2.subtask_id

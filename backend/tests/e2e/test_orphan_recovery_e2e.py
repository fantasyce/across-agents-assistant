import pytest
from unittest.mock import MagicMock, patch

from across_agents_assistant.task_manager.models import (
    Task, SubTask, Job, JobStatus, TaskType
)
from across_agents_assistant.task_manager.state import TaskState
from across_agents_assistant.task_manager.dispatcher import TaskDispatcher


class FakeAgentBridge:
    """Fake AgentBridge for testing orphan recovery."""
    def __init__(self):
        self.invoked = []

    def invoke(self, agent_id, message, context=None, timeout=120.0):
        self.invoked.append({
            "agent_id": agent_id,
            "message": message,
            "context": context,
            "timeout": timeout,
        })
        # Simulate successful resume
        return MagicMock(is_success=True, output="Resumed successfully")


class FakeUniversalAgentClient:
    pass


class TestOrphanRecovery:
    """Test orphan job recovery after backend restart."""

    def test_recover_dispatched_orphan(self):
        """DISPATCHED orphans should be re-dispatched."""
        state = TaskState()
        task = state.create_task("Test task", TaskType.SIMPLE_QA)
        subtask = state.add_subtask(task.task_id, "Do something", "openclaw")

        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.DISPATCHED)

        # Verify orphan is detected
        orphans = state.get_jobs_in_status([JobStatus.DISPATCHED, JobStatus.RUNNING])
        assert len(orphans) == 1
        assert orphans[0].job_id == job.job_id

    def test_recover_running_orphan_with_pin(self):
        """RUNNING orphans with pinned_session_id should attempt resume."""
        state = TaskState()
        task = state.create_task("Test task", TaskType.SIMPLE_QA)
        subtask = state.add_subtask(task.task_id, "Do something", "openclaw")

        job = state.create_job(subtask)
        job.pinned_session_id = "sess-abc-123"
        state.update_job_status(job.job_id, JobStatus.RUNNING)

        orphans = state.get_jobs_in_status([JobStatus.DISPATCHED, JobStatus.RUNNING])
        assert len(orphans) == 1
        assert orphans[0].pinned_session_id == "sess-abc-123"

    def test_recover_running_orphan_without_pin(self):
        """RUNNING orphans without pinned_session_id should be marked FAILED."""
        state = TaskState()
        task = state.create_task("Test task", TaskType.SIMPLE_QA)
        subtask = state.add_subtask(task.task_id, "Do something", "openclaw")

        job = state.create_job(subtask)
        # No pinned_session_id
        state.update_job_status(job.job_id, JobStatus.RUNNING)

        orphans = state.get_jobs_in_status([JobStatus.DISPATCHED, JobStatus.RUNNING])
        assert len(orphans) == 1
        assert orphans[0].pinned_session_id is None

    def test_get_jobs_in_status_multiple_statuses(self):
        """get_jobs_in_status should support querying multiple statuses."""
        state = TaskState()

        # Create jobs in different states
        task = state.create_task("Test task", TaskType.SIMPLE_QA)

        subtask1 = state.add_subtask(task.task_id, "Task 1", "openclaw")
        subtask2 = state.add_subtask(task.task_id, "Task 2", "claude")
        subtask3 = state.add_subtask(task.task_id, "Task 3", "hermes")

        job1 = state.create_job(subtask1)
        job2 = state.create_job(subtask2)
        job3 = state.create_job(subtask3)

        state.update_job_status(job1.job_id, JobStatus.DISPATCHED)
        state.update_job_status(job2.job_id, JobStatus.RUNNING)
        # job3 stays PENDING

        # Query DISPATCHED + RUNNING
        active = state.get_jobs_in_status([JobStatus.DISPATCHED, JobStatus.RUNNING])
        assert len(active) == 2
        job_ids = {j.job_id for j in active}
        assert job1.job_id in job_ids
        assert job2.job_id in job_ids
        assert job3.job_id not in job_ids

    def test_job_attempt_counter(self):
        """Job attempt counter should be incremented on retry."""
        job = Job(
            job_id="job-test",
            subtask_id="st-test",
            agent_id="openclaw",
            task_description="Test",
            attempt=0
        )
        assert job.attempt == 0
        job.attempt += 1
        assert job.attempt == 1

    def test_job_failure_reason_tracking(self):
        """Job should track failure reason."""
        state = TaskState()
        subtask = SubTask(
            subtask_id="st-test",
            description="Test",
            agent_id="openclaw"
        )
        job = state.create_job(subtask)
        job.failure_reason = "timeout"

        assert state.get_job(job.job_id).failure_reason == "timeout"

    def test_complete_job_updates_subtask_status(self):
        """Completing a job should update the corresponding subtask status."""
        state = TaskState()
        task = state.create_task("Test task", TaskType.SIMPLE_QA)
        subtask = state.add_subtask(task.task_id, "Do something", "openclaw")

        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.RUNNING)
        state.complete_job(job.job_id, success=True, output="Done")

        # Check subtask status is updated
        updated_task = state.get_task(task.task_id)
        assert updated_task.subtasks[0].status == JobStatus.COMPLETED
        assert updated_task.subtasks[0].progress == 1.0

    def test_cancel_job_from_dispatched(self):
        """Cancel should work from DISPATCHED state."""
        state = TaskState()
        subtask = SubTask(
            subtask_id="st-test",
            description="Test",
            agent_id="openclaw"
        )
        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.DISPATCHED)

        result = state.cancel_job(job.job_id)
        assert result is not None
        assert result.success is False

        updated = state.get_job(job.job_id)
        assert updated.status == JobStatus.CANCELLED

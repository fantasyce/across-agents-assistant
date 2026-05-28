import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from across_agents_assistant.task_manager.models import (
    AcceptanceResult,
    JobStatus,
    ProgressUpdate,
    SubTask,
    TaskStatus,
    ValidationReport,
)
from across_agents_assistant.task_manager.orchestration.orchestrator import TaskOrchestrator
from across_agents_assistant.task_manager.state import TaskState


@pytest.fixture
def mock_dispatcher():
    dispatcher = MagicMock()
    dispatcher.add_progress_callback = MagicMock()
    dispatcher.dispatch_subtask = MagicMock(return_value=None)
    return dispatcher


@pytest.fixture
def mock_validator():
    validator = MagicMock()
    validator.validate = MagicMock(return_value=ValidationReport(passed=True, errors=[]))
    return validator


@pytest.fixture
def mock_owner_agent():
    agent = MagicMock()
    agent.decompose_and_assign = MagicMock()
    agent.accept_subtask = MagicMock(return_value=AcceptanceResult(
        subtask_id="st-1",
        level1_passed=True,
        level2_passed=True,
    ))
    agent.decide_on_failure = MagicMock(return_value=MagicMock(action="downgrade"))
    agent.run_integration_test = MagicMock(return_value=MagicMock(passed=True))
    return agent


@pytest.fixture
def orchestrator(mock_dispatcher, mock_validator, mock_owner_agent):
    state = TaskState()
    return TaskOrchestrator(
        state=state,
        dispatcher=mock_dispatcher,
        validator=mock_validator,
        owner_agent=mock_owner_agent,
    )


class TestDAGAutoProgression:
    """Test Scenario 1: DAG Auto-Progression (A -> B)

    - Create a task with 2 subtasks: A (no deps) and B (depends on A)
    - Mock the dispatcher so that when A is dispatched, it immediately completes
      (by calling the registered progress callback with COMPLETED status)
    - Verify that after A completes, B is automatically dispatched
    """

    @pytest.mark.asyncio
    async def test_a_completes_then_b_dispatched(self, orchestrator, mock_dispatcher, mock_owner_agent):
        # Capture the registered callback
        callback = mock_dispatcher.add_progress_callback.call_args[0][0]

        # Setup: owner agent decomposes into A (no deps) and B (depends on A)
        def decompose_side_effect(task, context=None):
            task.subtasks = [
                SubTask(subtask_id="st-a", description="Subtask A", agent_id="claude", dependencies=[]),
                SubTask(subtask_id="st-b", description="Subtask B", agent_id="deepseek", dependencies=["st-a"]),
            ]

        mock_owner_agent.decompose_and_assign.side_effect = decompose_side_effect

        def dispatch_side_effect(subtask):
            job = orchestrator._state.create_job(subtask)
            orchestrator._state.complete_job(job.job_id, success=True)
            # Immediately call the progress callback to simulate completion
            update = ProgressUpdate(job_id=job.job_id, status=JobStatus.COMPLETED, progress=1.0)
            callback(update)

        mock_dispatcher.dispatch_subtask.side_effect = dispatch_side_effect

        # Submit the task
        task_id = orchestrator.submit_task("Build a task management system")

        # Wait for async processing to complete
        await asyncio.sleep(0.2)

        # Verify task was created
        assert task_id is not None
        assert task_id.startswith("task-")

        # Verify both subtasks were dispatched
        dispatched_ids = [call.args[0].subtask_id for call in mock_dispatcher.dispatch_subtask.call_args_list]
        assert "st-a" in dispatched_ids
        assert "st-b" in dispatched_ids

        # Verify B was dispatched after A completed (i.e., B appears after A in call order)
        a_index = dispatched_ids.index("st-a")
        b_index = dispatched_ids.index("st-b")
        assert b_index > a_index, "Subtask B should be dispatched after subtask A completes"

        # Verify A is marked completed
        task = orchestrator._state.get_task(task_id)
        st_a = next(st for st in task.subtasks if st.subtask_id == "st-a")
        assert st_a.status == JobStatus.COMPLETED

        # Verify B is also completed (since our mock auto-completes everything)
        st_b = next(st for st in task.subtasks if st.subtask_id == "st-b")
        assert st_b.status == JobStatus.COMPLETED


class TestFixLoop:
    """Test Scenario 2: Fix Loop

    - Create a task with subtask A
    - Mock Level 1 validation to fail A (return ValidationReport with passed=False)
    - Verify that a fix subtask A-fix-1 is created and dispatched
    - Mock the fix to pass (return ValidationReport with passed=True,
      and OwnerAgent accept_subtask returns passed=True)
    - Verify DAG continues (no more fix subtasks created)
    """

    @pytest.mark.asyncio
    async def test_level1_failure_creates_fix_then_passes(self, orchestrator, mock_dispatcher, mock_validator, mock_owner_agent):
        callback = mock_dispatcher.add_progress_callback.call_args[0][0]

        fix_dispatched = threading.Event()

        def decompose_side_effect(task, context=None):
            task.subtasks = [
                SubTask(subtask_id="st-a", description="Subtask A", agent_id="claude", dependencies=[]),
            ]

        mock_owner_agent.decompose_and_assign.side_effect = decompose_side_effect

        # Level 1 fails for original, passes for fix
        def validate_side_effect(job):
            if "fix" in job.subtask_id:
                return ValidationReport(passed=True, errors=[])
            return ValidationReport(passed=False, errors=[MagicMock(error_type="missing_endpoint", message="missing /api/items")])

        mock_validator.validate.side_effect = validate_side_effect

        # Level 2: fail for original, pass for fix
        def accept_side_effect(job):
            if "fix" in job.subtask_id:
                return AcceptanceResult(
                    subtask_id=job.subtask_id,
                    level1_passed=True,
                    level2_passed=True,
                )
            return AcceptanceResult(
                subtask_id=job.subtask_id,
                level1_passed=False,
                level2_passed=True,
            )

        mock_owner_agent.accept_subtask.side_effect = accept_side_effect

        def dispatch_side_effect(subtask):
            job = orchestrator._state.create_job(subtask)
            orchestrator._state.complete_job(job.job_id, success=True)
            update = ProgressUpdate(job_id=job.job_id, status=JobStatus.COMPLETED, progress=1.0)
            callback(update)
            if "fix" in subtask.subtask_id:
                fix_dispatched.set()

        mock_dispatcher.dispatch_subtask.side_effect = dispatch_side_effect

        # Submit task
        task_id = orchestrator.submit_task("Build API")

        # Wait for fix to be dispatched
        fix_dispatched.wait(timeout=2.0)
        await asyncio.sleep(0.1)

        # Verify fix subtask was created and dispatched
        dispatched_ids = [call.args[0].subtask_id for call in mock_dispatcher.dispatch_subtask.call_args_list]
        assert any("fix" in sid for sid in dispatched_ids), "Fix subtask should be dispatched"

        fix_calls = [sid for sid in dispatched_ids if "fix" in sid]
        assert len(fix_calls) == 1, f"Expected exactly 1 fix subtask, got {len(fix_calls)}: {fix_calls}"
        assert fix_calls[0] == "st-a-fix-1"

        # Wait a bit more to ensure no additional fix subtasks are created
        await asyncio.sleep(0.2)

        dispatched_ids_after = [call.args[0].subtask_id for call in mock_dispatcher.dispatch_subtask.call_args_list]
        fix_calls_after = [sid for sid in dispatched_ids_after if "fix" in sid]
        assert len(fix_calls_after) == 1, "No additional fix subtasks should be created after fix passes"

        # Verify the original subtask A is marked completed
        task = orchestrator._state.get_task(task_id)
        st_a = next(st for st in task.subtasks if st.subtask_id == "st-a")
        assert st_a.status == JobStatus.COMPLETED


class TestMaxRoundsDowngrade:
    """Test Scenario 3: Max Rounds (3) -> Failed

    - Create a task with subtask A
    - Mock Level 2 acceptance to fail A 3 times in a row
      (return AcceptanceResult with passed=False, action="fix")
    - Verify remediation is exhausted without downgrade/reassign
    - Verify subtask is marked as failed
    """

    @pytest.mark.asyncio
    async def test_max_rounds_then_failed(self, orchestrator, mock_dispatcher, mock_validator, mock_owner_agent):
        callback = mock_dispatcher.add_progress_callback.call_args[0][0]
        mock_dispatcher._get_valid_agents.return_value = ["claude", "deepseek"]

        def decompose_side_effect(task, context=None):
            task.subtasks = [
                SubTask(subtask_id="st-a", description="Subtask A", agent_id="claude", dependencies=[]),
            ]

        mock_owner_agent.decompose_and_assign.side_effect = decompose_side_effect

        # Level 1 always passes, Level 2 always fails (triggers fix loop)
        mock_validator.validate.return_value = ValidationReport(passed=True, errors=[])

        def accept_side_effect(job):
            return AcceptanceResult(
                subtask_id=job.subtask_id,
                level1_passed=True,
                level2_passed=False,
                level2_feedback="Still broken",
            )

        mock_owner_agent.accept_subtask.side_effect = accept_side_effect

        dispatch_count = 0
        dispatch_event = threading.Event()

        def dispatch_side_effect(subtask):
            nonlocal dispatch_count
            dispatch_count += 1
            job = orchestrator._state.create_job(subtask)
            orchestrator._state.complete_job(job.job_id, success=True)

            update = ProgressUpdate(job_id=job.job_id, status=JobStatus.COMPLETED, progress=1.0)
            callback(update)
            # Signal when original + 3 fixes have been dispatched
            if dispatch_count >= 4:
                dispatch_event.set()

        mock_dispatcher.dispatch_subtask.side_effect = dispatch_side_effect

        # Submit task
        task_id = orchestrator.submit_task("Build API")

        # Wait for all dispatches to complete
        dispatch_event.wait(timeout=3.0)
        await asyncio.sleep(0.3)

        # Verify fix rounds were tracked against the original subtask
        ost = orchestrator._orchestrator_states[task_id]
        assert ost.fix_rounds.get("st-a", 0) == 3, f"Expected 3 fix rounds, got {ost.fix_rounds.get('st-a', 0)}"

        # Verify decide_on_failure is not used after remediation budget exhaustion.
        mock_owner_agent.decide_on_failure.assert_not_called()
        assert "st-a" not in ost.completed_subtasks

        # Verify subtask status is FAILED.
        task = orchestrator._state.get_task(task_id)
        st_a = next(st for st in task.subtasks if st.subtask_id == "st-a")
        assert st_a.status == JobStatus.FAILED
        assert task.status == TaskStatus.COMPLETED_WITH_FAILURES

        # Verify exactly 3 fix subtasks were created (fix-1, fix-2, fix-3)
        dispatched_ids = [call.args[0].subtask_id for call in mock_dispatcher.dispatch_subtask.call_args_list]
        fix_calls = [sid for sid in dispatched_ids if "fix" in sid]
        assert len(fix_calls) == 3, f"Expected 3 fix subtasks, got {len(fix_calls)}: {fix_calls}"

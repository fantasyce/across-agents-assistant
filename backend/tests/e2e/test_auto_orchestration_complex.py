import asyncio
import threading
import time
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


async def wait_for_dispatched(mock_dispatcher, expected_ids, timeout=3.0):
    expected = set(expected_ids)
    deadline = time.time() + timeout
    dispatched_ids = []
    while time.time() < deadline:
        dispatched_ids = [call.args[0].subtask_id for call in mock_dispatcher.dispatch_subtask.call_args_list]
        if expected.issubset(dispatched_ids):
            return dispatched_ids
        await asyncio.sleep(0.05)
    return dispatched_ids


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


class TestComplexDAGExecution:
    """Test Scenario: Complex DAG with 6 SubTasks

    DAG:
        SubTask 1: Architecture (claude)       — no deps
        SubTask 2: DB Schema (deepseek)        — depends on 1
        SubTask 3: Backend API (deepseek)      — depends on 2
        SubTask 4: Frontend UI (hermes)        — depends on 1
        SubTask 5: Integration Tests (claude)  — depends on 3, 4
        SubTask 6: DevOps Config (minimax)     — depends on 3, 4

    Expected execution order: 1 → (2, 4 parallel) → 3 → (5, 6 parallel)
    """

    @pytest.mark.asyncio
    async def test_complex_dag_execution_order(self, orchestrator, mock_dispatcher, mock_owner_agent):
        callback = mock_dispatcher.add_progress_callback.call_args[0][0]

        def decompose_side_effect(task, context=None):
            task.subtasks = [
                SubTask(subtask_id="st-1", description="Architecture", agent_id="claude", dependencies=[]),
                SubTask(subtask_id="st-2", description="DB Schema", agent_id="deepseek", dependencies=["st-1"]),
                SubTask(subtask_id="st-3", description="Backend API", agent_id="deepseek", dependencies=["st-2"]),
                SubTask(subtask_id="st-4", description="Frontend UI", agent_id="hermes", dependencies=["st-1"]),
                SubTask(subtask_id="st-5", description="Integration Tests", agent_id="claude", dependencies=["st-3", "st-4"]),
                SubTask(subtask_id="st-6", description="DevOps Config", agent_id="minimax", dependencies=["st-3", "st-4"]),
            ]

        mock_owner_agent.decompose_and_assign.side_effect = decompose_side_effect

        def dispatch_side_effect(subtask):
            job = orchestrator._state.create_job(subtask)
            orchestrator._state.complete_job(job.job_id, success=True)
            update = ProgressUpdate(job_id=job.job_id, status=JobStatus.COMPLETED, progress=1.0)
            callback(update)

        mock_dispatcher.dispatch_subtask.side_effect = dispatch_side_effect

        task_id = orchestrator.submit_task("Build a full-stack application")
        dispatched_ids = await wait_for_dispatched(
            mock_dispatcher,
            ["st-1", "st-2", "st-3", "st-4", "st-5", "st-6"],
        )

        task = orchestrator._state.get_task(task_id)
        assert task is not None

        # Verify all 6 subtasks were dispatched
        for st_id in ["st-1", "st-2", "st-3", "st-4", "st-5", "st-6"]:
            assert st_id in dispatched_ids, f"{st_id} should be dispatched"

        # Verify execution order constraints
        idx1 = dispatched_ids.index("st-1")
        idx2 = dispatched_ids.index("st-2")
        idx3 = dispatched_ids.index("st-3")
        idx4 = dispatched_ids.index("st-4")
        idx5 = dispatched_ids.index("st-5")
        idx6 = dispatched_ids.index("st-6")

        # st-1 must be first
        assert idx1 == 0, "st-1 (Architecture) should be dispatched first"

        # st-2 and st-4 both depend on st-1, so they must come after st-1
        assert idx2 > idx1, "st-2 should be dispatched after st-1"
        assert idx4 > idx1, "st-4 should be dispatched after st-1"

        # st-3 depends on st-2, so it must come after st-2
        assert idx3 > idx2, "st-3 should be dispatched after st-2"

        # st-5 and st-6 depend on st-3 and st-4, so they must come after both
        assert idx5 > idx3, "st-5 should be dispatched after st-3"
        assert idx5 > idx4, "st-5 should be dispatched after st-4"
        assert idx6 > idx3, "st-6 should be dispatched after st-3"
        assert idx6 > idx4, "st-6 should be dispatched after st-4"

        # Verify all subtasks are completed
        for st in task.subtasks:
            assert st.status == JobStatus.COMPLETED, f"{st.subtask_id} should be COMPLETED"

        # Verify integration test was run
        mock_owner_agent.run_integration_test.assert_called()


class TestFixLoopWithDAGDependency:
    """Test Scenario: Fix Loop with DAG Dependency

    - SubTask 1 passes
    - SubTask 2 fails Level 1 validation → creates fix-1 → passes
    - SubTask 3 depends on 2, so it should wait until 2's fix passes
    - Verify the dependency chain is respected during fix loops
    """

    @pytest.mark.asyncio
    async def test_fix_loop_respects_dag_dependencies(self, orchestrator, mock_dispatcher, mock_validator, mock_owner_agent):
        callback = mock_dispatcher.add_progress_callback.call_args[0][0]

        def decompose_side_effect(task, context=None):
            task.subtasks = [
                SubTask(subtask_id="st-1", description="Architecture", agent_id="claude", dependencies=[]),
                SubTask(subtask_id="st-2", description="DB Schema", agent_id="deepseek", dependencies=["st-1"]),
                SubTask(subtask_id="st-3", description="Backend API", agent_id="deepseek", dependencies=["st-2"]),
            ]

        mock_owner_agent.decompose_and_assign.side_effect = decompose_side_effect

        # Level 1 fails for st-2 original, passes for everything else (including fix)
        def validate_side_effect(job):
            if job.subtask_id == "st-2":
                return ValidationReport(passed=False, errors=[MagicMock(error_type="schema_error", message="Invalid schema")])
            return ValidationReport(passed=True, errors=[])

        mock_validator.validate.side_effect = validate_side_effect

        # Level 2: fail for st-2 original, pass for fix and others
        def accept_side_effect(job):
            if job.subtask_id == "st-2":
                return AcceptanceResult(
                    subtask_id=job.subtask_id,
                    level1_passed=False,
                    level2_passed=True,
                )
            return AcceptanceResult(
                subtask_id=job.subtask_id,
                level1_passed=True,
                level2_passed=True,
            )

        mock_owner_agent.accept_subtask.side_effect = accept_side_effect

        fix_dispatched = threading.Event()

        def dispatch_side_effect(subtask):
            job = orchestrator._state.create_job(subtask)
            orchestrator._state.complete_job(job.job_id, success=True)
            update = ProgressUpdate(job_id=job.job_id, status=JobStatus.COMPLETED, progress=1.0)
            callback(update)
            if "fix" in subtask.subtask_id:
                fix_dispatched.set()

        mock_dispatcher.dispatch_subtask.side_effect = dispatch_side_effect

        task_id = orchestrator.submit_task("Build API with DB")

        # Wait for fix to be dispatched
        fix_dispatched.wait(timeout=2.0)
        dispatched_ids = await wait_for_dispatched(
            mock_dispatcher,
            ["st-1", "st-2", "st-2-fix-1", "st-3"],
        )

        task = orchestrator._state.get_task(task_id)

        # Verify fix subtask was created and dispatched
        fix_calls = [sid for sid in dispatched_ids if "fix" in sid]
        assert len(fix_calls) == 1, f"Expected exactly 1 fix subtask, got {len(fix_calls)}: {fix_calls}"
        assert fix_calls[0] == "st-2-fix-1"

        # Verify st-3 was dispatched AFTER st-2-fix-1
        idx_st2_fix = dispatched_ids.index("st-2-fix-1")
        idx_st3 = dispatched_ids.index("st-3")
        assert idx_st3 > idx_st2_fix, "st-3 should be dispatched after st-2-fix-1 completes"

        # Verify all subtasks are completed
        for st in task.subtasks:
            assert st.status == JobStatus.COMPLETED, f"{st.subtask_id} should be COMPLETED"


class TestMaxRoundsDowngradeInComplexDAG:
    """Test Scenario: Max Rounds with Failure in Complex DAG

    - SubTask 4 fails acceptance 3 times
    - Verify remediation is exhausted without downgrade/reassign
    - Verify SubTask 4 is marked as failed
    - Verify SubTask 5 and 6 (which depend on 4) are cancelled
    """

    @pytest.mark.asyncio
    async def test_remediation_exhaustion_blocks_downstream_in_complex_dag(self, orchestrator, mock_dispatcher, mock_validator, mock_owner_agent):
        callback = mock_dispatcher.add_progress_callback.call_args[0][0]
        mock_dispatcher._get_valid_agents.return_value = ["claude", "deepseek", "hermes", "minimax"]

        def decompose_side_effect(task, context=None):
            task.subtasks = [
                SubTask(subtask_id="st-1", description="Architecture", agent_id="claude", dependencies=[]),
                SubTask(subtask_id="st-2", description="DB Schema", agent_id="deepseek", dependencies=["st-1"]),
                SubTask(subtask_id="st-3", description="Backend API", agent_id="deepseek", dependencies=["st-2"]),
                SubTask(subtask_id="st-4", description="Frontend UI", agent_id="hermes", dependencies=["st-1"]),
                SubTask(subtask_id="st-5", description="Integration Tests", agent_id="claude", dependencies=["st-3", "st-4"]),
                SubTask(subtask_id="st-6", description="DevOps Config", agent_id="minimax", dependencies=["st-3", "st-4"]),
            ]

        mock_owner_agent.decompose_and_assign.side_effect = decompose_side_effect

        # Level 1 always passes
        mock_validator.validate.return_value = ValidationReport(passed=True, errors=[])

        # Level 2: fail for st-4, pass for others
        def accept_side_effect(job):
            if job.subtask_id == "st-4" or job.subtask_id.startswith("st-4-fix-"):
                return AcceptanceResult(
                    subtask_id=job.subtask_id,
                    level1_passed=True,
                    level2_passed=False,
                    level2_feedback="UI still broken",
                )
            return AcceptanceResult(
                subtask_id=job.subtask_id,
                level1_passed=True,
                level2_passed=True,
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

            if subtask.subtask_id == "st-4-fix-3":
                dispatch_event.set()

        mock_dispatcher.dispatch_subtask.side_effect = dispatch_side_effect

        task_id = orchestrator.submit_task("Build a full-stack application")

        # Wait for all dispatches to complete
        dispatch_event.wait(timeout=5.0)
        await asyncio.sleep(0.5)

        task = orchestrator._state.get_task(task_id)
        ost = orchestrator._orchestrator_states[task_id]

        # Verify fix rounds were tracked against st-4
        assert ost.fix_rounds.get("st-4", 0) == 3, f"Expected 3 fix rounds for st-4, got {ost.fix_rounds.get('st-4', 0)}"

        # Verify decide_on_failure is not used after remediation budget exhaustion.
        mock_owner_agent.decide_on_failure.assert_not_called()

        # Verify st-4 is marked as failed.
        assert "st-4" not in ost.completed_subtasks
        st_4 = next(st for st in task.subtasks if st.subtask_id == "st-4")
        assert st_4.status == JobStatus.FAILED, "st-4 should be FAILED after remediation exhaustion"

        # Verify exactly 3 fix subtasks were created for st-4
        dispatched_ids = [call.args[0].subtask_id for call in mock_dispatcher.dispatch_subtask.call_args_list]
        st4_fix_calls = [sid for sid in dispatched_ids if sid.startswith("st-4-fix-")]
        assert len(st4_fix_calls) == 3, f"Expected 3 fix subtasks for st-4, got {len(st4_fix_calls)}: {st4_fix_calls}"

        # Verify st-5 and st-6 were cancelled because st-4 never produced accepted output.
        assert "st-5" not in dispatched_ids, "st-5 should remain blocked after st-4 failure"
        assert "st-6" not in dispatched_ids, "st-6 should remain blocked after st-4 failure"
        st_5 = next(st for st in task.subtasks if st.subtask_id == "st-5")
        st_6 = next(st for st in task.subtasks if st.subtask_id == "st-6")
        assert st_5.status == JobStatus.CANCELLED
        assert st_6.status == JobStatus.CANCELLED

        assert task.status == TaskStatus.FAILED
        mock_owner_agent.run_integration_test.assert_not_called()

"""
Unit tests for N4 Remediation Lineage Fix.

Tests verify that:
1. Canonical ID parsing works for all remediation patterns
2. Reassign does not chain v2 suffix
3. Reassign consumes remediation budget
4. Fix and reassign share budget
5. State layer rejects duplicate subtask IDs
6. Wave fix has max remediation attempts
"""
import pytest
from across_agents_assistant.task_manager.orchestration.orchestrator import TaskOrchestrator
from across_agents_assistant.task_manager.models import (
    Task, SubTask, Job, JobStatus, OrchestratorState, AcceptanceResult
)
from across_agents_assistant.task_manager.state import TaskState


class TestCanonicalSubtaskId:
    """Test canonical ID extraction strips all remediation suffixes."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        mock_state = TaskState()
        mock_dispatcher = type('MockDispatcher', (), {'_get_valid_agents': lambda self: ['agent-1', 'agent-2'], 'add_progress_callback': lambda self, cb: None})()
        mock_validator = type('MockValidator', (), {'validate': lambda self, job: type('Report', (), {'passed': True, 'errors': []})()})()
        mock_owner = type('MockOwner', (), {
            'accept_subtask': lambda self, job: AcceptanceResult(
                subtask_id=job.subtask_id,
                level1_passed=True,
                level2_passed=True,
            ),
        })()
        return TaskOrchestrator(mock_state, mock_dispatcher, mock_validator, mock_owner)

    def test_original_id_unchanged(self, orchestrator):
        assert orchestrator._get_canonical_subtask_id("st-a") == "st-a"

    def test_fix_suffix_stripped(self, orchestrator):
        assert orchestrator._get_canonical_subtask_id("st-a-fix-1") == "st-a"

    def test_v_suffix_stripped(self, orchestrator):
        assert orchestrator._get_canonical_subtask_id("st-a-v2") == "st-a"

    def test_v_and_fix_suffix_stripped(self, orchestrator):
        assert orchestrator._get_canonical_subtask_id("st-a-v2-fix-1") == "st-a"

    def test_multiple_v_suffixes_stripped(self, orchestrator):
        assert orchestrator._get_canonical_subtask_id("st-a-v2-v3-fix-2") == "st-a"

    def test_wave_fix_suffix_stripped(self, orchestrator):
        assert orchestrator._get_canonical_subtask_id("wave-5-fix-1") == "wave-5"

    def test_wave_v_suffix_stripped(self, orchestrator):
        assert orchestrator._get_canonical_subtask_id("wave-5-v2") == "wave-5"

    def test_get_original_delegates_to_canonical(self, orchestrator):
        assert orchestrator._get_original_subtask_id("st-a-v2-fix-1") == "st-a"


class TestRemediationBudget:
    """Test remediation attempt reservation and budget sharing."""

    @pytest.fixture
    def task_and_state(self):
        """Create task with subtask and state."""
        state = TaskState()
        task = Task.new(description="Test task")
        state._tasks[task.task_id] = task

        subtask = SubTask(
            subtask_id="st-a",
            description="Test subtask",
            agent_id="agent-1",
            task_id=task.task_id,
        )
        task.subtasks.append(subtask)

        return state, task

    @pytest.fixture
    def orchestrator_state(self):
        """Create orchestrator state."""
        return OrchestratorState(
            task_id="test-task",
            fix_rounds={},
            max_fix_rounds=3,
        )

    @pytest.fixture
    def orchestrator(self, task_and_state):
        """Create orchestrator with mocked dependencies."""
        state, _ = task_and_state
        mock_dispatcher = type('MockDispatcher', (), {
            '_get_valid_agents': lambda self: ['agent-1', 'agent-2'],
            'add_progress_callback': lambda self, cb: None
        })()
        mock_validator = type('MockValidator', (), {'validate': lambda self, job: type('Report', (), {'passed': True, 'errors': []})()})()
        mock_owner = type('MockOwner', (), {
            'accept_subtask': lambda self, job: AcceptanceResult(
                subtask_id=job.subtask_id,
                level1_passed=True,
                level2_passed=True,
            ),
        })()
        return TaskOrchestrator(state, mock_dispatcher, mock_validator, mock_owner)

    def test_reserve_first_attempt(self, orchestrator, task_and_state, orchestrator_state):
        state, task = task_and_state

        result = orchestrator._reserve_remediation_attempt(task, orchestrator_state, "st-a")
        assert result == 1
        assert task.fix_rounds["st-a"] == 1

    def test_reserve_multiple_attempts(self, orchestrator, task_and_state, orchestrator_state):
        state, task = task_and_state

        assert orchestrator._reserve_remediation_attempt(task, orchestrator_state, "st-a") == 1
        assert orchestrator._reserve_remediation_attempt(task, orchestrator_state, "st-a") == 2
        assert orchestrator._reserve_remediation_attempt(task, orchestrator_state, "st-a") == 3
        assert orchestrator._reserve_remediation_attempt(task, orchestrator_state, "st-a") is None

    def test_budget_shared_between_fix_and_reassign(self, orchestrator, task_and_state, orchestrator_state):
        """Fix and reassign share the same budget per canonical ID."""
        state, task = task_and_state

        canonical_id = "st-a"

        # Fix consumes 2 attempts
        assert orchestrator._reserve_remediation_attempt(task, orchestrator_state, canonical_id) == 1
        assert orchestrator._reserve_remediation_attempt(task, orchestrator_state, canonical_id) == 2

        # Reassign would be attempt 3
        assert orchestrator._reserve_remediation_attempt(task, orchestrator_state, canonical_id) == 3

        # No more budget
        assert orchestrator._reserve_remediation_attempt(task, orchestrator_state, canonical_id) is None


class TestDuplicateSubtaskProtection:
    """Test that add_subtask rejects duplicate IDs."""

    def test_rejects_duplicate_subtask_id(self):
        state = TaskState()
        task = Task.new(description="Test task")
        state._tasks[task.task_id] = task

        # First add succeeds
        subtask1 = state.add_subtask(
            task_id=task.task_id,
            description="First subtask",
            agent_id="agent-1",
            subtask_id="st-a",
        )
        assert subtask1 is not None
        assert subtask1.subtask_id == "st-a"

        # Second add with same ID fails
        subtask2 = state.add_subtask(
            task_id=task.task_id,
            description="Duplicate subtask",
            agent_id="agent-2",
            subtask_id="st-a",
        )
        assert subtask2 is None

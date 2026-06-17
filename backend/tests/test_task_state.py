import os
from typing import Dict, List

import pytest
from across_agents_assistant.legacy_task_history.state import TaskState
from across_agents_assistant.legacy_task_history.models import JobStatus


class TestTaskTypePersistence:
    def test_normalize_delivery_task_types_composite(self):
        types, mode = TaskState._normalize_delivery_task_types(["functional", "artifact"])
        assert types == ["functional", "artifact"]
        assert mode == "composite"

    def test_normalize_delivery_task_types_single(self):
        types, mode = TaskState._normalize_delivery_task_types(["functional"])
        assert types == ["functional"]
        assert mode == "functional"

    def test_normalize_delivery_task_types_defaults_to_external(self):
        types, mode = TaskState._normalize_delivery_task_types(None)
        assert types == []
        assert mode == "external"

    def test_normalize_delivery_task_types_empty(self):
        types, mode = TaskState._normalize_delivery_task_types([])
        assert types == []
        assert mode == "external"

    def test_normalize_delivery_task_types_rejects_unknown(self):
        try:
            TaskState._normalize_delivery_task_types(["research"])
        except ValueError as exc:
            assert "Unsupported task type" in str(exc)
        else:
            raise AssertionError("Expected invalid task type to be rejected")

    def test_create_task_persists_task_types_in_memory(self):
        state = TaskState()
        task = state.create_task(
            description="Build a todo tool",
            task_types=["functional", "artifact"],
            delivery_mode="composite",
        )
        assert task.task_types == ["functional", "artifact"]
        assert task.delivery_mode == "composite"

    def test_create_task_without_task_types_defaults_to_external_boundary(self):
        state = TaskState()
        task = state.create_task(description="External Orchestrator task")
        assert task.task_types == []
        assert task.delivery_mode == "external"

    def test_create_task_persists_task_types_to_db(self):
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        state.set_persistence(persistence)

        task = state.create_task(
            description="Build a todo tool",
            task_types=["functional", "artifact"],
            delivery_mode="composite",
        )

        saved = persistence.tasks[task.task_id]
        assert saved["task_types"] == ["functional", "artifact"]
        assert saved["delivery_mode"] == "composite"

    def test_persist_task_includes_task_types_in_payload(self):
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        state.set_persistence(persistence)

        task = state.create_task(
            description="Build a todo tool",
            task_types=["functional"],
        )

        saved = persistence.tasks[task.task_id]
        assert saved["task_types"] == ["functional"]
        assert saved["delivery_mode"] == "functional"

    def test_persisted_final_status_waits_for_delivery_contract_acceptance(self):
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        persistence.get_delivery_contract = lambda task_id: {"task_types": ["functional"]}
        state.set_persistence(persistence)

        task = state.create_task(
            description="Build a functional app",
            task_types=["functional"],
            delivery_mode="functional",
        )
        subtask = state.add_subtask(task.task_id, "Build app", "deepseek")
        state.update_subtask_status(task.task_id, subtask.subtask_id, JobStatus.COMPLETED)

        assert state.derive_persisted_final_status(task.task_id) is None

        task.last_owner_decision = {"delivery_quality": {"delivery_quality": "passed"}}
        state._persist_task(task)

        assert state.derive_persisted_final_status(task.task_id) == "completed"

        task.last_owner_decision = {"delivery_quality": {"delivery_quality": "failed"}}
        state._persist_task(task)

        assert state.derive_persisted_final_status(task.task_id) == "failed"


class TestIsAllSubtasksCompleted:
    def test_all_subtasks_completed_returns_true(self):
        state = TaskState()
        task = state.create_task("Test task")
        st1 = state.add_subtask(task.task_id, "Subtask 1", "agent-1")
        st2 = state.add_subtask(task.task_id, "Subtask 2", "agent-2")

        state.update_subtask_status(task.task_id, st1.subtask_id, JobStatus.COMPLETED)
        state.update_subtask_status(task.task_id, st2.subtask_id, JobStatus.COMPLETED)

        assert state.is_all_subtasks_completed(task.task_id) is True

    def test_cancelled_subtask_returns_false(self):
        state = TaskState()
        task = state.create_task("Test task")
        st1 = state.add_subtask(task.task_id, "Subtask 1", "agent-1")
        st2 = state.add_subtask(task.task_id, "Subtask 2", "agent-2")

        state.update_subtask_status(task.task_id, st1.subtask_id, JobStatus.COMPLETED)
        state.update_subtask_status(task.task_id, st2.subtask_id, JobStatus.CANCELLED)

        assert state.is_all_subtasks_completed(task.task_id) is False

    def test_one_subtask_pending_returns_false(self):
        state = TaskState()
        task = state.create_task("Test task")
        st1 = state.add_subtask(task.task_id, "Subtask 1", "agent-1")
        st2 = state.add_subtask(task.task_id, "Subtask 2", "agent-2")

        state.update_subtask_status(task.task_id, st1.subtask_id, JobStatus.COMPLETED)
        # st2 remains PENDING

        assert state.is_all_subtasks_completed(task.task_id) is False

    def test_one_subtask_running_returns_false(self):
        state = TaskState()
        task = state.create_task("Test task")
        st1 = state.add_subtask(task.task_id, "Subtask 1", "agent-1")
        st2 = state.add_subtask(task.task_id, "Subtask 2", "agent-2")

        state.update_subtask_status(task.task_id, st1.subtask_id, JobStatus.COMPLETED)
        state.update_subtask_status(task.task_id, st2.subtask_id, JobStatus.RUNNING)

        assert state.is_all_subtasks_completed(task.task_id) is False

    def test_task_not_found_returns_false(self):
        state = TaskState()
        assert state.is_all_subtasks_completed("nonexistent-task-id") is False

    def test_task_with_no_subtasks_returns_false(self):
        state = TaskState()
        task = state.create_task("Empty task")
        assert state.is_all_subtasks_completed(task.task_id) is False

    def test_all_failed_returns_false(self):
        state = TaskState()
        task = state.create_task("Test task")
        st1 = state.add_subtask(task.task_id, "Subtask 1", "agent-1")
        st2 = state.add_subtask(task.task_id, "Subtask 2", "agent-2")

        state.update_subtask_status(task.task_id, st1.subtask_id, JobStatus.FAILED)
        state.update_subtask_status(task.task_id, st2.subtask_id, JobStatus.FAILED)

        assert state.is_all_subtasks_completed(task.task_id) is False


class TestGetTaskBySubtask:
    def test_finds_correct_parent_task(self):
        state = TaskState()
        task_a = state.create_task("Task A")
        task_b = state.create_task("Task B")

        st_a1 = state.add_subtask(task_a.task_id, "Subtask A1", "agent-1")
        st_b1 = state.add_subtask(task_b.task_id, "Subtask B1", "agent-2")

        found = state.get_task_by_subtask(st_a1.subtask_id)
        assert found is not None
        assert found.task_id == task_a.task_id

        found = state.get_task_by_subtask(st_b1.subtask_id)
        assert found is not None
        assert found.task_id == task_b.task_id

    def test_returns_none_for_unknown_subtask(self):
        state = TaskState()
        task = state.create_task("Task")
        state.add_subtask(task.task_id, "Subtask", "agent-1")

        assert state.get_task_by_subtask("unknown-subtask-id") is None

    def test_returns_none_when_no_tasks(self):
        state = TaskState()
        assert state.get_task_by_subtask("any-subtask-id") is None


class TestSubtaskObservability:
    def test_pending_subtask_reports_unsatisfied_dependencies(self):
        state = TaskState()
        task = state.create_task("Task")
        dependency = state.add_subtask(task.task_id, "Dependency", "agent-1")
        blocked = state.add_subtask(task.task_id, "Blocked", "agent-2")
        blocked.dependencies = [dependency.subtask_id]

        info = state.get_subtask_observability(task.task_id, blocked.subtask_id)

        assert info["blocked_reason"] == "waiting_on_dependencies"
        assert info["waiting_on_dependencies"] == [dependency.subtask_id]

    def test_running_subtask_reports_running_duration(self):
        state = TaskState()
        task = state.create_task("Task")
        subtask = state.add_subtask(task.task_id, "Running", "agent-1")
        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.RUNNING)
        state._jobs[job.job_id].started_at = 100.0

        info = state.get_subtask_observability(task.task_id, subtask.subtask_id, now=160.0)

        assert info["blocked_reason"] is None
        assert info["waiting_on_dependencies"] == []
        assert info["running_for_seconds"] == 60.0


class FakePersistence:
    def __init__(self):
        self.jobs = {}

    def save_job(self, job):
        self.jobs[job["job_id"]] = dict(job)


class RestorePersistence:
    def __init__(self):
        self.task = {
            "task_id": "task-restore",
            "description": "Restore task",
            "task_type": "unknown",
            "status": "running",
            "project_dir": "/tmp/demo",
            "error": None,
            "can_handle_directly": 0,
            "direct_response": None,
            "created_at": 1.0,
            "updated_at": 2.0,
            "owner_session_id": "owner-fixed-session",
            "owner_state_summary": {"owner_session_id": "owner-fixed-session"},
            "last_owner_decision": {"recommended_action": "wave_fix"},
        }
        self.subtasks = [{
            "subtask_id": "st-1",
            "description": "Do work",
            "agent_id": "deepseek",
            "priority": 1,
            "dependencies": [],
            "status": "completed",
            "progress": 1.0,
            "wave_number": 1,
            "error_message": None,
            "output_file": "/tmp/demo/app.py",
            "duration": 1.5,
        }]
        self.waves = [{
            "wave_id": "wave-1",
            "wave_number": 1,
            "status": "completed",
            "is_blocked": 0,
            "governance_status": "approved",
            "blocked_by_wave": None,
            "is_revalidating": 0,
            "owner_decision": {"recommended_action": "approve"},
        }]
        self.acceptance_records = [{
            "acceptance_id": "acc-1",
            "task_id": "task-restore",
            "subtask_id": "st-1",
            "wave_number": 1,
            "level": "wave",
            "decision": "approve",
            "deterministic_passed": True,
            "judge_passed": True,
            "failed_checks": [],
            "missing_artifacts": [],
            "feedback": None,
            "root_cause_scope": "current_wave",
            "root_cause_wave": 1,
            "root_cause_artifact_ids": [],
            "recommended_action": "approve",
            "preferred_agent": None,
            "owner_session_id": "owner-fixed-session",
            "created_at": 3.0,
        }]
        self.artifact_records = [{
            "artifact_id": "art-1",
            "task_id": "task-restore",
            "subtask_id": "st-1",
            "wave_number": 1,
            "name": "app.py",
            "artifact_type": "job_output",
            "version": 2,
            "status": "accepted",
            "content_ref": "/tmp/demo/app.py",
            "produced_by": "deepseek",
            "schema_version": "1.0",
            "metadata": {},
            "source_artifact_ids": [],
            "supersedes_artifact_id": None,
            "superseded_by_artifact_id": None,
            "created_at": 2.5,
        }]

    def get_task(self, task_id):
        return self.task if task_id == self.task["task_id"] else None

    def get_subtasks(self, task_id):
        return list(self.subtasks)

    def get_waves(self, task_id):
        return list(self.waves)

    def get_jobs_by_subtask(self, subtask_id):
        return []

    def get_acceptance_records(self, task_id):
        return list(self.acceptance_records)

    def get_artifact_records(self, task_id):
        return list(self.artifact_records)


class TestJobPersistence:
    def test_update_job_status_persists(self):
        state = TaskState()
        state.set_persistence(FakePersistence())
        task = state.create_task("Task")
        subtask = state.add_subtask(task.task_id, "Subtask", "deepseek")
        job = state.create_job(subtask)

        state.update_job_status(job.job_id, JobStatus.RUNNING)

        assert state._persistence.jobs[job.job_id]["status"] == "running"

    def test_update_job_progress_persists(self):
        state = TaskState()
        state.set_persistence(FakePersistence())
        task = state.create_task("Task")
        subtask = state.add_subtask(task.task_id, "Subtask", "deepseek")
        job = state.create_job(subtask)

        state.update_job_progress(job.job_id, 0.4, "working")

        persisted = state._persistence.jobs[job.job_id]
        assert persisted["progress"] == 0.4
        assert persisted["status"] == "running"

    def test_complete_job_persists_failed_subtask_status(self):
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        state.set_persistence(persistence)
        task = state.create_task("Task")
        subtask = state.add_subtask(task.task_id, "Subtask", "deepseek")
        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.RUNNING)

        state.complete_job(job.job_id, success=False, error="timeout")

        persisted_subtask = persistence.subtasks[task.task_id][0]
        persisted_task = persistence.tasks[task.task_id]
        persisted_job = persistence.jobs[task.task_id][0]
        assert persisted_subtask["status"] == "failed"
        assert persisted_subtask["error_message"] == "timeout"
        assert persisted_job["status"] == "failed"
        assert persisted_task["updated_at"] >= task.created_at

    def test_cancel_job_persists_cancelled_subtask_status(self):
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        state.set_persistence(persistence)
        task = state.create_task("Task")
        subtask = state.add_subtask(task.task_id, "Subtask", "deepseek")
        job = state.create_job(subtask)
        state.update_job_status(job.job_id, JobStatus.RUNNING)

        state.cancel_job(job.job_id, error="cancelled by test")

        persisted_subtask = persistence.subtasks[task.task_id][0]
        persisted_job = persistence.jobs[task.task_id][0]
        assert persisted_subtask["status"] == "cancelled"
        assert persisted_job["status"] == "cancelled"


class TestTaskRestore:
    def test_restore_task_recovers_owner_context(self):
        state = TaskState()
        state.set_persistence(RestorePersistence())

        restored = state.restore_task("task-restore")

        assert restored is True
        task = state.get_task("task-restore")
        assert task is not None
        assert task.owner_session_id == "owner-fixed-session"
        assert task.last_owner_decision["recommended_action"] == "approve"
        assert task.owner_state_summary["artifact_versions"]["app.py"] == 2
        assert task.waves[0].governance_status == "approved"


class RecordingPersistence:
    """Minimal persistence that records save_subtask calls for verification."""

    def __init__(self):
        self.saved_subtasks: List[Dict] = []

    def save_task(self, _task):
        pass

    def save_subtask(self, subtask: Dict):
        self.saved_subtasks.append(dict(subtask))

    def save_job(self, _job):
        pass

    def save_wave(self, _wave):
        pass

    def get_task(self, _task_id):
        return None

    def get_subtasks(self, _task_id):
        return []

    def get_waves(self, _task_id):
        return []

    def get_jobs_by_subtask(self, _subtask_id):
        return []

    def get_acceptance_records(self, _task_id):
        return []

    def get_artifact_records(self, _task_id):
        return []


class TestRestoreCancelledDownstream:
    def test_restore_cancelled_downstream_persists_restored_subtasks(self):
        """restore_cancelled_downstream should persist each restored subtask."""
        from across_agents_assistant.legacy_task_history.models import SubTask

        state = TaskState()
        persistence = RecordingPersistence()
        state.set_persistence(persistence)

        task = state.create_task("restore downstream")
        st_a = SubTask(subtask_id="st-a", description="A", agent_id="claude", dependencies=[])
        st_b = SubTask(subtask_id="st-b", description="B", agent_id="deepseek", dependencies=["st-a"])
        st_c = SubTask(subtask_id="st-c", description="C", agent_id="minimax", dependencies=["st-b"])
        st_b.status = JobStatus.CANCELLED
        st_c.status = JobStatus.CANCELLED
        task.subtasks.extend([st_a, st_b, st_c])

        restored = state.restore_cancelled_downstream(task.task_id, "st-a")

        assert restored == ["st-b", "st-c"]
        assert st_b.status == JobStatus.PENDING
        assert st_c.status == JobStatus.PENDING
        saved = {row["subtask_id"]: row["status"] for row in persistence.saved_subtasks}
        assert saved["st-b"] == "pending"
        assert saved["st-c"] == "pending"


class TestCancelDownstreamSubtasks:
    """NEW-4: cancelled downstream subtasks must be persisted."""

    def test_cancel_downstream_persists_cancelled_subtasks(self):
        from across_agents_assistant.legacy_task_history.models import SubTask

        state = TaskState()
        persistence = RecordingPersistence()
        state.set_persistence(persistence)

        task = state.create_task("cancel downstream")
        st_a = SubTask(subtask_id="st-a", description="A", agent_id="claude", dependencies=[])
        st_b = SubTask(subtask_id="st-b", description="B", agent_id="deepseek", dependencies=["st-a"])
        st_c = SubTask(subtask_id="st-c", description="C", agent_id="minimax", dependencies=["st-b"])
        task.subtasks.extend([st_a, st_b, st_c])

        cancelled = state.cancel_downstream_subtasks(task.task_id, "st-a")

        assert cancelled == ["st-b", "st-c"]
        assert st_b.status == JobStatus.CANCELLED
        assert st_c.status == JobStatus.CANCELLED
        saved = {row["subtask_id"]: row["status"] for row in persistence.saved_subtasks}
        assert saved["st-b"] == "cancelled"
        assert saved["st-c"] == "cancelled"


class TestEffectiveSubtaskStatus:
    """NEW-5: _get_subtask_status should be remediation-aware."""

    def test_get_subtask_status_treats_successful_fix_as_completed_dependency(self):
        from across_agents_assistant.legacy_task_history.models import SubTask

        state = TaskState()
        task = state.create_task("effective status")
        original = SubTask(subtask_id="st-a", description="A", agent_id="deepseek", dependencies=[])
        fix = SubTask(subtask_id="st-a-fix-1", description="Fix A", agent_id="deepseek", dependencies=[])
        downstream = SubTask(subtask_id="st-b", description="B", agent_id="minimax", dependencies=["st-a"])
        original.status = JobStatus.FAILED
        fix.status = JobStatus.COMPLETED
        downstream.status = JobStatus.PENDING
        task.subtasks.extend([original, fix, downstream])

        assert state._get_subtask_status(task.task_id, "st-a") == JobStatus.COMPLETED
        ready = state.get_ready_subtasks(task.task_id, strict=True)
        assert [st.subtask_id for st in ready] == ["st-b"]

    def test_get_subtask_status_treats_successful_reassign_as_completed_dependency(self):
        from across_agents_assistant.legacy_task_history.models import SubTask

        state = TaskState()
        task = state.create_task("effective reassign status")
        original = SubTask(subtask_id="st-a", description="A", agent_id="claude", dependencies=[])
        reassigned = SubTask(subtask_id="st-a-v4", description="A retry", agent_id="hermes", dependencies=[])
        downstream = SubTask(subtask_id="st-b", description="B", agent_id="deepseek", dependencies=["st-a"])
        original.status = JobStatus.FAILED
        reassigned.status = JobStatus.COMPLETED
        downstream.status = JobStatus.PENDING
        task.subtasks.extend([original, reassigned, downstream])

        assert state._get_subtask_status(task.task_id, "st-a") == JobStatus.COMPLETED
        ready = state.get_ready_subtasks(task.task_id, strict=True)
        assert [st.subtask_id for st in ready] == ["st-b"]

    def test_get_subtask_status_does_not_satisfy_dependency_when_all_remediations_failed(self):
        from across_agents_assistant.legacy_task_history.models import SubTask

        state = TaskState()
        task = state.create_task("failed remediation status")
        original = SubTask(subtask_id="st-a", description="A", agent_id="claude", dependencies=[])
        fix = SubTask(subtask_id="st-a-fix-1", description="Fix A", agent_id="claude", dependencies=[])
        reassigned = SubTask(subtask_id="st-a-v2", description="Retry A", agent_id="hermes", dependencies=[])
        downstream = SubTask(subtask_id="st-b", description="B", agent_id="deepseek", dependencies=["st-a"])
        original.status = JobStatus.FAILED
        fix.status = JobStatus.FAILED
        reassigned.status = JobStatus.FAILED
        downstream.status = JobStatus.PENDING
        task.subtasks.extend([original, fix, reassigned, downstream])

        assert state._get_subtask_status(task.task_id, "st-a") == JobStatus.FAILED
        assert state.get_ready_subtasks(task.task_id, strict=True) == []


class FakePersistenceWithTasks:
    """Simulates TaskPersistenceService for recover_orphaned tests."""

    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self.subtasks: Dict[str, List[Dict]] = {}
        self.jobs: Dict[str, List[Dict]] = {}
        self.manifests: Dict[str, Dict] = {}
        self.waves: Dict[str, List[Dict]] = {}

    def get_all_tasks(self):
        return list(self.tasks.values())

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def get_subtasks(self, task_id):
        return list(self.subtasks.get(task_id, []))

    def get_jobs_by_subtask(self, subtask_id):
        st_jobs = []
        for task_jobs in self.jobs.values():
            for j in task_jobs:
                if j["subtask_id"] == subtask_id:
                    st_jobs.append(j)
        return st_jobs

    def get_waves(self, task_id):
        return list(self.waves.get(task_id, []))

    def get_acceptance_records(self, task_id):
        return []

    def get_artifact_records(self, task_id):
        return []

    def save_task(self, task):
        self.tasks[task["task_id"]] = dict(task)

    def save_subtask(self, subtask):
        tid = subtask["task_id"]
        if tid not in self.subtasks:
            self.subtasks[tid] = []
        existing = [s for s in self.subtasks[tid] if s["subtask_id"] == subtask["subtask_id"]]
        if existing:
            existing[0].update(dict(subtask))
        else:
            self.subtasks[tid].append(dict(subtask))

    def save_job(self, job):
        tid = None
        for task_id, task_jobs in self.jobs.items():
            if any(j["job_id"] == job["job_id"] for j in task_jobs):
                for j in task_jobs:
                    if j["job_id"] == job["job_id"]:
                        j.update(dict(job))
                return
        # Need to find task_id — fallback: store under first found subtask's task
        for task_id, st_list in self.subtasks.items():
            for st in st_list:
                if st["subtask_id"] == job.get("subtask_id"):
                    tid = task_id
                    break
        if tid is None:
            tid = "unknown"
        if tid not in self.jobs:
            self.jobs[tid] = []
        self.jobs[tid].append(dict(job))

    def get_requirement_manifest(self, task_id):
        return self.manifests.get(task_id)


def test_create_task_canonicalizes_project_dir_symlink(tmp_path):
    real_project = tmp_path / "real-project"
    real_project.mkdir()
    linked_project = tmp_path / "linked-project"
    linked_project.symlink_to(real_project, target_is_directory=True)

    state = TaskState()
    task = state.create_task("Build README.md", project_dir=str(linked_project))

    assert task.project_dir == os.path.realpath(linked_project)


def test_resolve_output_file_returns_canonical_realpath(tmp_path):
    real_project = tmp_path / "real-project"
    real_project.mkdir()
    linked_project = tmp_path / "linked-project"
    linked_project.symlink_to(real_project, target_is_directory=True)
    (real_project / "README.md").write_text("# Done\n", encoding="utf-8")

    resolved = TaskState._resolve_output_file(
        output="Created README.md",
        project_dir=str(linked_project),
        task_description="Create README.md",
    )

    assert resolved == os.path.realpath(real_project / "README.md")


def test_resolve_output_file_ignores_directory_candidates(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    resolved = TaskState._resolve_output_file(
        output=f"Created `{project}`",
        project_dir=str(project),
        task_description="Run the application and verify tests",
    )

    assert resolved is None


def test_resolve_output_file_ignores_paths_outside_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "README.md"
    outside.write_text("# Outside\n", encoding="utf-8")

    resolved = TaskState._resolve_output_file(
        output=f"Created `{outside}`",
        project_dir=str(project),
        task_description="Create README.md",
    )

    assert resolved is None


def test_resolve_output_file_ignores_workspace_noise(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    noisy = project / "test_import.py"
    noisy.write_text("import app\n", encoding="utf-8")

    resolved = TaskState._resolve_output_file(
        output=f"Created `{noisy}`",
        project_dir=str(project),
        task_description="Implement receipt upload endpoint",
    )

    assert resolved is None


class TestOrphanRecovery:
    """N36: recover_orphaned_persisted_tasks startup recovery."""

    def _make_task_row(self, task_id: str, status: str, desc: str = "Orphaned task"):
        return {
            "task_id": task_id,
            "description": desc,
            "status": status,
            "task_type": "unknown",
            "project_dir": "/tmp/project",
            "error": None,
            "created_at": 1000.0,
            "updated_at": 1000.0,
        }

    def _make_subtask_row(self, task_id: str, subtask_id: str, status: str):
        return {
            "subtask_id": subtask_id,
            "task_id": task_id,
            "description": "Subtask",
            "agent_id": "deepseek",
            "status": status,
            "progress": 0.0,
            "wave_number": 1,
            "dependencies": "[]",
        }

    def _make_job_row(self, job_id: str, subtask_id: str, status: str):
        return {
            "job_id": job_id,
            "subtask_id": subtask_id,
            "agent_id": "deepseek",
            "task_description": "Job",
            "status": status,
            "result": None,
            "error": None,
            "failure_reason": None,
            "completed_at": None,
        }

    def test_recover_orphaned_paused_running_task(self):
        """Running task with running subtask/job should be marked paused."""
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        state.set_persistence(persistence)

        t = self._make_task_row("task-orphan-1", "running")
        persistence.save_task(t)
        st = self._make_subtask_row("task-orphan-1", "st-orphan", "running")
        persistence.save_subtask(st)
        j = self._make_job_row("job-orphan-1", "st-orphan", "running")
        persistence.save_job(j)

        recovered = state.recover_orphaned_persisted_tasks()

        assert recovered == 1

        saved_task = persistence.get_task("task-orphan-1")
        assert saved_task["status"] == "paused"
        assert "orphaned" in (saved_task.get("error") or "").lower()

        saved_st = persistence.get_subtasks("task-orphan-1")
        assert saved_st[0]["status"] == "paused"

        saved_jobs = persistence.get_jobs_by_subtask("st-orphan")
        assert saved_jobs[0]["status"] == "failed"
        assert saved_jobs[0]["failure_reason"] == "orphan_recovery"

    def test_recover_orphaned_dispatched_job(self):
        """A DISPATCHED job should also be marked failed."""
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        state.set_persistence(persistence)

        t = self._make_task_row("task-orphan-2", "pending")
        persistence.save_task(t)
        st = self._make_subtask_row("task-orphan-2", "st-dispatched", "pending")
        persistence.save_subtask(st)
        j = self._make_job_row("job-orphan-2", "st-dispatched", "dispatched")
        persistence.save_job(j)

        recovered = state.recover_orphaned_persisted_tasks()

        assert recovered == 1
        saved_job = persistence.get_jobs_by_subtask("st-dispatched")[0]
        assert saved_job["status"] == "failed"
        assert saved_job["failure_reason"] == "orphan_recovery"

    def test_recover_orphaned_skips_completed_task(self):
        """Tasks already in terminal state should not be touched."""
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        state.set_persistence(persistence)

        t = self._make_task_row("task-completed", "completed")
        persistence.save_task(t)
        st = self._make_subtask_row("task-completed", "st-completed", "completed")
        persistence.save_subtask(st)

        recovered = state.recover_orphaned_persisted_tasks()

        assert recovered == 0
        assert persistence.get_task("task-completed")["status"] == "completed"

    def test_recover_orphaned_archives_stale_remediation_for_terminal_task(self):
        """Terminal tasks should not become running again because a retry row is stale."""
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        state.set_persistence(persistence)

        t = self._make_task_row("task-terminal-remediation", "completed_with_failures")
        persistence.save_task(t)
        original = self._make_subtask_row("task-terminal-remediation", "st-docs", "failed")
        retry = self._make_subtask_row("task-terminal-remediation", "st-docs-v2", "running")
        persistence.save_subtask(original)
        persistence.save_subtask(retry)
        j = self._make_job_row("job-stale-retry", "st-docs-v2", "running")
        persistence.save_job(j)

        recovered = state.recover_orphaned_persisted_tasks()

        assert recovered == 0
        assert persistence.get_task("task-terminal-remediation")["status"] == "completed_with_failures"
        retry_row = next(
            st for st in persistence.get_subtasks("task-terminal-remediation")
            if st["subtask_id"] == "st-docs-v2"
        )
        assert retry_row["status"] == "cancelled"
        assert "stale remediation" in retry_row["error_message"].lower()
        saved_job = persistence.get_jobs_by_subtask("st-docs-v2")[0]
        assert saved_job["status"] == "failed"
        assert saved_job["failure_reason"] == "orphan_recovery"

    def test_recover_orphaned_idempotent(self):
        """Calling recovery twice should not produce extra changes."""
        state = TaskState()
        persistence = FakePersistenceWithTasks()
        state.set_persistence(persistence)

        t = self._make_task_row("task-orphan-idem", "running")
        persistence.save_task(t)
        st = self._make_subtask_row("task-orphan-idem", "st-idem", "running")
        persistence.save_subtask(st)
        j = self._make_job_row("job-idem-1", "st-idem", "running")
        persistence.save_job(j)

        first = state.recover_orphaned_persisted_tasks()
        assert first == 1

        second = state.recover_orphaned_persisted_tasks()
        assert second == 0

        saved_job = persistence.get_jobs_by_subtask("st-idem")[0]
        assert saved_job["error"] is not None
        # Verify error is not double-appended
        assert saved_job["error"].count("Backend restarted") == 1


def test_derive_persisted_final_status_all_business_completed():
    from across_agents_assistant.legacy_task_history.models import SubTask
    persistence = FakePersistenceWithTasks()
    persistence.tasks["task-done"] = {
        "task_id": "task-done",
        "description": "done",
        "status": "running",
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    persistence.subtasks["task-done"] = [
        {"subtask_id": "task-done-decompose", "task_id": "task-done", "description": "decompose", "agent_id": "owner", "status": "completed", "wave_number": 0, "progress": 1.0, "dependencies": [], "error_message": None},
        {"subtask_id": "st-a", "task_id": "task-done", "description": "A", "agent_id": "deepseek", "status": "completed", "wave_number": 1, "progress": 1.0, "dependencies": [], "error_message": None},
        {"subtask_id": "st-b", "task_id": "task-done", "description": "B", "agent_id": "minimax", "status": "completed", "wave_number": 1, "progress": 1.0, "dependencies": [], "error_message": None},
    ]
    state = TaskState()
    state.set_persistence(persistence)

    derived = state.derive_persisted_final_status("task-done")

    assert derived == "completed"


def test_derive_persisted_final_status_required_manifest_missing_returns_failed(tmp_path):
    persistence = FakePersistenceWithTasks()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "main.py").write_text("print('ok')\n")
    persistence.tasks["task-missing"] = {
        "task_id": "task-missing",
        "description": "missing required file",
        "status": "running",
        "project_dir": str(project_dir),
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    persistence.subtasks["task-missing"] = [
        {"subtask_id": "st-a", "task_id": "task-missing", "description": "A", "agent_id": "deepseek", "status": "completed", "wave_number": 1, "progress": 1.0, "dependencies": [], "error_message": None},
    ]
    persistence.manifests["task-missing"] = {
        "manifest_id": "manifest-task-missing",
        "task_id": "task-missing",
        "project_dir": str(project_dir),
        "deliverables": [
            {"path_hint": "main.py", "required": True, "status": "accepted"},
            {"path_hint": "README.md", "required": True, "status": "assigned"},
        ],
        "quality_checks": [],
    }
    state = TaskState()
    state.set_persistence(persistence)

    derived = state.derive_persisted_final_status("task-missing")

    assert derived == "failed"


def test_derive_persisted_final_status_defers_with_active_remediation():
    persistence = FakePersistenceWithTasks()
    persistence.tasks["task-remediating"] = {
        "task_id": "task-remediating",
        "description": "remediating",
        "status": "running",
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    persistence.subtasks["task-remediating"] = [
        {
            "subtask_id": "st-a",
            "task_id": "task-remediating",
            "description": "A",
            "agent_id": "deepseek",
            "status": "failed",
            "wave_number": 1,
            "progress": 0.0,
            "dependencies": [],
            "error_message": "needs fix",
        },
        {
            "subtask_id": "st-b",
            "task_id": "task-remediating",
            "description": "B",
            "agent_id": "minimax",
            "status": "cancelled",
            "wave_number": 2,
            "progress": 0.0,
            "dependencies": ["st-a"],
            "error_message": None,
        },
        {
            "subtask_id": "st-a-fix-1",
            "task_id": "task-remediating",
            "description": "Fix A",
            "agent_id": "claude",
            "status": "running",
            "wave_number": 1,
            "progress": 0.0,
            "dependencies": [],
            "error_message": None,
        },
    ]
    state = TaskState()
    state.set_persistence(persistence)

    derived = state.derive_persisted_final_status("task-remediating")

    assert derived is None
    assert persistence.tasks["task-remediating"]["status"] == "running"


def test_recover_orphaned_repairs_stale_running_completed_task_instead_of_pausing():
    from across_agents_assistant.legacy_task_history.models import SubTask
    persistence = FakePersistenceWithTasks()
    persistence.tasks["task-done"] = {
        "task_id": "task-done",
        "description": "done",
        "status": "running",
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    persistence.subtasks["task-done"] = [
        {"subtask_id": "st-a", "task_id": "task-done", "description": "A", "agent_id": "deepseek", "status": "completed", "wave_number": 1, "progress": 1.0, "dependencies": [], "error_message": None},
        {"subtask_id": "st-b", "task_id": "task-done", "description": "B", "agent_id": "minimax", "status": "completed", "wave_number": 1, "progress": 1.0, "dependencies": [], "error_message": None},
    ]
    persistence.jobs["task-done"] = [{"job_id": "job-a", "subtask_id": "st-a", "agent_id": "deepseek", "task_description": "A", "status": "running", "result": None, "error": None, "failure_reason": None, "completed_at": None}]
    state = TaskState()
    state.set_persistence(persistence)

    recovered = state.recover_orphaned_persisted_tasks(reason="test_restart", auto_resume=False)

    assert recovered == 0
    assert persistence.tasks["task-done"]["status"] == "completed"
    assert persistence.tasks["task-done"].get("error") in (None, "")


def test_recover_orphaned_repairs_stale_running_failed_task_instead_of_suspending():
    from across_agents_assistant.legacy_task_history.models import SubTask
    persistence = FakePersistenceWithTasks()
    persistence.tasks["task-failed"] = {
        "task_id": "task-failed",
        "description": "failed",
        "status": "running",
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    persistence.subtasks["task-failed"] = [
        {"subtask_id": "st-ok", "task_id": "task-failed", "description": "A", "agent_id": "deepseek", "status": "completed", "wave_number": 1, "progress": 1.0, "dependencies": [], "error_message": None},
        {"subtask_id": "st-bad", "task_id": "task-failed", "description": "B", "agent_id": "minimax", "status": "failed", "wave_number": 1, "progress": 0.0, "dependencies": [], "error_message": "LLM error"},
        {"subtask_id": "st-later", "task_id": "task-failed", "description": "C", "agent_id": "claude", "status": "cancelled", "wave_number": 2, "progress": 0.0, "dependencies": [], "error_message": None},
    ]
    state = TaskState()
    state.set_persistence(persistence)

    recovered = state.recover_orphaned_persisted_tasks(reason="test_restart", auto_resume=False)

    assert recovered == 0
    assert persistence.tasks["task-failed"]["status"] == "failed"
    assert "cancelled" in persistence.tasks["task-failed"]["error"].lower()


def test_restore_task_can_restore_second_task_without_taskstatus_shadowing():
    state = TaskState()
    persistence = FakePersistenceWithTasks()
    state.set_persistence(persistence)

    persistence.tasks["task-a"] = {
        "task_id": "task-a",
        "description": "first recovered task",
        "task_type": "unknown",
        "status": "failed",
        "project_dir": None,
        "owner_agent": None,
        "allowed_subtask_agents": [],
        "created_at": 1.0,
        "updated_at": 1.0,
    }
    persistence.tasks["task-b"] = {
        "task_id": "task-b",
        "description": "second recovered task",
        "task_type": "unknown",
        "status": "pending",
        "project_dir": None,
        "owner_agent": None,
        "allowed_subtask_agents": [],
        "created_at": 2.0,
        "updated_at": 2.0,
    }
    persistence.subtasks["task-a"] = []
    persistence.subtasks["task-b"] = []
    persistence.waves["task-a"] = []
    persistence.waves["task-b"] = []

    assert state.restore_task("task-a") is False
    assert state.restore_task("task-b") is True


def test_restore_task_startup_mode_allows_multiple_pending_recovered_tasks():
    state = TaskState()
    persistence = FakePersistenceWithTasks()
    state.set_persistence(persistence)

    for task_id in ("task-one", "task-two"):
        persistence.tasks[task_id] = {
            "task_id": task_id,
            "description": task_id,
            "task_type": "unknown",
            "status": "pending",
            "project_dir": None,
            "owner_agent": None,
            "allowed_subtask_agents": [],
            "created_at": 1.0,
            "updated_at": 1.0,
            "error": "Recovered after backend_startup; orphaned jobs were reset and task can resume.",
        }
        persistence.subtasks[task_id] = []
        persistence.waves[task_id] = []

    assert state.restore_task("task-one", allow_concurrent=True) is True
    assert state.restore_task("task-two", allow_concurrent=True) is True
    assert state.get_task("task-one") is not None
    assert state.get_task("task-two") is not None


def test_get_tasks_waiting_for_keys_from_persistence():
    persistence = FakePersistenceWithTasks()
    persistence.tasks["task-wait"] = {
        "task_id": "task-wait",
        "description": "waiting",
        "status": "pending",
        "error": "Waiting for API keys to sync before resuming decomposition.",
        "last_owner_decision": {
            "blocked_reason": "waiting_for_keys",
            "recoverable": True,
            "next_repair_action": "keys_synced",
        },
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    state = TaskState()
    state.set_persistence(persistence)

    waiting = state.get_tasks_waiting_for_keys()

    assert waiting == ["task-wait"]

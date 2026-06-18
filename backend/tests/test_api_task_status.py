"""Tests for _compute_task_status edge cases.

Covers the all-failed vs partial-success distinction added as part
of the N47 follow-up fix (2026-05-15).
"""

import os
import tempfile

os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from across_agents_assistant.api_server import _compute_task_status
from across_agents_assistant.task_history.models import JobStatus, SubTask, Task, TaskStatus
from across_agents_assistant.task_history.state import TaskState


def test_compute_task_status_pending_task_without_subtasks_returns_created():
    state = TaskState()
    task = Task(task_id="task-empty", description="Pending external task", status=TaskStatus.PENDING)

    assert _compute_task_status(task, state) == "created"


def test_compute_task_status_all_failed_returns_failed():
    """When every original business subtask is FAILED, the status should be 'failed'."""
    state = TaskState()
    task = state.create_task("all failed")
    st_a = SubTask(subtask_id="st-a", description="A", agent_id="deepseek")
    st_b = SubTask(subtask_id="st-b", description="B", agent_id="minimax")
    st_a.status = JobStatus.FAILED
    st_b.status = JobStatus.FAILED
    task.subtasks.extend([st_a, st_b])
    task.status = TaskStatus.FAILED

    assert _compute_task_status(task, state) == "failed"


def test_compute_task_status_some_completed_returns_completed_with_failures():
    """When some subtasks completed and others failed, status should be 'completed_with_failures'."""
    state = TaskState()
    task = state.create_task("partial")
    st_a = SubTask(subtask_id="st-a", description="A", agent_id="deepseek")
    st_b = SubTask(subtask_id="st-b", description="B", agent_id="minimax")
    st_a.status = JobStatus.COMPLETED
    st_b.status = JobStatus.FAILED
    task.subtasks.extend([st_a, st_b])
    # orchestrator left this RUNNING, not FAILED — terminal branch kicks in
    task.status = TaskStatus.RUNNING

    assert _compute_task_status(task, state) == "completed_with_failures"


def test_compute_task_status_all_failed_remains_failed_when_task_status_not_set():
    """Even without task.status == FAILED, all terminal should return 'failed'."""
    state = TaskState()
    task = state.create_task("implicit all failed")
    st_a = SubTask(subtask_id="st-a", description="A", agent_id="deepseek")
    st_b = SubTask(subtask_id="st-b", description="B", agent_id="minimax")
    st_a.status = JobStatus.FAILED
    st_b.status = JobStatus.CANCELLED
    task.subtasks.extend([st_a, st_b])

    st_a.status = JobStatus.FAILED
    st_b.status = JobStatus.CANCELLED
    task.subtasks.extend([st_a, st_b])
    task.status = TaskStatus.RUNNING

    assert _compute_task_status(task, state) == "failed"


def test_compute_task_status_mixed_fix_rounds_uses_business_subtasks_only():
    """Fix/reassign subtasks should not inflate the completed count."""
    state = TaskState()
    task = state.create_task("fix rounds inflating")
    original = SubTask(subtask_id="st-a", description="A", agent_id="deepseek")
    fix = SubTask(subtask_id="st-a-fix-1", description="Fix A", agent_id="deepseek")
    original.status = JobStatus.FAILED
    fix.status = JobStatus.COMPLETED
    task.subtasks.extend([original, fix])
    task.status = TaskStatus.RUNNING

    assert _compute_task_status(task, state) == "failed"


def test_compute_task_status_honors_persisted_failed_status():
    """When task.status is FAILED, API should return 'failed' regardless of subtask mix."""
    state = TaskState()
    task = state.create_task("cancelled majority")
    st_ok = SubTask(subtask_id="st-ok", description="A", agent_id="deepseek")
    st_failed = SubTask(subtask_id="st-failed", description="B", agent_id="minimax")
    st_cancelled_1 = SubTask(subtask_id="st-cancelled-1", description="C", agent_id="hermes")
    st_cancelled_2 = SubTask(subtask_id="st-cancelled-2", description="D", agent_id="hermes")
    st_ok.status = JobStatus.COMPLETED
    st_failed.status = JobStatus.FAILED
    st_cancelled_1.status = JobStatus.CANCELLED
    st_cancelled_2.status = JobStatus.CANCELLED
    task.subtasks.extend([st_ok, st_failed, st_cancelled_1, st_cancelled_2])
    task.status = TaskStatus.FAILED
    task.error = "Task failed: 2 subtask(s) were cancelled."

    assert _compute_task_status(task, state) == "failed"


def test_compute_task_status_cancelled_majority_returns_failed():
    """Even without FAILED status, terminal with cancelled majority should be 'failed'."""
    state = TaskState()
    task = state.create_task("cancelled majority")
    statuses = [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.CANCELLED]
    for index, status in enumerate(statuses):
        st = SubTask(subtask_id=f"st-{index}", description=str(index), agent_id="deepseek")
        st.status = status
        task.subtasks.append(st)
    task.status = TaskStatus.RUNNING

    assert _compute_task_status(task, state) == "failed"


def test_compute_task_status_returns_completed_with_failures_for_terminal_mixed_failures():
    state = TaskState()
    task = state.create_task("mixed")
    st_ok = SubTask(subtask_id="st-ok", description="ok", agent_id="deepseek")
    st_bad = SubTask(subtask_id="st-bad", description="bad", agent_id="minimax")
    st_ok.status = JobStatus.COMPLETED
    st_bad.status = JobStatus.FAILED
    task.subtasks.extend([st_ok, st_bad])
    task.status = TaskStatus.RUNNING

    assert _compute_task_status(task, state) == "completed_with_failures"


def test_compute_task_status_honors_completed_with_failures_terminal_status():
    state = TaskState()
    task = state.create_task("persisted terminal mixed")
    task.status = TaskStatus.COMPLETED_WITH_FAILURES
    st_ok = SubTask(subtask_id="st-ok", description="ok", agent_id="deepseek")
    st_bad = SubTask(subtask_id="st-bad", description="bad", agent_id="minimax")
    st_ok.status = JobStatus.COMPLETED
    st_bad.status = JobStatus.FAILED
    task.subtasks.extend([st_ok, st_bad])

    assert _compute_task_status(task, state) == "completed_with_failures"


def test_compute_task_status_waits_for_delivery_contract_acceptance():
    state = TaskState()
    task = state.create_task("functional delivery")
    task.status = TaskStatus.RUNNING
    st = state.add_subtask(task.task_id, "Build app", "deepseek")
    state.update_subtask_status(task.task_id, st.subtask_id, JobStatus.COMPLETED)
    state.get_delivery_contract = lambda task_id: {"task_types": ["functional"]} if task_id == task.task_id else None

    assert _compute_task_status(task, state) == "running"

    task.last_owner_decision = {"delivery_quality": {"delivery_quality": "passed"}}

    assert _compute_task_status(task, state) == "completed"


def test_quality_health_does_not_mark_historical_failed_attempts_inconsistent_when_delivery_passed():
    from across_agents_assistant.api_server import _build_quality_health

    state = TaskState()
    task = state.create_task("delivery passed after retry")
    task.status = TaskStatus.COMPLETED
    task.last_owner_decision = {
        "delivery_quality": {
            "delivery_quality": "passed",
            "missing_required": [],
            "failed_constraints": [],
        }
    }
    original = SubTask(subtask_id="st-original", description="A", agent_id="deepseek")
    original.status = JobStatus.FAILED
    remediation = SubTask(subtask_id="st-quality-readme-v2", description="Fix", agent_id="deepseek")
    remediation.status = JobStatus.FAILED
    task.subtasks.extend([original, remediation])

    health = _build_quality_health(task, state, {"deliverables": []}, [], effective_task_status="completed")

    assert health["quality_gate"] == "passed"
    assert health["orchestration_health"] == "healthy"
    assert "terminal_task_has_failed_business_subtasks" not in health["terminal_inconsistencies"]
    assert "terminal_task_has_failed_remediation" not in health["terminal_inconsistencies"]


def test_quality_health_does_not_treat_paused_remediation_as_active_when_delivery_passed():
    from across_agents_assistant.api_server import _build_quality_health

    state = TaskState()
    task = state.create_task("delivery passed with paused old repair")
    task.status = TaskStatus.COMPLETED
    task.last_owner_decision = {
        "delivery_quality": {
            "delivery_quality": "passed",
            "missing_required": [],
            "failed_constraints": [],
        }
    }
    original = SubTask(subtask_id="st-original", description="A", agent_id="deepseek")
    original.status = JobStatus.COMPLETED
    paused = SubTask(subtask_id="st-quality-old", description="Old repair", agent_id="deepseek")
    paused.status = JobStatus.PAUSED
    task.subtasks.extend([original, paused])

    health = _build_quality_health(task, state, {"deliverables": []}, [], effective_task_status="completed")

    assert health["active_remediation_subtasks"] == []
    assert health["quality_gate"] == "passed"


def test_quality_health_wave_zero_completed_when_decompose_done():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Wave
    state = TaskState()
    task = state.create_task("wave zero")
    decompose = SubTask(subtask_id=f"{task.task_id}-decompose", description="decompose", agent_id="owner")
    decompose.wave_number = 0
    decompose.status = JobStatus.COMPLETED
    task.subtasks.append(decompose)
    task.waves = [Wave(wave_id="w0", task_id=task.task_id, wave_number=0, subtasks=[decompose])]

    health = _build_quality_health(task, state, {"deliverables": []}, [])

    assert health["wave_statuses"]["0"] == "completed"
    assert health["wave_details"]["0"]["execution_status"] == "completed"
    assert health["wave_details"]["0"]["governance_status"] == "not_applicable"


def test_quality_health_blocked_by_wave_gate_not_counted_as_repair_needed():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Wave
    state = TaskState()
    task = state.create_task("blocked")
    st1 = SubTask(subtask_id="st-1", description="A", agent_id="deepseek")
    st2 = SubTask(subtask_id="st-2", description="B", agent_id="minimax", dependencies=["st-1"])
    st1.wave_number = 1
    st2.wave_number = 2
    st1.status = JobStatus.COMPLETED
    st2.status = JobStatus.PENDING
    task.subtasks.extend([st1, st2])

    wave1 = Wave(wave_id="w1", task_id=task.task_id, wave_number=1, subtasks=[st1])
    wave1.governance_status = "pending"  # Wave 1 completed but has not been approved yet
    wave2 = Wave(wave_id="w2", task_id=task.task_id, wave_number=2, subtasks=[st2])
    task.waves = [wave1, wave2]

    health = _build_quality_health(task, state, {"deliverables": []}, [])

    assert "st-2" in health["blocked_by_wave_gate"]
    assert "st-2" not in health["dispatch_repairable"]
    assert health["dispatch_repair_needed"] is False


def test_repair_task_dispatch_if_possible_skips_removed_legacy_runtime(monkeypatch):
    import across_agents_assistant.api_server as srv

    from across_agents_assistant.task_history.models import Task as TaskModel
    task = TaskModel.new(description="pending task")
    task.status = TaskStatus.PENDING

    class DummyState:
        def get_task(self, task_id):
            return task if task_id == task.task_id else None

    monkeypatch.setattr(srv, "_task_state", DummyState())

    result = srv._repair_task_dispatch_if_possible(task.task_id, reason="api_status_poll")

    assert result == {
        "task_id": task.task_id,
        "state_created": False,
        "waves_approved": [],
        "dispatched_subtasks": [],
        "reason": "api_status_poll",
        "skipped": "external_orchestrator_only",
    }


def test_quality_health_wave_zero_governance_not_applicable():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Wave
    from across_agents_assistant.task_history.state import TaskState as TS
    task = Task.new(description="quality diagnostic")
    decompose = SubTask(
        task_id=task.task_id,
        subtask_id=f"{task.task_id}-decompose",
        description="decompose",
        agent_id="owner",
        dependencies=[],
    )
    decompose.wave_number = 0
    decompose.status = JobStatus.COMPLETED
    task.subtasks.append(decompose)
    task.waves = [
        Wave(
            wave_id="wave-0",
            task_id=task.task_id,
            wave_number=0,
            subtasks=[decompose],
            status=JobStatus.COMPLETED,
        )
    ]

    health = _build_quality_health(task, TS(), None, [])

    assert health["wave_details"]["0"]["execution_status"] == "completed"
    assert health["wave_details"]["0"]["governance_status"] == "not_applicable"
    assert health["wave_details"]["0"]["effective_status"] == "completed"


def test_quality_health_failed_task_with_accepted_manifest_is_inconsistent():
    from across_agents_assistant.api_server import _build_quality_health

    state = TaskState()
    task = state.create_task("failed but manifest accepted")
    task.status = TaskStatus.FAILED
    st = SubTask(subtask_id="st-1", description="work", agent_id="deepseek")
    st.status = JobStatus.FAILED
    task.subtasks.append(st)

    health = _build_quality_health(
        task,
        state,
        {"deliverables": [{"path_hint": "main.py", "required": True, "status": "accepted"}]},
        [],
    )

    assert health["quality_gate"] == "inconsistent"
    assert "failed_task_has_fully_accepted_manifest" in health["terminal_inconsistencies"]


def test_key_readiness_reports_missing(monkeypatch):
    import os
    import across_agents_assistant.api_server as srv

    class EmptyStore:
        def get(self, provider_id: str):
            return None

    monkeypatch.setattr(srv, "_credential_cache", {}, raising=False)
    monkeypatch.setattr(srv, "_get_credential_store", lambda: EmptyStore())
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    readiness = srv._build_key_readiness()

    assert readiness["has_any_key"] is False
    assert readiness["providers"]["deepseek"] == "not_configured"
    assert readiness["providers"]["minimax"] == "not_configured"
    assert "api_keys" in readiness["readiness_blockers"]


def test_key_readiness_reports_configured_from_cache(monkeypatch):
    import across_agents_assistant.api_server as srv

    monkeypatch.setattr(srv, "_credential_cache", {"minimax": "unit-valid-minimax-key"}, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    readiness = srv._build_key_readiness()

    assert readiness["has_any_key"] is True
    assert readiness["providers"]["minimax"] == "configured"
    assert readiness["readiness_blockers"] == []


def test_key_readiness_rejects_placeholder_cache(monkeypatch):
    import across_agents_assistant.api_server as srv

    class EmptyStore:
        def get(self, provider_id: str):
            return None

    monkeypatch.setattr(srv, "_credential_cache", {"minimax": "placeholder-secret"}, raising=False)
    monkeypatch.setattr(srv, "_get_credential_store", lambda: EmptyStore())
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    readiness = srv._build_key_readiness()

    assert readiness["has_any_key"] is False
    assert readiness["providers"]["minimax"] == "not_configured"
    assert "api_keys" in readiness["readiness_blockers"]


def test_quality_health_detects_terminal_inconsistency():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Wave
    from across_agents_assistant.task_history.state import TaskState as TS

    task = Task.new(description="inconsistent")
    task.status = TaskStatus.FAILED
    decompose = SubTask(
        task_id=task.task_id,
        subtask_id=f"{task.task_id}-decompose",
        description="decompose",
        agent_id="owner",
        dependencies=[],
    )
    decompose.wave_number = 0
    decompose.status = JobStatus.RUNNING
    task.subtasks.append(decompose)
    task.waves = [Wave(wave_id="wave-0", task_id=task.task_id, wave_number=0, subtasks=[decompose], status=JobStatus.RUNNING)]

    health = _build_quality_health(task, TS(), None, [])

    assert "failed_task_has_nonterminal_subtasks" in health["terminal_inconsistencies"]


def test_update_keys_reports_waiting_tasks_without_legacy_repair(monkeypatch):
    import asyncio
    import across_agents_assistant.api_server as srv

    waiting_task = Task.new(description="waiting for keys")
    waiting_task.status = TaskStatus.PENDING
    waiting_task.last_owner_decision = {"blocked_reason": "waiting_for_keys"}

    class FakeState:
        def get_all_tasks(self):
            return [waiting_task]

    class DummyAgentManager:
        def get_agent_config(self, agent_id):
            return {}
        def update_agent(self, agent_id, config):
            pass

    class DummyStore:
        def save_many(self, values, source):
            return dict(values)

    monkeypatch.setattr(srv, "_task_state", FakeState())
    monkeypatch.setattr(srv, "_keychain_cache", {}, raising=False)
    monkeypatch.setattr(srv, "agent_manager", DummyAgentManager())
    monkeypatch.setattr(srv, "_get_credential_store", lambda: DummyStore())

    response = asyncio.run(srv.update_keys(srv.KeysRequest(deepseek="unit-valid-deepseek-key")))

    assert response["status"] == "ok"
    assert response["repair"] == {
        "task_ids": [waiting_task.task_id],
        "reason": "keys_synced",
        "repaired": [],
        "skipped": "external_orchestrator_only",
    }


def test_check_keys_does_not_initialize_legacy_repair_for_waiting_tasks(monkeypatch):
    import asyncio
    import across_agents_assistant.api_server as srv

    waiting_task = Task.new(description="waiting for keys")
    waiting_task.status = TaskStatus.PENDING
    waiting_task.last_owner_decision = {"blocked_reason": "waiting_for_keys"}

    class FakeState:
        def get_all_tasks(self):
            return [waiting_task]

    class EmptyStore:
        def get(self, provider_id: str):
            return None

    monkeypatch.setattr(srv, "_credential_cache", {"deepseek": "unit-valid-deepseek-key"}, raising=False)
    monkeypatch.setattr(srv, "_get_credential_store", lambda: EmptyStore())
    monkeypatch.setattr(srv, "_task_state", FakeState())
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    repair = srv._repair_active_tasks_waiting_for_keys(reason="keys_checked")
    response = asyncio.run(srv.check_keys())

    assert repair == {
        "task_ids": [waiting_task.task_id],
        "reason": "keys_checked",
        "repaired": [],
        "skipped": "external_orchestrator_only",
    }
    assert any(item.provider_id == "deepseek" and item.status == "configured" for item in response.results)


def test_check_keys_does_not_initialize_orchestrator_without_active_waiting_tasks(monkeypatch):
    import asyncio
    import across_agents_assistant.api_server as srv

    class FakeState:
        def get_all_tasks(self):
            return []

    class EmptyStore:
        def get(self, provider_id: str):
            return None

    monkeypatch.setattr(srv, "_credential_cache", {"deepseek": "unit-valid-deepseek-key"}, raising=False)
    monkeypatch.setattr(srv, "_get_credential_store", lambda: EmptyStore())
    monkeypatch.setattr(srv, "_task_state", FakeState())
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    response = asyncio.run(srv.check_keys())

    assert any(item.provider_id == "deepseek" and item.status == "configured" for item in response.results)


def test_quality_health_waiting_for_keys_gate():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.state import TaskState as TS

    task = Task.new(description="waiting")
    task.status = TaskStatus.PENDING
    task.last_owner_decision = {
        "blocked_reason": "waiting_for_keys",
        "recoverable": True,
        "next_repair_action": "keys_synced",
    }

    health = _build_quality_health(task, TS(), {"deliverables": []}, [])

    assert health["readiness_blockers"] == ["api_keys"]
    assert health["quality_gate"] == "waiting"
    assert health["next_repair_action"] == "keys_synced"


def test_quality_health_missing_manifest_gate():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.state import TaskState as TS

    task = Task.new(description="missing manifest")
    task.status = TaskStatus.FAILED

    manifest = {
        "deliverables": [
            {"path_hint": "main.py", "status": "accepted", "required": True},
            {"path_hint": "README.md", "status": "missing", "required": True},
        ]
    }

    health = _build_quality_health(task, TS(), manifest, [])

    assert health["quality_gate"] == "failed"
    assert health["next_repair_action"] == "quality_remediation"


def test_quality_health_manifest_partial_gate():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    task = Task.new(description="partial")
    task.status = TaskStatus.RUNNING
    manifest = {
        "deliverables": [
            {"path_hint": "main.py", "status": "produced", "required": True},
            {"path_hint": "README.md", "status": "assigned", "required": True},
        ]
    }

    health = _build_quality_health(task, TaskState(), manifest, [])

    assert health["manifest_total"] == 2
    assert health["manifest_produced"] == 1
    assert health["quality_gate"] == "partial"
    assert health["next_repair_action"] is None


def test_quality_health_manifest_passed_gate():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    task = Task.new(description="passed")
    task.status = TaskStatus.COMPLETED
    manifest = {
        "deliverables": [
            {"path_hint": "main.py", "status": "accepted", "required": True},
            {"path_hint": "README.md", "status": "accepted", "required": True},
        ]
    }

    health = _build_quality_health(task, TaskState(), manifest, [])

    assert health["manifest_total"] == 2
    assert health["manifest_accepted"] == 2
    assert health["quality_gate"] == "passed"
    assert health["next_repair_action"] is None


def test_quality_health_active_quality_remediation_next_action():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import JobStatus, SubTask, Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    task = Task.new("quality remediation")
    task.status = TaskStatus.RUNNING
    st = SubTask(task_id=task.task_id, subtask_id="st-quality-1234", description="fix readme", agent_id="openclaw")
    st.status = JobStatus.RUNNING
    task.subtasks.append(st)

    health = _build_quality_health(task, TaskState(), {"deliverables": [{"path_hint": "README.md", "status": "missing", "required": True}]}, [])

    assert health["active_quality_remediation"] == ["st-quality-1234"]
    assert health["next_repair_action"] == "await_quality_remediation"


def test_compute_task_status_waiting_for_keys_is_pending_even_with_error():
    from across_agents_assistant.api_server import _compute_task_status
    from across_agents_assistant.task_history.models import JobStatus, SubTask, Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    state = TaskState()
    task = Task.new(description="waiting")
    task.status = TaskStatus.PENDING
    task.error = "Waiting for API keys to sync before resuming decomposition."
    task.last_owner_decision = {
        "blocked_reason": "waiting_for_keys",
        "recoverable": True,
        "next_repair_action": "keys_synced",
    }
    decompose = SubTask(
        task_id=task.task_id,
        subtask_id=f"{task.task_id}-decompose",
        description="decompose",
        agent_id="owner",
        dependencies=[],
    )
    decompose.status = JobStatus.PENDING
    decompose.wave_number = 0
    task.subtasks.append(decompose)
    state._tasks[task.task_id] = task

    assert _compute_task_status(task, state) == "pending"


def test_compute_task_status_non_recoverable_error_still_failed():
    from across_agents_assistant.api_server import _compute_task_status
    from across_agents_assistant.task_history.models import JobStatus, SubTask, Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    state = TaskState()
    task = Task.new(description="broken")
    task.status = TaskStatus.PENDING
    task.error = "Decomposition failed for non-key reason."
    decompose = SubTask(
        task_id=task.task_id,
        subtask_id=f"{task.task_id}-decompose",
        description="decompose",
        agent_id="owner",
        dependencies=[],
    )
    decompose.status = JobStatus.PENDING
    decompose.wave_number = 0
    task.subtasks.append(decompose)
    state._tasks[task.task_id] = task

    assert _compute_task_status(task, state) == "failed"


def test_quality_health_waiting_for_keys_matches_computed_status():
    from across_agents_assistant.api_server import _build_quality_health, _compute_task_status
    from across_agents_assistant.task_history.models import JobStatus, SubTask, Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    state = TaskState()
    task = Task.new(description="waiting")
    task.status = TaskStatus.PENDING
    task.error = "Waiting for API keys to sync before resuming decomposition."
    task.last_owner_decision = {
        "blocked_reason": "waiting_for_keys",
        "recoverable": True,
        "next_repair_action": "keys_synced",
    }
    decompose = SubTask(
        task_id=task.task_id,
        subtask_id=f"{task.task_id}-decompose",
        description="decompose",
        agent_id="owner",
        dependencies=[],
    )
    decompose.status = JobStatus.PENDING
    decompose.wave_number = 0
    task.subtasks.append(decompose)
    state._tasks[task.task_id] = task

    status = _compute_task_status(task, state)
    health = _build_quality_health(task, state, {"deliverables": []}, [])

    assert status == "pending"
    assert health["quality_gate"] == "waiting"
    assert health["readiness_blockers"] == ["api_keys"]


def test_has_inconsistent_acceptance_judge_passed_with_failed_checks():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    state = TaskState()
    task = Task.new(description="test")
    task.status = TaskStatus.RUNNING
    state._tasks[task.task_id] = task

    records = [
        {
            "level": "subtask",
            "task_id": task.task_id,
            "subtask_id": "st-1",
            "decision": "approve",
            "judge_passed": True,
            "recommended_action": "approve",
            "failed_checks": ["missing_contract_deliverable"],
        }
    ]

    health = _build_quality_health(task, state, {"deliverables": []}, records)
    assert health["has_inconsistent_acceptance"] is True


def test_has_inconsistent_acceptance_approve_with_failed_checks():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    state = TaskState()
    task = Task.new(description="test")
    task.status = TaskStatus.RUNNING
    state._tasks[task.task_id] = task

    records = [
        {
            "level": "subtask",
            "task_id": task.task_id,
            "subtask_id": "st-1",
            "decision": "approve",
            "judge_passed": True,
            "recommended_action": "approve",
            "failed_checks": ["some_error"],
        }
    ]

    health = _build_quality_health(task, state, {"deliverables": []}, records)
    assert health["has_inconsistent_acceptance"] is True


def test_has_inconsistent_acceptance_fix_with_approve_recommended():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    state = TaskState()
    task = Task.new(description="test")
    task.status = TaskStatus.RUNNING
    state._tasks[task.task_id] = task

    records = [
        {
            "level": "subtask",
            "task_id": task.task_id,
            "subtask_id": "st-1",
            "decision": "fix",
            "judge_passed": False,
            "recommended_action": "approve",
            "failed_checks": [],
        }
    ]

    health = _build_quality_health(task, state, {"deliverables": []}, records)
    assert health["has_inconsistent_acceptance"] is True


def test_has_inconsistent_acceptance_consistent_record():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    state = TaskState()
    task = Task.new(description="test")
    task.status = TaskStatus.RUNNING
    state._tasks[task.task_id] = task

    records = [
        {
            "level": "subtask",
            "task_id": task.task_id,
            "subtask_id": "st-1",
            "decision": "fix",
            "judge_passed": False,
            "recommended_action": "fix",
            "failed_checks": ["missing_contract_deliverable"],
        }
    ]

    health = _build_quality_health(task, state, {"deliverables": []}, records)
    assert health["has_inconsistent_acceptance"] is False


def test_has_inconsistent_acceptance_false_for_normalized_wave_fix_record():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Task, TaskStatus
    from across_agents_assistant.task_history.state import TaskState

    state = TaskState()
    task = Task.new(description="wave acceptance normalized")
    task.status = TaskStatus.RUNNING
    state._tasks[task.task_id] = task

    records = [
        {
            "level": "wave",
            "task_id": task.task_id,
            "wave_number": 1,
            "decision": "fix",
            "judge_passed": False,
            "recommended_action": "wave_fix",
            "failed_checks": [],
        }
    ]

    health = _build_quality_health(task, state, {"deliverables": []}, records)
    assert health["has_inconsistent_acceptance"] is False
    assert "delivery_quality" in health
    assert "orchestration_health" in health


def test_quality_health_separates_delivery_quality_from_orchestration_health():
    from across_agents_assistant.api_server import _derive_delivery_and_orchestration_health

    result = _derive_delivery_and_orchestration_health(
        task_status="completed",
        delivery_quality_report={"delivery_quality": "passed"},
        terminal_inconsistencies=["terminal_task_has_nonterminal_subtasks"],
    )

    assert result["delivery_quality"] == "passed"
    assert result["orchestration_health"] == "inconsistent"
    assert result["quality_gate"] == "passed"


def test_running_task_with_active_remediation_reports_recovering_health():
    from across_agents_assistant.api_server import _build_quality_health

    state = TaskState()
    task = state.create_task("running fix")
    task.status = TaskStatus.RUNNING
    original = SubTask(subtask_id="st-cli", description="CLI", agent_id="openclaw")
    original.status = JobStatus.FAILED
    fix = SubTask(subtask_id="st-cli-fix-1", description="Fix CLI", agent_id="deepseek")
    fix.status = JobStatus.RUNNING
    task.subtasks.extend([original, fix])

    health = _build_quality_health(task, state, {"deliverables": []}, [])

    assert health["active_remediation_subtasks"] == ["st-cli-fix-1"]
    assert health["orchestration_health"] == "recovering"
    assert health["next_repair_action"] == "await_remediation"


def test_quality_health_treats_historical_failed_remediation_as_residue_when_delivery_passed():
    from across_agents_assistant.api_server import _build_quality_health

    state = TaskState()
    task = state.create_task("delivery passed after failed fix rounds")
    task.status = TaskStatus.COMPLETED
    task.last_owner_decision = {"delivery_quality": {"delivery_quality": "passed"}}

    original = SubTask(subtask_id="st-docs", description="README", agent_id="minimax")
    original.status = JobStatus.FAILED
    retry = SubTask(subtask_id="st-docs-v2", description="Retry README", agent_id="claude")
    retry.status = JobStatus.FAILED
    task.subtasks.extend([original, retry])

    health = _build_quality_health(
        task,
        state,
        {"deliverables": [{"path_hint": "README.md", "required": True, "status": "produced"}]},
        [],
    )

    assert "terminal_task_has_failed_remediation" not in health["terminal_inconsistencies"]
    assert health["remediation_residue"] == ["st-docs-v2"]
    assert health["delivery_quality"] == "passed"
    assert health["orchestration_health"] == "healthy"


def test_quality_health_derives_delivery_quality_from_odc_when_owner_decision_missing(tmp_path):
    from across_agents_assistant.api_server import _build_quality_health

    class StateWithContract(TaskState):
        def get_delivery_contract(self, task_id):
            return {
                "contract_id": "delivery-contract-api-fallback",
                "task_id": task_id,
                "task_types": ["artifact"],
                "delivery_mode": "artifact",
                "project_dir": str(tmp_path),
                "capabilities": [],
                "deliverables": [{"path_hint": "README.md", "artifact_type": "documentation", "required": True}],
                "constraints": [],
                "acceptance_probes": [],
            }

    (tmp_path / "README.md").write_text("# Done\n", encoding="utf-8")
    state = StateWithContract()
    task = state.create_task("Build README.md", project_dir=str(tmp_path), task_types=["artifact"])
    task.status = TaskStatus.COMPLETED

    health = _build_quality_health(
        task,
        state,
        {"deliverables": [{"path_hint": "README.md", "required": True, "status": "produced"}]},
        [],
    )

    assert health["delivery_quality"] == "passed"
    assert health["quality_gate"] == "passed"
    assert health["orchestration_health"] == "healthy"


def test_quality_health_recomputes_stale_failed_delivery_quality_for_terminal_task(tmp_path):
    from across_agents_assistant.api_server import _build_quality_health

    class StateWithContract(TaskState):
        def get_delivery_contract(self, task_id):
            return {
                "contract_id": "delivery-contract-stale-failed",
                "task_id": task_id,
                "task_types": ["artifact"],
                "delivery_mode": "artifact",
                "project_dir": str(tmp_path),
                "capabilities": [],
                "deliverables": [{"path_hint": "README.md", "artifact_type": "documentation", "required": True}],
                "constraints": [],
                "acceptance_probes": [],
            }

    (tmp_path / "README.md").write_text("# Done\n", encoding="utf-8")
    state = StateWithContract()
    task = state.create_task("stale failed delivery quality", project_dir=str(tmp_path), task_types=["artifact"])
    task.status = TaskStatus.FAILED
    task.last_owner_decision = {"delivery_quality": {"delivery_quality": "failed", "missing_required": ["README.md"]}}

    health = _build_quality_health(
        task,
        state,
        {"deliverables": [{"path_hint": "README.md", "required": True, "status": "produced"}]},
        [],
        effective_task_status="failed",
    )

    assert health["delivery_quality"] == "passed"
    assert health["quality_gate"] == "passed"


def test_quality_health_uses_effective_terminal_status_for_odc_acceptance(tmp_path):
    from across_agents_assistant.api_server import _build_quality_health

    class StateWithContract(TaskState):
        def get_delivery_contract(self, task_id):
            return {
                "contract_id": "delivery-contract-runtime-terminal",
                "task_id": task_id,
                "task_types": ["artifact"],
                "delivery_mode": "artifact",
                "project_dir": str(tmp_path),
                "capabilities": [],
                "deliverables": [{"path_hint": "README.md", "artifact_type": "documentation", "required": True}],
                "constraints": [
                    {
                        "id": "constraint-forbidden-init",
                        "constraint_type": "forbidden_file",
                        "value": "__init__.py",
                        "required": True,
                    }
                ],
                "acceptance_probes": [],
            }

    (tmp_path / "README.md").write_text("# Done\n", encoding="utf-8")
    (tmp_path / "__init__.py").write_text("# forbidden\n", encoding="utf-8")
    state = StateWithContract()
    task = state.create_task("Build README.md", project_dir=str(tmp_path), task_types=["artifact"])
    task.status = TaskStatus.RUNNING

    health = _build_quality_health(
        task,
        state,
        {"deliverables": [{"path_hint": "README.md", "required": True, "status": "produced"}]},
        [],
        effective_task_status="failed",
    )

    assert health["delivery_quality"] == "failed"
    assert health["quality_gate"] == "failed"
    assert health["delivery_quality_report"]["failed_constraints"][0]["value"] == "__init__.py"


def test_quality_health_uses_effective_terminal_status_for_orchestration_residue(tmp_path):
    from across_agents_assistant.api_server import _build_quality_health

    class StateWithContract(TaskState):
        def get_delivery_contract(self, task_id):
            return {
                "contract_id": "delivery-contract-runtime-orchestration",
                "task_id": task_id,
                "task_types": ["artifact"],
                "delivery_mode": "artifact",
                "project_dir": str(tmp_path),
                "capabilities": [],
                "deliverables": [{"path_hint": "README.md", "artifact_type": "documentation", "required": True}],
                "constraints": [],
                "acceptance_probes": [],
            }

    (tmp_path / "README.md").write_text("# Done\n", encoding="utf-8")
    state = StateWithContract()
    task = state.create_task("Build README.md", project_dir=str(tmp_path), task_types=["artifact"])
    task.status = TaskStatus.RUNNING
    original = SubTask(subtask_id="st-docs", description="README", agent_id="minimax")
    original.status = JobStatus.FAILED
    retry = SubTask(subtask_id="st-docs-v2", description="Retry README", agent_id="claude")
    retry.status = JobStatus.RUNNING
    task.subtasks.extend([original, retry])

    health = _build_quality_health(
        task,
        state,
        {"deliverables": [{"path_hint": "README.md", "required": True, "status": "produced"}]},
        [],
        effective_task_status="failed",
    )

    assert health["delivery_quality"] == "passed"
    assert "st-docs-v2" in health["active_remediation_subtasks"]
    assert "failed_task_has_nonterminal_subtasks" in health["terminal_inconsistencies"]
    assert health["orchestration_health"] == "inconsistent"


def test_delivery_quality_adjusts_failed_status_to_completed_with_failures():
    from across_agents_assistant.api_server import _status_with_delivery_quality

    adjusted = _status_with_delivery_quality(
        "failed",
        {
            "delivery_quality": "passed",
            "orchestration_health": "inconsistent",
            "terminal_inconsistencies": ["terminal_task_has_failed_remediation"],
        },
    )

    assert adjusted == "completed_with_failures"


def test_delivery_quality_keeps_active_remediation_running():
    from across_agents_assistant.api_server import _status_with_delivery_quality

    adjusted = _status_with_delivery_quality(
        "failed",
        {
            "delivery_quality": "passed",
            "orchestration_health": "inconsistent",
            "terminal_inconsistencies": ["terminal_task_has_nonterminal_subtasks"],
            "active_remediation_subtasks": ["st-quality-readme-v2"],
        },
    )

    assert adjusted == "running"


def test_delivery_quality_adjusts_completed_status_to_failed_when_contract_fails():
    from across_agents_assistant.api_server import _status_with_delivery_quality

    adjusted = _status_with_delivery_quality(
        "completed",
        {
            "delivery_quality": "failed",
            "orchestration_health": "healthy",
            "terminal_inconsistencies": [],
        },
    )

    assert adjusted == "failed"


def test_quality_health_marks_terminal_task_with_running_remediation_as_inconsistent():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import SubTask, TaskStatus

    state = TaskState()
    task = state.create_task("terminal but retry running")
    task.status = TaskStatus.COMPLETED_WITH_FAILURES
    task.last_owner_decision = {"delivery_quality": {"delivery_quality": "passed"}}
    original = SubTask(subtask_id="st-docs", description="README", agent_id="minimax")
    original.status = JobStatus.FAILED
    retry = SubTask(subtask_id="st-docs-v2", description="Retry README", agent_id="claude")
    retry.status = JobStatus.RUNNING
    task.subtasks.extend([original, retry])

    health = _build_quality_health(
        task,
        state,
        {"deliverables": [{"path_hint": "README.md", "required": True, "status": "produced"}]},
        [],
    )

    assert "terminal_task_has_nonterminal_subtasks" in health["terminal_inconsistencies"]
    assert "st-docs-v2" in health["active_remediation_subtasks"]
    assert health["delivery_quality"] == "passed"
    assert health["orchestration_health"] == "inconsistent"


def test_quality_health_treats_failed_business_subtask_as_residue_when_delivery_passed():
    from across_agents_assistant.api_server import _build_quality_health
    from across_agents_assistant.task_history.models import Wave, SubTask, TaskStatus

    state = TaskState()
    task = state.create_task("terminal but wave failed")
    task.status = TaskStatus.COMPLETED_WITH_FAILURES
    task.last_owner_decision = {"delivery_quality": {"delivery_quality": "passed"}}
    st = SubTask(subtask_id="st-readme", description="README", agent_id="claude")
    st.status = JobStatus.FAILED
    st.wave_number = 1
    task.subtasks.append(st)
    task.waves = [Wave(wave_id="wave-1", task_id=task.task_id, wave_number=1, subtasks=[st], status=JobStatus.FAILED)]

    health = _build_quality_health(
        task,
        state,
        {"deliverables": [{"path_hint": "README.md", "required": True, "status": "produced"}]},
        [],
    )

    assert "terminal_task_has_failed_business_subtasks" not in health["terminal_inconsistencies"]
    assert health["orchestration_health"] == "healthy"


def test_completion_metrics_use_passed_delivery_quality_as_completion_truth():
    from across_agents_assistant.api_server import _completion_metrics_with_quality

    progress, completed_count, total_count = _completion_metrics_with_quality(
        "completed",
        {
            "delivery_quality": "passed",
            "quality_gate": "passed",
            "delivery_quality_report": {"produced_required": ["index.html", "app.js"]},
        },
        completed_count=1,
        total_count=5,
        progress=0.2,
    )

    assert progress == 1.0
    assert completed_count == 5
    assert total_count == 5


def test_completion_metrics_leave_non_passed_tasks_unchanged():
    from across_agents_assistant.api_server import _completion_metrics_with_quality

    progress, completed_count, total_count = _completion_metrics_with_quality(
        "completed_with_failures",
        {"delivery_quality": "partial", "quality_gate": "partial"},
        completed_count=1,
        total_count=5,
        progress=0.2,
    )

    assert progress == 0.2
    assert completed_count == 1
    assert total_count == 5

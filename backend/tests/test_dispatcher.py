import time
from types import SimpleNamespace

from across_agents_assistant.task_manager.dispatcher import TaskDispatcher
from across_agents_assistant.task_manager.models import JobResult, JobStatus
from across_agents_assistant.task_manager.state import TaskState


def test_dispatch_subtask_marks_parent_subtask_running_before_execution():
    state = TaskState()
    task = state.create_task("Build backend service")
    subtask = state.add_subtask(task.task_id, "Implement FastAPI backend", "deepseek")
    dispatcher = TaskDispatcher(state, local_agent_client=object())
    observed = {}

    def fake_execute(job, current_subtask, agent_id):
        current_task = state.get_task(task.task_id)
        observed["job_status"] = state.get_job(job.job_id).status
        observed["subtask_status"] = next(
            st.status for st in current_task.subtasks if st.subtask_id == current_subtask.subtask_id
        )
        return JobResult(job_id=job.job_id, success=True, output="done")

    dispatcher._get_valid_agents = lambda: ["deepseek"]
    dispatcher._execute_agent_job = fake_execute

    job = dispatcher.dispatch_subtask(subtask)
    assert job is not None

    deadline = time.time() + 2.0
    while time.time() < deadline:
        current_job = state.get_job(job.job_id)
        if current_job and current_job.status == JobStatus.COMPLETED:
            break
        time.sleep(0.01)

    assert observed["job_status"] == JobStatus.RUNNING
    assert observed["subtask_status"] == JobStatus.RUNNING
    assert state.get_job(job.job_id).status == JobStatus.COMPLETED
    assert state.get_task(task.task_id).subtasks[0].status == JobStatus.COMPLETED


def test_quality_remediation_subtasks_use_dedicated_timeout(monkeypatch):
    state = TaskState()
    task = state.create_task("Repair static delivery", project_dir="/tmp/example")
    subtask = state.add_subtask(
        task.task_id,
        "Quality remediation attempt 1: fix browser e2e",
        "hermes",
        subtask_id="st-quality-browser-e2e",
    )
    job = state.create_job(subtask)
    dispatcher = TaskDispatcher(state, local_agent_client=object())
    observed = {}

    def fake_invoke(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(is_success=True, output="fixed", metadata={}, error=None)

    dispatcher._agent_bridge.invoke = fake_invoke
    monkeypatch.setenv("ACROSS_AGENTS_AGENT_TIMEOUT", "600")
    monkeypatch.setenv("ACROSS_AGENTS_REMEDIATION_TIMEOUT", "180")

    result = dispatcher._execute_agent_job(job, subtask, "hermes")

    assert result.success is True
    assert observed["timeout"] == 180.0

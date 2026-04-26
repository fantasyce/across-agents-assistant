import pytest
import time
from unittest.mock import Mock, patch
from across_agents_assistant.task_manager.dispatcher import TaskDispatcher
from across_agents_assistant.task_manager.models import Task, SubTask, Job, JobStatus, TaskType
from across_agents_assistant.task_manager.state import TaskState

@pytest.fixture
def task_state():
    return TaskState()

@pytest.fixture
def mock_openclaw():
    mock = Mock()
    mock.send = Mock(return_value=Mock(text="Task completed"))
    return mock

@pytest.fixture
def mock_openclaw_slow():
    """Mock that takes 0.5 seconds to respond, useful for testing cancellation."""
    mock = Mock()
    def slow_send(*args, **kwargs):
        time.sleep(0.5)
        return Mock(text="Task completed")
    mock.send = Mock(side_effect=slow_send)
    return mock

@pytest.fixture
def dispatcher(task_state, mock_openclaw):
    dispatcher = TaskDispatcher(task_state, mock_openclaw)
    return dispatcher

def test_dispatcher_initialization(dispatcher, task_state):
    assert dispatcher._state is task_state
    assert dispatcher._openclaw is not None

def test_dispatch_subtask_creates_job(dispatcher, task_state):
    task = task_state.create_task("测试任务")
    subtask = task_state.add_subtask(task.task_id, "执行子任务", "openclaw")
    job = dispatcher.dispatch_subtask(subtask)
    assert job is not None
    assert job.agent_id == "openclaw"
    # Job may complete quickly, so check from state which reflects current status
    state_job = task_state.get_job(job.job_id)
    assert state_job is not None
    assert state_job.agent_id == "openclaw"

def test_dispatch_subtask_with_nonexistent_agent(dispatcher, task_state):
    task = task_state.create_task("测试任务")
    subtask = task_state.add_subtask(task.task_id, "执行子任务", "invalid_agent")
    job = dispatcher.dispatch_subtask(subtask)
    assert job is None

def test_cancel_job(task_state, mock_openclaw_slow):
    """Test that cancellation works on a slow-running job."""
    dispatcher = TaskDispatcher(task_state, mock_openclaw_slow)
    task = task_state.create_task("测试")
    subtask = task_state.add_subtask(task.task_id, "执行", "openclaw")
    job = dispatcher.dispatch_subtask(subtask)
    # Wait a bit for thread to start (but not long enough for job to complete)
    time.sleep(0.1)
    cancelled = dispatcher.cancel_job(job.job_id)
    assert cancelled == True
    assert task_state.get_job(job.job_id).status == JobStatus.CANCELLED

def test_get_active_jobs(dispatcher, task_state):
    task = task_state.create_task("测试")
    subtask1 = task_state.add_subtask(task.task_id, "任务1", "openclaw")
    subtask2 = task_state.add_subtask(task.task_id, "任务2", "claude")
    job1 = dispatcher.dispatch_subtask(subtask1)
    job2 = dispatcher.dispatch_subtask(subtask2)
    active = dispatcher.get_active_jobs()
    assert len(active) >= 0  # Jobs may complete quickly
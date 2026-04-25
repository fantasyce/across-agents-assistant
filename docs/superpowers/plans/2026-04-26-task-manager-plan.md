# Task Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Task Manager module that enables the App to create, decompose, dispatch, and track tasks assigned to specialized Agents.

**Architecture:** Task Manager uses LLM Gateway (built in Phase 0) to decompose user requests into sub-tasks, then dispatches them to Agents via the Agent Bridge. It maintains an in-memory task state with progress tracking and integrates with the App's async loop.

**Tech Stack:** Python 3.10+, dataclasses, asyncio, threading, existing llm_gateway, FastAPI

---

## File Structure

```
backend/src/across_agents_assistant/task_manager/
├── __init__.py                  # Module exports
├── models.py                    # Task, SubTask, Job, JobStatus dataclasses
├── state.py                     # In-memory task state management
├── task_decomposer.py           # LLM-powered task decomposition
├── dispatcher.py                # Agent dispatch logic (sync with agent_manager)
├── progress.py                   # Progress tracking and integration
└── api.py                       # FastAPI endpoints for task operations

backend/src/across_agents_assistant/
├── app.py                       # MODIFY: integrate TaskManager
├── api_server.py                # MODIFY: add task endpoints

backend/tests/task_manager/
├── __init__.py
├── test_models.py
├── test_task_decomposer.py
├── test_dispatcher.py
└── test_state.py
```

---

## Design Decisions

**Task vs SubTask vs Job:**
- `Task` = top-level user request (e.g., "帮我重构这个项目")
- `SubTask` = decomposed piece assigned to a specific agent
- `Job` = a running execution of a SubTask (with progress, logs, result)

**No persistence in Phase 1:** Tasks live in memory only. Phase 2 will add persistence.

**Synchronous dispatch:** Agent dispatch uses threading + queue, not async directly, to integrate with existing agent_manager patterns.

**LLM Decomposition Prompt:** Structured JSON output with task type, subtasks (with agent assignments), and whether App can handle directly.

---

## TASK 1: Create Task Manager Module Structure and Data Models

**Files:**
- Create: `backend/src/across_agents_assistant/task_manager/__init__.py`
- Create: `backend/src/across_agents_assistant/task_manager/models.py`
- Create: `backend/tests/task_manager/__init__.py`
- Create: `backend/tests/task_manager/test_models.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend/src/across_agents_assistant/task_manager
mkdir -p /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend/tests/task_manager
touch /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend/src/across_agents_assistant/task_manager/__init__.py
touch /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend/tests/task_manager/__init__.py
```

- [ ] **Step 2: Write failing test for models**

```python
# backend/tests/task_manager/test_models.py
import pytest
from dataclasses import dataclass
from across_agents_assistant.task_manager.models import (
    JobStatus, TaskType, SubTask, Task, Job, JobResult
)

def test_job_status_enum():
    assert JobStatus.PENDING.value == "pending"
    assert JobStatus.RUNNING.value == "running"
    assert JobStatus.COMPLETED.value == "completed"
    assert JobStatus.FAILED.value == "failed"

def test_task_type_enum():
    assert TaskType.RESEARCH.value == "research"
    assert TaskType.CODE_REVIEW.value == "code_review"
    assert TaskType.AUTOMATION.value == "automation"
    assert TaskType.SIMPLE_QA.value == "simple_qa"

def test_subtask_creation():
    st = SubTask(
        subtask_id="st-1",
        description="分析代码结构",
        agent_id="claude",
        priority=1
    )
    assert st.subtask_id == "st-1"
    assert st.agent_id == "claude"
    assert st.status == JobStatus.PENDING

def test_task_creation():
    task = Task(
        task_id="task-1",
        description="帮我重构这个项目",
        task_type=TaskType.CODE_REVIEW
    )
    assert task.task_id == "task-1"
    assert len(task.subtasks) == 0
    assert task.can_handle_directly == False

def test_job_creation():
    job = Job(
        job_id="job-1",
        subtask_id="st-1",
        agent_id="claude",
        task_description="分析代码结构"
    )
    assert job.job_id == "job-1"
    assert job.status == JobStatus.PENDING
    assert job.progress == 0.0

def test_job_result():
    result = JobResult(
        job_id="job-1",
        success=True,
        output="分析完成：项目结构良好"
    )
    assert result.success == True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -m pytest tests/task_manager/test_models.py -v 2>&1 | head -20`
Expected: FAIL - module not found

- [ ] **Step 4: Write models.py implementation**

```python
# backend/src/across_agents_assistant/task_manager/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
import uuid
import time

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(str, Enum):
    RESEARCH = "research"
    CODE_REVIEW = "code_review"
    AUTOMATION = "automation"
    SIMPLE_QA = "simple_qa"
    UNKNOWN = "unknown"

@dataclass
class SubTask:
    subtask_id: str
    description: str
    agent_id: str  # openclaw, hermes, claude
    priority: int = 1
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    dependencies: List[str] = field(default_factory=list)  # subtask_ids this depends on

@dataclass
class Task:
    task_id: str
    description: str
    task_type: TaskType = TaskType.UNKNOWN
    subtasks: List[SubTask] = field(default_factory=list)
    can_handle_directly: bool = False
    direct_response: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @staticmethod
    def new(description: str, task_type: TaskType = TaskType.UNKNOWN) -> Task:
        return Task(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            description=description,
            task_type=task_type
        )

@dataclass
class Job:
    job_id: str
    subtask_id: str
    agent_id: str
    task_description: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    logs: List[str] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @staticmethod
    def new(subtask: SubTask, agent_id: str) -> Job:
        return Job(
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            subtask_id=subtask.subtask_id,
            agent_id=agent_id,
            task_description=subtask.description
        )

@dataclass
class JobResult:
    job_id: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration_sec: Optional[float] = None

@dataclass
class ProgressUpdate:
    job_id: str
    status: JobStatus
    progress: float
    log: Optional[str] = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -m pytest tests/task_manager/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager
git add backend/src/across_agents_assistant/task_manager/__init__.py backend/src/across_agents_assistant/task_manager/models.py backend/tests/task_manager/__init__.py backend/tests/task_manager/test_models.py
git commit -m "feat(task_manager): create module structure and data models"
```

---

## TASK 2: Implement Task State Management

**Files:**
- Create: `backend/src/across_agents_assistant/task_manager/state.py`
- Create: `backend/tests/task_manager/test_state.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/task_manager/test_state.py
import pytest
from across_agents_assistant.task_manager.state import TaskState
from across_agents_assistant.task_manager.models import Task, SubTask, Job, JobStatus, TaskType

def test_task_state_initialization():
    state = TaskState()
    assert len(state.get_all_tasks()) == 0
    assert len(state.get_all_jobs()) == 0

def test_create_task():
    state = TaskState()
    task = state.create_task("帮我重构这个项目")
    assert task.task_id.startswith("task-")
    assert task.description == "帮我重构这个项目"

def test_add_subtask():
    state = TaskState()
    task = state.create_task("分析项目")
    subtask = state.add_subtask(task.task_id, "分析代码结构", "claude", priority=1)
    assert subtask.subtask_id.startswith("st-")
    assert subtask.agent_id == "claude"

def test_get_task():
    state = TaskState()
    task = state.create_task("测试任务")
    found = state.get_task(task.task_id)
    assert found is not None
    assert found.task_id == task.task_id

def test_get_nonexistent_task():
    state = TaskState()
    found = state.get_task("nonexistent")
    assert found is None

def test_create_job():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行任务", "openclaw")
    job = state.create_job(subtask)
    assert job.job_id.startswith("job-")
    assert job.status == JobStatus.PENDING

def test_update_job_progress():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行任务", "openclaw")
    job = state.create_job(subtask)
    updated = state.update_job_progress(job.job_id, progress=0.5, log="正在进行中...")
    assert updated is not None
    assert updated.progress == 0.5

def test_complete_job():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行任务", "openclaw")
    job = state.create_job(subtask)
    state.update_job_status(job.job_id, JobStatus.RUNNING)
    result = state.complete_job(job.job_id, success=True, output="完成")
    assert result.success == True
    assert state.get_job(job.job_id).status == JobStatus.COMPLETED

def test_get_task_progress():
    state = TaskState()
    task = state.create_task("测试")
    state.add_subtask(task.task_id, "子任务1", "openclaw")
    state.add_subtask(task.task_id, "子任务2", "claude")
    progress = state.get_task_progress(task.task_id)
    assert progress == 0.0  # All pending

def test_cancel_task():
    state = TaskState()
    task = state.create_task("测试")
    subtask = state.add_subtask(task.task_id, "执行", "openclaw")
    job = state.create_job(subtask)
    cancelled = state.cancel_task(task.task_id)
    assert cancelled == True
    assert state.get_job(job.job_id).status == JobStatus.CANCELLED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -m pytest tests/task_manager/test_state.py -v 2>&1 | head -20`
Expected: FAIL - module not found

- [ ] **Step 3: Write state.py implementation**

```python
# backend/src/across_agents_assistant/task_manager/state.py
import threading
import time
import uuid
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .models import Task, SubTask, Job, JobResult, JobStatus, TaskType, ProgressUpdate

@dataclass
class TaskState:
    """
    Thread-safe in-memory task state management.

    All access is protected by a reentrant lock to support
    nested calls from the same thread.
    """
    _tasks: Dict[str, Task] = field(default_factory=dict)
    _jobs: Dict[str, Job] = field(default_factory=dict)
    _subtask_to_job: Dict[str, str] = field(default_factory=dict)  # subtask_id -> job_id
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def create_task(self, description: str, task_type: TaskType = TaskType.UNKNOWN) -> Task:
        with self._lock:
            task = Task.new(description=description, task_type=task_type)
            self._tasks[task.task_id] = task
            return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[Task]:
        with self._lock:
            return list(self._tasks.values())

    def add_subtask(self, task_id: str, description: str, agent_id: str, priority: int = 1, dependencies: List[str] = None) -> Optional[SubTask]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            subtask = SubTask(
                subtask_id=f"st-{uuid.uuid4().hex[:8]}",
                description=description,
                agent_id=agent_id,
                priority=priority,
                dependencies=dependencies or []
            )
            task.subtasks.append(subtask)
            task.updated_at = time.time()
            return subtask

    def update_subtask_status(self, task_id: str, subtask_id: str, status: JobStatus) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            for st in task.subtasks:
                if st.subtask_id == subtask_id:
                    st.status = status
                    task.updated_at = time.time()
                    return True
            return False

    def get_task_progress(self, task_id: str) -> float:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or not task.subtasks:
                return 0.0
            total = len(task.subtasks)
            completed = sum(1 for st in task.subtasks if st.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED))
            return completed / total

    def create_job(self, subtask: SubTask) -> Job:
        with self._lock:
            job = Job.new(subtask=subtask, agent_id=subtask.agent_id)
            self._jobs[job.job_id] = job
            self._subtask_to_job[subtask.subtask_id] = job.job_id
            return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def get_job_by_subtask(self, subtask_id: str) -> Optional[Job]:
        with self._lock:
            job_id = self._subtask_to_job.get(subtask_id)
            if job_id:
                return self._jobs.get(job_id)
            return None

    def get_all_jobs(self) -> List[Job]:
        with self._lock:
            return list(self._jobs.values())

    def update_job_progress(self, job_id: str, progress: float, log: Optional[str] = None) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.progress = min(1.0, max(0.0, progress))
            if log:
                job.logs.append(log)
            if job.status == JobStatus.PENDING and progress > 0:
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
            return job

    def update_job_status(self, job_id: str, status: JobStatus) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.status = status
            if status == JobStatus.RUNNING and job.started_at is None:
                job.started_at = time.time()
            return job

    def complete_job(self, job_id: str, success: bool, output: Optional[str] = None, error: Optional[str] = None) -> Optional[JobResult]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.status = JobStatus.COMPLETED if success else JobStatus.FAILED
            job.completed_at = time.time()
            job.result = output
            job.error = error
            job.progress = 1.0 if success else job.progress

            # Update subtask status
            for task in self._tasks.values():
                for st in task.subtasks:
                    if st.subtask_id == job.subtask_id:
                        st.status = job.status
                        st.progress = job.progress

            duration = None
            if job.started_at and job.completed_at:
                duration = job.completed_at - job.started_at

            return JobResult(
                job_id=job_id,
                success=success,
                output=output,
                error=error,
                duration_sec=duration
            )

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            for st in task.subtasks:
                st.status = JobStatus.CANCELLED
                job_id = self._subtask_to_job.get(st.subtask_id)
                if job_id:
                    job = self._jobs.get(job_id)
                    if job and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                        job.status = JobStatus.CANCELLED
                        job.completed_at = time.time()
            task.updated_at = time.time()
            return True

    def get_ready_subtasks(self, task_id: str) -> List[SubTask]:
        """Get subtasks that are ready to run (pending and dependencies satisfied)."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return []
            ready = []
            for st in task.subtasks:
                if st.status != JobStatus.PENDING:
                    continue
                # Check dependencies
                deps_satisfied = all(
                    self._get_subtask_status(task_id, dep) in (JobStatus.COMPLETED, JobStatus.CANCELLED)
                    for dep in st.dependencies
                )
                if deps_satisfied:
                    ready.append(st)
            return ready

    def _get_subtask_status(self, task_id: str, subtask_id: str) -> JobStatus:
        task = self._tasks.get(task_id)
        if not task:
            return JobStatus.PENDING
        for st in task.subtasks:
            if st.subtask_id == subtask_id:
                return st.status
        return JobStatus.PENDING
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -m pytest tests/task_manager/test_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager
git add backend/src/across_agents_assistant/task_manager/state.py backend/tests/task_manager/test_state.py
git commit -m "feat(task_manager): implement thread-safe task state management"
```

---

## TASK 3: Implement Task Decomposer (LLM-Powered)

**Files:**
- Create: `backend/src/across_agents_assistant/task_manager/task_decomposer.py`
- Create: `backend/tests/task_manager/test_task_decomposer.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/task_manager/test_task_decomposer.py
import pytest
from unittest.mock import AsyncMock, patch
from across_agents_assistant.task_manager.task_decomposer import TaskDecomposer
from across_agents_assistant.task_manager.models import Task, TaskType
from across_agents_assistant.llm_gateway.base_adapter import LLMResponse

@pytest.fixture
def mock_gateway():
    """Create a mock LLM gateway that returns structured JSON."""
    mock = AsyncMock()
    return mock

def test_decomposer_initialization(mock_gateway):
    decomposer = TaskDecomposer(mock_gateway)
    assert decomposer._gateway is not None
    assert decomposer._default_agents == ["openclaw", "hermes", "claude"]

def test_parse_llm_response_research():
    decomposer = TaskDecomposer(AsyncMock())
    json_str = '''{
        "task_type": "research",
        "can_handle_directly": false,
        "subtasks": [
            {"description": "搜索相关信息", "agent": "openclaw", "priority": 1},
            {"description": "整理搜索结果", "agent": "claude", "priority": 2}
        ]
    }'''
    result = decomposer._parse_llm_response(json_str)
    assert result is not None
    assert result["task_type"] == "research"
    assert len(result["subtasks"]) == 2

def test_parse_llm_response_simple_qa():
    decomposer = TaskDecomposer(AsyncMock())
    json_str = '''{
        "task_type": "simple_qa",
        "can_handle_directly": true,
        "direct_response": "这是直接回答",
        "subtasks": []
    }'''
    result = decomposer._parse_llm_response(json_str)
    assert result is not None
    assert result["can_handle_directly"] == True
    assert result["direct_response"] == "这是直接回答"

def test_parse_invalid_json():
    decomposer = TaskDecomposer(AsyncMock())
    result = decomposer._parse_llm_response("not valid json")
    assert result is None

def test_apply_decomposition_to_task():
    decomposer = TaskDecomposer(AsyncMock())
    task = Task.new("分析这个项目")
    decomposition = {
        "task_type": "code_review",
        "can_handle_directly": False,
        "subtasks": [
            {"description": "分析代码结构", "agent": "claude", "priority": 1},
            {"description": "检查代码规范", "agent": "openclaw", "priority": 2}
        ]
    }
    decomposer._apply_decomposition(task, decomposition)
    assert len(task.subtasks) == 2
    assert task.task_type == TaskType.CODE_REVIEW
    assert task.can_handle_directly == False

def test_validate_agent():
    decomposer = TaskDecomposer(AsyncMock())
    assert decomposer._validate_agent("openclaw") == "openclaw"
    assert decomposer._validate_agent("claude") == "claude"
    assert decomposer._validate_agent("hermes") == "hermes"
    assert decomposer._validate_agent("unknown") == "openclaw"  # Default fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -m pytest tests/task_manager/test_task_decomposer.py -v 2>&1 | head -20`
Expected: FAIL - module not found

- [ ] **Step 3: Write task_decomposer.py implementation**

```python
# backend/src/across_agents_assistant/task_manager/task_decomposer.py
import json
import logging
from typing import Dict, Any, Optional, List

from ..llm_gateway.gateway import LLMGateway
from ..llm_gateway.base_adapter import LLMResponse
from .models import Task, TaskType

logger = logging.getLogger("across_agents_assistant.task_manager")

SYSTEM_PROMPT = """You are a task planning assistant for a macOS assistant app called "Across Agents Assistant".

Your role is to break down user requests into clear, actionable sub-tasks assigned to specialized agents.

**Available Agents:**
- openclaw: General purpose development and automation tasks
- hermes: Specific scenario development and conversational tasks
- claude: Code/technical deep expertise and code reviews

**Task Types:**
- research: Information gathering, web search, knowledge lookup
- code_review: Code analysis, quality assessment, refactoring suggestions
- automation: repetitive tasks, scripting, workflow automation
- simple_qa: Questions the app can answer directly without agent dispatch
- unknown: Cannot determine type

**Output Format:**
You MUST output a JSON object with this exact structure:
{
    "task_type": "research|code_review|automation|simple_qa|unknown",
    "can_handle_directly": true|false,
    "direct_response": "..." (only if can_handle_directly is true),
    "subtasks": [
        {"description": "...", "agent": "openclaw|hermes|claude", "priority": 1, "dependencies": []}
    ]
}

**Rules:**
1. If the task is a simple question or can be answered from context, set can_handle_directly=true
2. Complex tasks should be broken into subtasks assigned to appropriate agents
3. Dependencies indicate which subtask must complete before this one starts (use subtask descriptions to match)
4. Priority 1 = highest, run first
5. Keep descriptions concise but actionable
"""

class TaskDecomposer:
    """Uses LLM to decompose user requests into subtasks."""

    VALID_AGENTS = ["openclaw", "hermes", "claude"]
    TASK_TYPES = ["research", "code_review", "automation", "simple_qa", "unknown"]

    def __init__(self, gateway: LLMGateway):
        self._gateway = gateway
        self._default_agents = self.VALID_AGENTS

    async def decompose(self, task: Task, context: Optional[Dict[str, Any]] = None) -> Task:
        """
        Use LLM to decompose a task into subtasks.

        Args:
            task: The task to decompose
            context: Optional context dict (e.g., frontmost_app, window_title)

        Returns:
            The same task object with subtasks populated
        """
        user_message = task.description

        try:
            response = await self._gateway.chat(
                message=user_message,
                system_prompt=SYSTEM_PROMPT,
                context=context,
                temperature=0.3,  # Lower temp for structured output
                max_tokens=2048
            )

            logger.info(f"LLM decomposition response: {response.text[:200]}...")

            decomposition = self._parse_llm_response(response.text)
            if decomposition:
                self._apply_decomposition(task, decomposition)
                logger.info(f"Task {task.task_id} decomposed into {len(task.subtasks)} subtasks")
            else:
                logger.warning(f"Failed to parse LLM response for task {task.task_id}")
                task.task_type = TaskType.UNKNOWN

        except Exception as e:
            logger.error(f"Task decomposition failed for {task.task_id}: {e}")
            task.task_type = TaskType.UNKNOWN

        return task

    def _parse_llm_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM response text."""
        text = text.strip()

        # Try direct JSON parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code blocks
        import re
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try to find JSON object pattern
        obj_match = re.search(r"\{[\s\S]*\}", text)
        if obj_match:
            try:
                return json.loads(obj_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _apply_decomposition(self, task: Task, decomposition: Dict[str, Any]) -> None:
        """Apply parsed decomposition to task."""
        # Parse task type
        task_type_str = decomposition.get("task_type", "unknown")
        if task_type_str in self.TASK_TYPES:
            task.task_type = TaskType(task_type_str)
        else:
            task.task_type = TaskType.UNKNOWN

        # Parse direct handling
        task.can_handle_directly = decomposition.get("can_handle_directly", False)
        task.direct_response = decomposition.get("direct_response")

        # Parse subtasks
        for st_data in decomposition.get("subtasks", []):
            description = st_data.get("description", "")
            if not description:
                continue

            agent = self._validate_agent(st_data.get("agent"))
            priority = int(st_data.get("priority", 1))
            dependencies = st_data.get("dependencies", [])

            subtask = task.SubTask(
                subtask_id=f"st-",  # Will be set properly in dispatch
                description=description,
                agent_id=agent,
                priority=priority,
                dependencies=dependencies
            )
            task.subtasks.append(subtask)

    def _validate_agent(self, agent: Optional[str]) -> str:
        """Validate and normalize agent ID."""
        if agent and agent in self.VALID_AGENTS:
            return agent
        logger.warning(f"Invalid agent '{agent}', defaulting to 'openclaw'")
        return "openclaw"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -m pytest tests/task_manager/test_task_decomposer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager
git add backend/src/across_agents_assistant/task_manager/task_decomposer.py backend/tests/task_manager/test_task_decomposer.py
git commit -m "feat(task_manager): implement LLM-powered task decomposition"
```

---

## TASK 4: Implement Task Dispatcher

**Files:**
- Create: `backend/src/across_agents_assistant/task_manager/dispatcher.py`
- Create: `backend/tests/task_manager/test_dispatcher.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/task_manager/test_dispatcher.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from across_agents_assistant.task_manager.dispatcher import TaskDispatcher
from across_agents_assistant.task_manager.models import Task, SubTask, Job, JobStatus, TaskType
from across_agents_assistant.task_manager.state import TaskState

@pytest.fixture
def task_state():
    return TaskState()

@pytest.fixture
def dispatcher(task_state):
    mock_openclaw = AsyncMock()
    mock_openclaw.send = AsyncMock(return_value=Mock(text="Task completed"))
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
    assert job.status == JobStatus.PENDING

def test_dispatch_subtask_with_nonexistent_agent(dispatcher, task_state):
    task = task_state.create_task("测试任务")
    subtask = task_state.add_subtask(task.task_id, "执行子任务", "invalid_agent")
    job = dispatcher.dispatch_subtask(subtask)
    assert job is None

def test_execute_job_updates_progress(dispatcher, task_state):
    task = task_state.create_task("测试")
    subtask = task_state.add_subtask(task.task_id, "执行", "openclaw")
    job = dispatcher.dispatch_subtask(subtask)
    assert job.progress == 0.0

def test_get_active_jobs(dispatcher, task_state):
    task = task_state.create_task("测试")
    subtask1 = task_state.add_subtask(task.task_id, "任务1", "openclaw")
    subtask2 = task_state.add_subtask(task.task_id, "任务2", "claude")
    job1 = dispatcher.dispatch_subtask(subtask1)
    job2 = dispatcher.dispatch_subtask(subtask2)
    active = dispatcher.get_active_jobs()
    assert len(active) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -m pytest tests/task_manager/test_dispatcher.py -v 2>&1 | head -20`
Expected: FAIL - module not found

- [ ] **Step 3: Write dispatcher.py implementation**

```python
# backend/src/across_agents_assistant/task_manager/dispatcher.py
import asyncio
import logging
import queue
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
        self._job_queues: Dict[str, queue.Queue] = {}
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
        job = self._state.create_job(subtask)

        def run_job():
            try:
                self._state.update_job_status(job.job_id, JobStatus.RUNNING)
                self._notify_progress(job.job_id, JobStatus.RUNNING, 0.0, "Started")

                # Execute based on agent type
                if subtask.agent_id == "openclaw":
                    result = self._execute_openclaw_job(job, subtask)
                elif subtask.agent_id == "hermes":
                    result = self._execute_hermes_job(job, subtask)
                elif subtask.agent_id == "claude":
                    result = self._execute_claude_job(job, subtask)
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
                    self._job_queues.pop(job.job_id, None)

        thread = threading.Thread(target=run_job, daemon=True)
        with self._lock:
            self._job_threads[job.job_id] = thread
            self._job_queues[job.job_id] = queue.Queue()

        thread.start()
        return job

    def _execute_openclaw_job(self, job: Job, subtask: SubTask) -> JobResult:
        """Execute a job using the openclaw agent."""
        try:
            # Update progress
            self._state.update_job_progress(job.job_id, 0.1, "Connecting to openclaw agent...")
            self._notify_progress(job.job_id, JobStatus.RUNNING, 0.1, "Connecting...")

            # Call the openclaw agent synchronously
            response = self._openclaw.send(
                message=subtask.description,
                session_id=None,
                use_current=True,
                target_agent="openclaw"
            )

            self._state.update_job_progress(job.job_id, 0.9, "Processing response...")
            self._notify_progress(job.job_id, JobStatus.RUNNING, 0.9, "Processing...")

            output = response.text if response and response.text else ""
            return JobResult(job_id=job.job_id, success=True, output=output)

        except Exception as e:
            return JobResult(job_id=job.job_id, success=False, error=str(e))

    def _execute_hermes_job(self, job: Job, subtask: SubTask) -> JobResult:
        """Execute a job using the hermes agent."""
        # Hermes uses the same openclaw client with different agent ID
        try:
            self._state.update_job_progress(job.job_id, 0.1, "Connecting to hermes agent...")
            self._notify_progress(job.job_id, JobStatus.RUNNING, 0.1, "Connecting...")

            response = self._openclaw.send(
                message=subtask.description,
                session_id=None,
                use_current=True,
                target_agent="hermes"
            )

            self._state.update_job_progress(job.job_id, 0.9, "Processing response...")
            output = response.text if response and response.text else ""
            return JobResult(job_id=job.job_id, success=True, output=output)

        except Exception as e:
            return JobResult(job_id=job.job_id, success=False, error=str(e))

    def _execute_claude_job(self, job: Job, subtask: SubTask) -> JobResult:
        """Execute a job using the claude agent."""
        # Claude uses the same openclaw client with different agent ID
        try:
            self._state.update_job_progress(job.job_id, 0.1, "Connecting to claude agent...")
            self._notify_progress(job.job_id, JobStatus.RUNNING, 0.1, "Connecting...")

            response = self._openclaw.send(
                message=subtask.description,
                session_id=None,
                use_current=True,
                target_agent="claude"
            )

            self._state.update_job_progress(job.job_id, 0.9, "Processing response...")
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

        self._state.complete_job(job_id, success=False, error="Cancelled by user")
        self._notify_progress(job_id, JobStatus.CANCELLED, job.progress, "Cancelled")
        return True

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -m pytest tests/task_manager/test_dispatcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager
git add backend/src/across_agents_assistant/task_manager/dispatcher.py backend/tests/task_manager/test_dispatcher.py
git commit -m "feat(task_manager): implement task dispatcher with agent dispatch"
```

---

## TASK 5: Create FastAPI Endpoints for Task Operations

**Files:**
- Modify: `backend/src/across_agents_assistant/api_server.py`
- Test: Existing API tests + manual verification

- [ ] **Step 1: Add Task Manager endpoints to api_server.py**

Add after the LLM Gateway imports at the top of api_server.py:

```python
# Task Manager imports
from .task_manager.state import TaskState
from .task_manager.dispatcher import TaskDispatcher
from .task_manager.task_decomposer import TaskDecomposer
from .task_manager.models import TaskType, JobStatus

# Global Task Manager instances
_task_state = TaskState()
_task_decomposer: Optional[TaskDecomposer] = None

def get_task_decomposer() -> TaskDecomposer:
    global _task_decomposer
    if _task_decomposer is None:
        from .llm_gateway.gateway import get_gateway
        _task_decomposer = TaskDecomposer(get_gateway())
    return _task_decomposer

_task_dispatcher: Optional[TaskDispatcher] = None

def get_task_dispatcher() -> TaskDispatcher:
    global _task_dispatcher
    if _task_dispatcher is None:
        from .openclaw.client import UniversalAgentClient
        from .agent_manager import AgentManager
        agent_manager = AgentManager()
        openclaw_client = UniversalAgentClient(agent_manager)
        _task_dispatcher = TaskDispatcher(_task_state, openclaw_client)
    return _task_dispatcher
```

Add these endpoint classes and routes after the LLM endpoints (before `@app.post("/api/chat/cancel")`):

```python
class TaskCreateRequest(BaseModel):
    description: str
    context: Optional[Dict[str, Any]] = None
    decompose_with_llm: bool = True

class SubTaskInfo(BaseModel):
    subtask_id: str
    description: str
    agent_id: str
    priority: int
    status: str
    progress: float
    dependencies: List[str]

class TaskInfo(BaseModel):
    task_id: str
    description: str
    task_type: str
    subtasks: List[SubTaskInfo]
    can_handle_directly: bool
    direct_response: Optional[str]
    progress: float
    created_at: float
    updated_at: float

class TaskCreateResponse(BaseModel):
    task_id: str
    description: str
    task_type: str
    subtasks: List[SubTaskInfo]
    can_handle_directly: bool
    direct_response: Optional[str]
    progress: float

@app.post("/api/tasks", response_model=TaskCreateResponse)
async def create_task(req: TaskCreateRequest):
    """
    Create a new task, optionally decomposing it with LLM.

    If decompose_with_llm=True, the task will be analyzed and broken into subtasks.
    """
    try:
        task = _task_state.create_task(req.description)

        if req.decompose_with_llm:
            decomposer = get_task_decomposer()
            context = req.context or {}
            await decomposer.decompose(task, context)

        progress = _task_state.get_task_progress(task.task_id)

        return TaskCreateResponse(
            task_id=task.task_id,
            description=task.description,
            task_type=task.task_type.value,
            subtasks=[
                SubTaskInfo(
                    subtask_id=st.subtask_id,
                    description=st.description,
                    agent_id=st.agent_id,
                    priority=st.priority,
                    status=st.status.value,
                    progress=st.progress,
                    dependencies=st.dependencies
                )
                for st in task.subtasks
            ],
            can_handle_directly=task.can_handle_directly,
            direct_response=task.direct_response,
            progress=progress
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TaskDispatchRequest(BaseModel):
    task_id: str
    subtask_ids: Optional[List[str]] = None  # If None, dispatch all ready subtasks

class JobInfo(BaseModel):
    job_id: str
    subtask_id: str
    agent_id: str
    task_description: str
    status: str
    progress: float
    logs: List[str]
    result: Optional[str]
    error: Optional[str]

class TaskDispatchResponse(BaseModel):
    task_id: str
    dispatched_jobs: List[JobInfo]
    ready_remaining: int

@app.post("/api/tasks/{task_id}/dispatch", response_model=TaskDispatchResponse)
async def dispatch_task(task_id: str, req: TaskDispatchRequest):
    """
    Dispatch subtasks to agents.

    If subtask_ids is provided, only those subtasks are dispatched.
    Otherwise, all ready subtasks (dependencies satisfied) are dispatched.
    """
    try:
        task = _task_state.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if req.subtask_ids:
            subtasks_to_dispatch = [st for st in task.subtasks if st.subtask_id in req.subtask_ids]
        else:
            subtasks_to_dispatch = _task_state.get_ready_subtasks(task_id)

        dispatcher = get_task_dispatcher()
        dispatched = []

        for subtask in subtasks_to_dispatch:
            job = dispatcher.dispatch_subtask(subtask)
            if job:
                dispatched.append(JobInfo(
                    job_id=job.job_id,
                    subtask_id=job.subtask_id,
                    agent_id=job.agent_id,
                    task_description=job.task_description,
                    status=job.status.value,
                    progress=job.progress,
                    logs=job.logs,
                    result=job.result,
                    error=job.error
                ))

        remaining = len(_task_state.get_ready_subtasks(task_id))

        return TaskDispatchResponse(
            task_id=task_id,
            dispatched_jobs=dispatched,
            ready_remaining=remaining
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str):
    """Get task details and progress."""
    try:
        task = _task_state.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        progress = _task_state.get_task_progress(task_id)

        return TaskInfo(
            task_id=task.task_id,
            description=task.description,
            task_type=task.task_type.value,
            subtasks=[
                SubTaskInfo(
                    subtask_id=st.subtask_id,
                    description=st.description,
                    agent_id=st.agent_id,
                    priority=st.priority,
                    status=st.status.value,
                    progress=st.progress,
                    dependencies=st.dependencies
                )
                for st in task.subtasks
            ],
            can_handle_directly=task.can_handle_directly,
            direct_response=task.direct_response,
            progress=progress,
            created_at=task.created_at,
            updated_at=task.updated_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks", response_model=List[TaskInfo])
async def list_tasks():
    """List all tasks."""
    try:
        tasks = _task_state.get_all_tasks()
        return [
            TaskInfo(
                task_id=t.task_id,
                description=t.description,
                task_type=t.task_type.value,
                subtasks=[
                    SubTaskInfo(
                        subtask_id=st.subtask_id,
                        description=st.description,
                        agent_id=st.agent_id,
                        priority=st.priority,
                        status=st.status.value,
                        progress=st.progress,
                        dependencies=st.dependencies
                    )
                    for st in t.subtasks
                ],
                can_handle_directly=t.can_handle_directly,
                direct_response=t.direct_response,
                progress=_task_state.get_task_progress(t.task_id),
                created_at=t.created_at,
                updated_at=t.updated_at
            )
            for t in tasks
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/{task_id}/jobs/{job_id}", response_model=JobInfo)
async def get_job(task_id: str, job_id: str):
    """Get job details."""
    try:
        job = _task_state.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return JobInfo(
            job_id=job.job_id,
            subtask_id=job.subtask_id,
            agent_id=job.agent_id,
            task_description=job.task_description,
            status=job.status.value,
            progress=job.progress,
            logs=job.logs,
            result=job.result,
            error=job.error
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class JobCancelRequest(BaseModel):
    job_id: str

@app.post("/api/tasks/{task_id}/jobs/{job_id}/cancel")
async def cancel_job(task_id: str, job_id: str):
    """Cancel a running job."""
    try:
        dispatcher = get_task_dispatcher()
        success = dispatcher.cancel_job(job_id)
        if not success:
            raise HTTPException(status_code=400, detail=f"Cannot cancel job {job_id}")
        return {"status": "success", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 2: Test imports**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -c "from across_agents_assistant.api_server import app, get_task_decomposer, get_task_dispatcher; print('Imports OK')"`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager
git add backend/src/across_agents_assistant/api_server.py
git commit -m "feat(api): add Task Manager REST endpoints"
```

---

## TASK 6: Integrate TaskManager into App Flow

**Files:**
- Modify: `backend/src/across_agents_assistant/app.py`

- [ ] **Step 1: Update app.py imports**

Add to the imports section in app.py (around line 17):

```python
from .task_manager.state import TaskState
from .task_manager.dispatcher import TaskDispatcher
from .task_manager.task_decomposer import TaskDecomposer
```

- [ ] **Step 2: Add TaskManager to App initialization**

In `AcrossAgentsAssistantApp.__init__`, add after the existing initialization (around line 52):

```python
# Task Manager for multi-agent coordination
self._task_state = TaskState()
self._task_dispatcher = TaskDispatcher(self._task_state, self._openclaw)
self._task_decomposer = TaskDecomposer(self._llm_gateway)
```

- [ ] **Step 3: Add task processing method**

Add to the `AcrossAgentsAssistantApp` class (after `_drain_hotkey_event` method):

```python
async def process_task(self, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Process a user task using the Task Manager.

    1. Create task and decompose with LLM
    2. If can_handle_directly, return direct response
    3. Otherwise, dispatch subtasks to agents

    Returns a dict with:
        - task_id: str
        - can_handle_directly: bool
        - direct_response: Optional[str]
        - subtasks: List[subtask info]
        - dispatched_jobs: List[job info]
    """
    task = self._task_state.create_task(description)

    # Decompose with LLM
    await self._task_decomposer.decompose(task, context or {})

    if task.can_handle_directly:
        return {
            "task_id": task.task_id,
            "can_handle_directly": True,
            "direct_response": task.direct_response,
            "subtasks": [],
            "dispatched_jobs": []
        }

    # Dispatch ready subtasks
    ready = self._task_state.get_ready_subtasks(task.task_id)
    dispatched = []
    for st in ready:
        job = self._task_dispatcher.dispatch_subtask(st)
        if job:
            dispatched.append({
                "job_id": job.job_id,
                "subtask_id": job.subtask_id,
                "agent_id": job.agent_id,
                "status": job.status.value
            })

    return {
        "task_id": task.task_id,
        "can_handle_directly": False,
        "direct_response": None,
        "subtasks": [
            {
                "subtask_id": st.subtask_id,
                "description": st.description,
                "agent_id": st.agent_id,
                "priority": st.priority,
                "status": st.status.value
            }
            for st in task.subtasks
        ],
        "dispatched_jobs": dispatched
    }
```

- [ ] **Step 4: Test imports**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -c "from across_agents_assistant.app import AcrossAgentsAssistantApp; print('App imports OK')"`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager
git add backend/src/across_agents_assistant/app.py
git commit -m "feat(app): integrate Task Manager into app flow"
```

---

## TASK 7: Update Tests Directory Structure

**Files:**
- Verify: `backend/tests/task_manager/` structure is complete
- Run: All tests

- [ ] **Step 1: Verify all test files exist**

Run: `ls -la /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend/tests/task_manager/`

Expected output:
```
test_models.py
test_state.py
test_task_decomposer.py
test_dispatcher.py
__init__.py
```

- [ ] **Step 2: Run all Task Manager tests**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager/backend && python3 -m pytest tests/task_manager/ -v`

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager
git add backend/tests/task_manager/
git commit -m "test(task_manager): add comprehensive tests"
```

---

## TASK 8: Update Documentation

**Files:**
- Create: `docs/superpowers/plans/2026-04-26-task-manager-spec.md`

- [ ] **Step 1: Create spec document**

```markdown
# Task Manager Specification

## Overview

Task Manager enables the App to act as a Manager by decomposing user requests into subtasks and dispatching them to specialized Agents (openclaw/hermes/claude).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      TaskManager                            │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │TaskDecomposer│  │TaskState     │  │TaskDispatcher    │  │
│  │(LLM-powered) │──│(in-memory)   │──│(agent dispatch)  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Data Models

### Task
Top-level user request containing multiple subtasks.

### SubTask
A single unit of work assigned to a specific agent.

### Job
A running execution of a subtask with progress tracking.

## API Endpoints

- `POST /api/tasks` - Create and decompose a task
- `GET /api/tasks` - List all tasks
- `GET /api/tasks/{task_id}` - Get task details
- `POST /api/tasks/{task_id}/dispatch` - Dispatch subtasks
- `GET /api/tasks/{task_id}/jobs/{job_id}` - Get job details
- `POST /api/tasks/{task_id}/jobs/{job_id}/cancel` - Cancel a job

## LLM Decomposition

Uses the LLM Gateway to analyze user requests and break them into subtasks:

```
User: 帮我重构这个项目

LLM Response:
{
    "task_type": "code_review",
    "can_handle_directly": false,
    "subtasks": [
        {"description": "分析项目结构", "agent": "claude", "priority": 1},
        {"description": "识别重构点", "agent": "openclaw", "priority": 2},
        {"description": "编写测试用例", "agent": "hermes", "priority": 3}
    ]
}
```

## Agent Assignment

| Agent | Best For |
|-------|----------|
| openclaw | General development and automation |
| hermes | Specific scenarios and conversational tasks |
| claude | Code/technical expertise and reviews |

## Phase 1 Limitations

- Tasks are in-memory only (no persistence)
- Single-threaded job execution per agent
- No result aggregation yet
```

- [ ] **Step 2: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+task-manager
git add docs/superpowers/plans/2026-04-26-task-manager-spec.md
git commit -m "docs: add Task Manager specification"
```

---

## Acceptance Criteria

### Functional Requirements

| ID | Criteria | Verification |
|----|----------|---------------|
| TM1 | Task can be created and stored in state | `POST /api/tasks` returns task |
| TM2 | Task can be decomposed by LLM into subtasks | Task has subtasks with agent assignments |
| TM3 | Subtasks can be dispatched to agents | `POST /api/tasks/{id}/dispatch` creates jobs |
| TM4 | Job progress can be tracked | `GET /api/tasks/{id}/jobs/{job_id}` returns progress |
| TM5 | Jobs can be cancelled | `POST /api/tasks/{id}/jobs/{job_id}/cancel` works |
| TM6 | App.process_task() integrates the flow | Called from app.py without errors |

### Technical Requirements

- [ ] All dataclasses use consistent field naming
- [ ] TaskState is thread-safe (RLock)
- [ ] All tests pass
- [ ] No regression in existing functionality
- [ ] API endpoints are documented

### Success Indicators

1. **Decomposition Quality**: LLM correctly identifies task type and assigns appropriate agents
2. **Progress Tracking**: Real-time progress updates via callbacks
3. **Agent Dispatch**: All three agents (openclaw/hermes/claude) can be targeted
4. **Graceful Degradation**: If LLM fails, task is marked as UNKNOWN type
```

---

## Estimated Effort

| Task | Description | Time |
|------|-------------|------|
| 1 | Module structure and data models | 20 min |
| 2 | Task state management | 30 min |
| 3 | Task decomposer (LLM) | 30 min |
| 4 | Task dispatcher | 30 min |
| 5 | FastAPI endpoints | 30 min |
| 6 | App integration | 20 min |
| 7 | Tests | 30 min |
| 8 | Documentation | 15 min |

**Total Phase 1: ~3 hours**

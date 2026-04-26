# Agent Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Agent Bridge module that provides a structured communication protocol between App (Manager) and Agents, with lifecycle management, result aggregation, and error standardization.

**Architecture:** Agent Bridge wraps the existing `UniversalAgentClient` with a structured protocol layer. It introduces `AgentMessage` JSON format, lifecycle handshake (init/heartbeat/terminate), standardized error types, and result aggregation. The existing `TaskDispatcher` will be updated to use the new `AgentBridge` instead of calling `openclaw.send()` directly.

**Tech Stack:** Python 3.10+, dataclasses, asyncio, existing openclaw client, existing task_manager

---

## File Structure

```
backend/src/across_agents_assistant/agent_bridge/
├── __init__.py                  # Module exports
├── protocol.py                  # AgentMessage, AgentResponse, MessageType dataclasses
├── errors.py                    # AgentError enum, AgentException
├── agent.py                     # Agent session (lifecycle, invoke, heartbeat)
├── bridge.py                    # AgentBridge (main entry point, batch_invoke, result aggregation)
├── result.py                   # TaskResult, SubtaskResult aggregation
└── tests/
    ├── __init__.py
    ├── test_protocol.py
    ├── test_errors.py
    ├── test_agent.py
    ├── test_bridge.py
    └── test_result.py
```

---

## TASK 1: Create Agent Bridge Module Structure and Protocol

**Files:**
- Create: `backend/src/across_agents_assistant/agent_bridge/__init__.py`
- Create: `backend/src/across_agents_assistant/agent_bridge/protocol.py`
- Create: `backend/tests/agent_bridge/__init__.py`
- Create: `backend/tests/agent_bridge/test_protocol.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend/src/across_agents_assistant/agent_bridge
mkdir -p /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend/tests/agent_bridge
touch /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend/src/across_agents_assistant/agent_bridge/__init__.py
touch /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend/tests/agent_bridge/__init__.py
```

- [ ] **Step 2: Write failing test**

```python
# backend/tests/agent_bridge/test_protocol.py
import pytest
import json
from across_agents_assistant.agent_bridge.protocol import (
    MessageType, AgentMessage, AgentResponse, InvokeRequest
)

def test_message_type_enum():
    assert MessageType.INVOKE.value == "invoke"
    assert MessageType.RESPONSE.value == "response"
    assert MessageType.HEARTBEAT.value == "heartbeat"
    assert MessageType.CANCEL.value == "cancel"
    assert MessageType.ERROR.value == "error"

def test_agent_message_creation():
    msg = AgentMessage(
        message_id="msg-123",
        message_type=MessageType.INVOKE,
        agent_id="openclaw",
        payload={"content": "Hello"},
        metadata={"task_id": "task-1"}
    )
    assert msg.message_id == "msg-123"
    assert msg.message_type == MessageType.INVOKE
    assert msg.agent_id == "openclaw"
    assert msg.payload["content"] == "Hello"

def test_agent_message_to_json():
    msg = AgentMessage(
        message_id="msg-123",
        message_type=MessageType.INVOKE,
        agent_id="openclaw",
        payload={"content": "Hello"}
    )
    json_str = msg.to_json()
    parsed = json.loads(json_str)
    assert parsed["message_id"] == "msg-123"
    assert parsed["message_type"] == "invoke"

def test_agent_message_from_json():
    json_str = '{"message_id":"msg-123","message_type":"invoke","agent_id":"openclaw","payload":{"content":"Hello"},"metadata":{}}'
    msg = AgentMessage.from_json(json_str)
    assert msg.message_id == "msg-123"
    assert msg.message_type == MessageType.INVOKE
    assert msg.payload["content"] == "Hello"

def test_invoke_request_creation():
    req = InvokeRequest(
        request_id="req-1",
        agent_id="openclaw",
        message="帮我分析这个代码",
        context={"frontmost_app": "Chrome"}
    )
    assert req.request_id == "req-1"
    assert req.agent_id == "openclaw"
    assert "frontmost_app" in req.context

def test_agent_response_fields():
    resp = AgentResponse(
        message_id="msg-123",
        request_id="req-1",
        success=True,
        output="分析完成",
        agent_id="openclaw"
    )
    assert resp.success == True
    assert resp.output == "分析完成"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_protocol.py -v 2>&1 | head -20`
Expected: FAIL - module not found

- [ ] **Step 4: Write protocol.py implementation**

```python
# backend/src/across_agents_assistant/agent_bridge/protocol.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, Optional
import json
import uuid
import time

class MessageType(str, Enum):
    INVOKE = "invoke"
    RESPONSE = "response"
    HEARTBEAT = "heartbeat"
    CANCEL = "cancel"
    ERROR = "error"

@dataclass
class AgentMessage:
    """Structured message format for Agent Bridge protocol."""
    message_id: str
    message_type: MessageType
    agent_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        data["message_type"] = self.message_type.value
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> AgentMessage:
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        data["message_type"] = MessageType(data["message_type"])
        return cls(**data)

    @staticmethod
    def new_invoke(agent_id: str, content: str, context: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None) -> AgentMessage:
        """Create a new INVOKE message."""
        return AgentMessage(
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            message_type=MessageType.INVOKE,
            agent_id=agent_id,
            payload={"content": content, "context": context or {}},
            metadata=metadata or {}
        )

@dataclass
class InvokeRequest:
    """Request to invoke an agent."""
    request_id: str
    agent_id: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    timeout: float = 120.0  # seconds

    @staticmethod
    def new(agent_id: str, message: str, context: Optional[Dict[str, Any]] = None) -> InvokeRequest:
        return InvokeRequest(
            request_id=f"req-{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            message=message,
            context=context or {}
        )

@dataclass
class AgentResponse:
    """Response from an agent invocation."""
    message_id: str
    request_id: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    agent_id: str
    elapsed_sec: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.success

    @property
    def is_error(self) -> bool:
        return not self.success
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_protocol.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge
git add backend/src/across_agents_assistant/agent_bridge/__init__.py backend/src/across_agents_assistant/agent_bridge/protocol.py backend/tests/agent_bridge/__init__.py backend/tests/agent_bridge/test_protocol.py
git commit -m "feat(agent_bridge): create module structure and protocol"
```

---

## TASK 2: Implement Agent Error Types

**Files:**
- Create: `backend/src/across_agents_assistant/agent_bridge/errors.py`
- Create: `backend/tests/agent_bridge/test_errors.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/agent_bridge/test_errors.py
import pytest
from across_agents_assistant.agent_bridge.errors import AgentError, AgentException

def test_agent_error_enum():
    assert AgentError.TIMEOUT.value == "timeout"
    assert AgentError.UNAVAILABLE.value == "unavailable"
    assert AgentError.CANCELLED.value == "cancelled"
    assert AgentError.INVALID_RESPONSE.value == "invalid_response"
    assert AgentError.PROTOCOL_ERROR.value == "protocol_error"
    assert AgentError.UNKNOWN.value == "unknown"

def test_agent_exception_creation():
    exc = AgentException(
        error=AgentError.TIMEOUT,
        agent_id="openclaw",
        message="Agent timed out after 120s"
    )
    assert exc.error == AgentError.TIMEOUT
    assert exc.agent_id == "openclaw"
    assert "timed out" in exc.message

def test_agent_exception_str():
    exc = AgentException(
        error=AgentError.UNAVAILABLE,
        agent_id="claude",
        message="Agent not ready"
    )
    assert str(exc) == "[unavailable] claude: Agent not ready"

def test_agent_exception_from_response():
    from across_agents_assistant.agent_bridge.protocol import AgentResponse
    resp = AgentResponse(
        message_id="msg-1",
        request_id="req-1",
        success=False,
        error="Connection refused",
        agent_id="hermes"
    )
    exc = AgentException.from_response(resp)
    assert exc.error == AgentError.UNKNOWN
    assert exc.agent_id == "hermes"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_errors.py -v 2>&1 | head -20`
Expected: FAIL - module not found

- [ ] **Step 3: Write errors.py implementation**

```python
# backend/src/across_agents_assistant/agent_bridge/errors.py
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .protocol import AgentResponse

class AgentError(str, Enum):
    """Standardized agent error types."""
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"
    INVALID_RESPONSE = "invalid_response"
    PROTOCOL_ERROR = "protocol_error"
    UNKNOWN = "unknown"

@dataclass
class AgentException(Exception):
    """Exception raised when agent operations fail."""
    error: AgentError
    agent_id: str
    message: str
    details: Optional[str] = None

    def __str__(self) -> str:
        return f"[{self.error.value}] {self.agent_id}: {self.message}"

    @classmethod
    def from_response(cls, response: AgentResponse) -> AgentException:
        """Create exception from failed agent response."""
        if response.error:
            msg = response.error
        else:
            msg = "Unknown error"

        # Try to classify the error
        error_type = AgentError.UNKNOWN
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            error_type = AgentError.TIMEOUT
        elif "unavailable" in msg.lower() or "not ready" in msg.lower():
            error_type = AgentError.UNAVAILABLE
        elif "cancelled" in msg.lower() or "cancel" in msg.lower():
            error_type = AgentError.CANCELLED
        elif "invalid" in msg.lower() or "parse" in msg.lower():
            error_type = AgentError.INVALID_RESPONSE

        return cls(
            error=error_type,
            agent_id=response.agent_id,
            message=msg,
            details=response.metadata.get("raw_error")
        )

    @classmethod
    def timeout(cls, agent_id: str, timeout_sec: float) -> AgentException:
        return cls(
            error=AgentError.TIMEOUT,
            agent_id=agent_id,
            message=f"Agent timed out after {timeout_sec}s"
        )

    @classmethod
    def unavailable(cls, agent_id: str) -> AgentException:
        return cls(
            error=AgentError.UNAVAILABLE,
            agent_id=agent_id,
            message=f"Agent {agent_id} is not available"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge
git add backend/src/across_agents_assistant/agent_bridge/errors.py backend/tests/agent_bridge/test_errors.py
git commit -m "feat(agent_bridge): implement agent error types"
```

---

## TASK 3: Implement Result Aggregation

**Files:**
- Create: `backend/src/across_agents_assistant/agent_bridge/result.py`
- Create: `backend/tests/agent_bridge/test_result.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/agent_bridge/test_result.py
import pytest
from across_agents_assistant.agent_bridge.result import TaskResult, SubtaskResult, ResultStatus

def test_result_status_enum():
    assert ResultStatus.PENDING.value == "pending"
    assert ResultStatus.RUNNING.value == "running"
    assert ResultStatus.COMPLETED.value == "completed"
    assert ResultStatus.FAILED.value == "failed"
    assert ResultStatus.CANCELLED.value == "cancelled"

def test_subtask_result_creation():
    result = SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="分析完成"
    )
    assert result.subtask_id == "st-1"
    assert result.output == "分析完成"

def test_task_result_initial_state():
    result = TaskResult(task_id="task-1")
    assert result.task_id == "task-1"
    assert result.is_complete == False
    assert len(result.subtask_results) == 0

def test_task_result_add_subtask():
    result = TaskResult(task_id="task-1")
    result.add_subtask_result(SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="第一步完成"
    ))
    assert len(result.subtask_results) == 1
    assert result.is_complete == False  # Only 1 of 2

def test_task_result_all_complete():
    result = TaskResult(task_id="task-1", total_subtasks=2)
    result.add_subtask_result(SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="第一步完成"
    ))
    result.add_subtask_result(SubtaskResult(
        subtask_id="st-2",
        agent_id="openclaw",
        status=ResultStatus.COMPLETED,
        output="第二步完成"
    ))
    assert result.is_complete == True

def test_task_result_any_failed():
    result = TaskResult(task_id="task-1", total_subtasks=2)
    result.add_subtask_result(SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.FAILED,
        error="执行失败"
    ))
    assert result.has_failures == True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_result.py -v 2>&1 | head -20`
Expected: FAIL - module not found

- [ ] **Step 3: Write result.py implementation**

```python
# backend/src/across_agents_assistant/agent_bridge/result.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict

class ResultStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class SubtaskResult:
    """Result from a single subtask execution."""
    subtask_id: str
    agent_id: str
    status: ResultStatus
    output: Optional[str] = None
    error: Optional[str] = None
    elapsed_sec: Optional[float] = None

    @property
    def is_success(self) -> bool:
        return self.status == ResultStatus.COMPLETED

    @property
    def is_failure(self) -> bool:
        return self.status in (ResultStatus.FAILED, ResultStatus.CANCELLED)

@dataclass
class TaskResult:
    """Aggregated result from multiple subtasks."""
    task_id: str
    subtask_results: List[SubtaskResult] = field(default_factory=list)
    total_subtasks: int = 0
    metadata: Dict[str, any] = field(default_factory=dict)

    def add_subtask_result(self, result: SubtaskResult) -> None:
        """Add a subtask result."""
        self.subtask_results.append(result)

    @property
    def completed_count(self) -> int:
        return sum(1 for r in self.subtask_results if r.status == ResultStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.subtask_results if r.status == ResultStatus.FAILED)

    @property
    def has_failures(self) -> bool:
        return self.failed_count > 0

    @property
    def is_complete(self) -> bool:
        if self.total_subtasks > 0:
            return self.completed_count + self.failed_count >= self.total_subtasks
        return False

    @property
    def progress(self) -> float:
        if self.total_subtasks == 0:
            return 0.0
        return len(self.subtask_results) / self.total_subtasks

    def get_summary(self) -> str:
        """Get a human-readable summary of the results."""
        lines = [f"Task {self.task_id}: {self.completed_count}/{self.total_subtasks} completed"]
        for r in self.subtask_results:
            status_icon = "✅" if r.is_success else "❌"
            lines.append(f"  {status_icon} [{r.agent_id}] {r.subtask_id}: {r.output or r.error}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_result.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge
git add backend/src/across_agents_assistant/agent_bridge/result.py backend/tests/agent_bridge/test_result.py
git commit -m "feat(agent_bridge): implement result aggregation"
```

---

## TASK 4: Implement Agent Session

**Files:**
- Create: `backend/src/across_agents_assistant/agent_bridge/agent.py`
- Create: `backend/tests/agent_bridge/test_agent.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/agent_bridge/test_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from across_agents_assistant.agent_bridge.agent import AgentSession

@pytest.fixture
def mock_openclaw_client():
    mock = MagicMock()
    mock.send = AsyncMock(return_value=MagicMock(text="Agent response", session_id="sess-1"))
    return mock

def test_agent_session_creation():
    session = AgentSession(
        agent_id="openclaw",
        client=AsyncMock()
    )
    assert session.agent_id == "openclaw"
    assert session.is_initialized == False

def test_agent_session_initialize():
    session = AgentSession(
        agent_id="openclaw",
        client=AsyncMock()
    )
    session.initialize()
    assert session.is_initialized == True

def test_agent_session_invoke(mock_openclaw_client):
    session = AgentSession(
        agent_id="openclaw",
        client=mock_openclaw_client
    )
    session.initialize()
    response = session.invoke("帮我分析代码")
    assert response.success == True
    assert response.output == "Agent response"

def test_agent_session_invoke_before_init(mock_openclaw_client):
    session = AgentSession(
        agent_id="openclaw",
        client=mock_openclaw_client
    )
    # Should auto-initialize
    response = session.invoke("帮我分析代码")
    assert session.is_initialized == True
    assert response.success == True

def test_agent_session_invoke_error():
    mock_client = AsyncMock()
    mock_client.send = AsyncMock(side_effect=Exception("Connection failed"))
    session = AgentSession(agent_id="claude", client=mock_client)
    session.initialize()
    response = session.invoke("分析代码")
    assert response.success == False
    assert "Connection failed" in response.error

def test_agent_session_heartbeat():
    mock_client = AsyncMock()
    session = AgentSession(agent_id="hermes", client=mock_client)
    session.initialize()
    is_alive = session.heartbeat()
    assert is_alive == True

def test_agent_session_shutdown():
    mock_client = AsyncMock()
    session = AgentSession(agent_id="openclaw", client=mock_client)
    session.initialize()
    session.shutdown()
    assert session.is_initialized == False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_agent.py -v 2>&1 | head -20`
Expected: FAIL - module not found

- [ ] **Step 3: Write agent.py implementation**

```python
# backend/src/across_agents_assistant/agent_bridge/agent.py
from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional, Dict, Any

from .protocol import AgentResponse, InvokeRequest
from .errors import AgentException, AgentError

logger = logging.getLogger("across_agents_assistant.agent_bridge")

class AgentSession:
    """
    Manages a session with a single agent.

    Handles lifecycle (initialize, heartbeat, shutdown) and
    provides invoke() method for agent communication.
    """

    def __init__(self, agent_id: str, client: Any):
        self.agent_id = agent_id
        self._client = client
        self._is_initialized = False
        self._last_heartbeat: float = 0
        self._session_metadata: Dict[str, Any] = {}

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def initialize(self) -> None:
        """Initialize the agent session."""
        if self._is_initialized:
            return

        try:
            logger.info(f"Initializing agent session: {self.agent_id}")
            # For now, just mark as initialized
            # In future, could do capability negotiation here
            self._is_initialized = True
            self._last_heartbeat = time.time()
            self._session_metadata["initialized_at"] = self._last_heartbeat
        except Exception as e:
            logger.error(f"Failed to initialize agent {self.agent_id}: {e}")
            raise AgentException.from_response(
                AgentResponse(
                    message_id="",
                    request_id="",
                    success=False,
                    error=str(e),
                    agent_id=self.agent_id
                )
            )

    def invoke(self, message: str, context: Optional[Dict[str, Any]] = None, timeout: float = 120.0) -> AgentResponse:
        """
        Invoke the agent with a message.

        Returns AgentResponse with success=True/False.
        """
        # Auto-initialize if not already
        if not self._is_initialized:
            self.initialize()

        request_id = f"req-{int(time.time() * 1000)}"
        start_time = time.time()

        try:
            logger.info(f"Invoking agent {self.agent_id}: {message[:50]}...")

            # Call the underlying openclaw client
            # Note: This is sync in the current implementation
            reply = self._client.send(
                message=message,
                session_id=None,
                use_current=True,
                target_agent=self.agent_id
            )

            elapsed = time.time() - start_time

            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=True,
                output=reply.text if reply and reply.text else "",
                agent_id=self.agent_id,
                elapsed_sec=elapsed
            )

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error(f"Agent {self.agent_id} timed out after {elapsed:.1f}s")
            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=False,
                error=f"Timeout after {timeout}s",
                agent_id=self.agent_id,
                elapsed_sec=elapsed
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Agent {self.agent_id} invocation failed: {e}")
            return AgentResponse(
                message_id=f"msg-{int(time.time() * 1000)}",
                request_id=request_id,
                success=False,
                error=str(e),
                agent_id=self.agent_id,
                elapsed_sec=elapsed
            )

    def heartbeat(self) -> bool:
        """
        Check if the agent is still alive.

        Returns True if agent responds to heartbeat.
        """
        if not self._is_initialized:
            return False

        try:
            # Simple check - just verify session exists
            self._last_heartbeat = time.time()
            return True
        except Exception as e:
            logger.warning(f"Heartbeat failed for {self.agent_id}: {e}")
            return False

    def shutdown(self) -> None:
        """Shutdown the agent session gracefully."""
        logger.info(f"Shutting down agent session: {self.agent_id}")
        self._is_initialized = False
        self._last_heartbeat = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge
git add backend/src/across_agents_assistant/agent_bridge/agent.py backend/tests/agent_bridge/test_agent.py
git commit -m "feat(agent_bridge): implement agent session"
```

---

## TASK 5: Implement AgentBridge Main Interface

**Files:**
- Create: `backend/src/across_agents_assistant/agent_bridge/bridge.py`
- Create: `backend/tests/agent_bridge/test_bridge.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/agent_bridge/test_bridge.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from across_agents_assistant.agent_bridge.bridge import AgentBridge
from across_agents_assistant.agent_bridge.protocol import InvokeRequest
from across_agents_assistant.agent_bridge.result import TaskResult, ResultStatus, SubtaskResult

@pytest.fixture
def mock_openclaw_client():
    mock = MagicMock()
    mock.send = AsyncMock(return_value=MagicMock(text="Response", session_id="sess-1"))
    return mock

@pytest.fixture
def bridge(mock_openclaw_client):
    return AgentBridge(openclaw_client=mock_openclaw_client)

def test_bridge_initialization(bridge):
    assert bridge.get_agent_ids() == ["openclaw", "hermes", "claude"]
    assert bridge.is_agent_available("openclaw") == True

def test_bridge_get_agent_session(bridge):
    session = bridge.get_session("claude")
    assert session is not None
    assert session.agent_id == "claude"

def test_bridge_invoke_single(bridge):
    response = bridge.invoke("openclaw", "分析代码")
    assert response.success == True
    assert response.output == "Response"

def test_bridge_batch_invoke(bridge):
    requests = [
        InvokeRequest.new("openclaw", "任务1"),
        InvokeRequest.new("claude", "任务2"),
        InvokeRequest.new("hermes", "任务3"),
    ]
    responses = bridge.batch_invoke(requests)
    assert len(responses) == 3
    assert all(r.success for r in responses)

def test_bridge_invoke_unknown_agent(bridge):
    response = bridge.invoke("unknown_agent", "测试")
    assert response.success == False
    assert "unknown" in response.error.lower()

def test_bridge_task_result_tracking(bridge):
    result = bridge.create_task_result("task-1", 2)
    assert result.task_id == "task-1"
    assert result.is_complete == False

def test_bridge_add_result_to_task(bridge):
    result = bridge.create_task_result("task-1", 2)
    bridge.add_subtask_result(result, SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="完成"
    ))
    assert result.completed_count == 1
    assert result.is_complete == False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_bridge.py -v 2>&1 | head -20`
Expected: FAIL - module not found

- [ ] **Step 3: Write bridge.py implementation**

```python
# backend/src/across_agents_assistant/agent_bridge/bridge.py
from __future__ import annotations
import logging
import time
import uuid
from typing import Dict, List, Optional, Any

from .protocol import AgentResponse, InvokeRequest, MessageType, AgentMessage
from .agent import AgentSession
from .result import TaskResult, SubtaskResult, ResultStatus
from .errors import AgentException, AgentError

logger = logging.getLogger("across_agents_assistant.agent_bridge")

# Default agents
DEFAULT_AGENTS = ["openclaw", "hermes", "claude"]

class AgentBridge:
    """
    Main interface for Agent Bridge.

    Provides:
    - invoke(): Single agent invocation
    - batch_invoke(): Multiple agents in parallel
    - Task result tracking and aggregation
    - Lifecycle management for agent sessions
    """

    def __init__(self, openclaw_client: Any):
        self._client = openclaw_client
        self._sessions: Dict[str, AgentSession] = {}
        self._task_results: Dict[str, TaskResult] = {}
        self._initialize_sessions()

    def _initialize_sessions(self) -> None:
        """Initialize sessions for all known agents."""
        for agent_id in DEFAULT_AGENTS:
            self._sessions[agent_id] = AgentSession(
                agent_id=agent_id,
                client=self._client
            )
        logger.info(f"Initialized AgentBridge with {len(self._sessions)} agents")

    def get_agent_ids(self) -> List[str]:
        """Get list of available agent IDs."""
        return list(self._sessions.keys())

    def is_agent_available(self, agent_id: str) -> bool:
        """Check if an agent is available."""
        return agent_id in self._sessions

    def get_session(self, agent_id: str) -> Optional[AgentSession]:
        """Get the session for an agent."""
        return self._sessions.get(agent_id)

    def invoke(self, agent_id: str, message: str, context: Optional[Dict[str, Any]] = None, timeout: float = 120.0) -> AgentResponse:
        """
        Invoke a single agent.

        Args:
            agent_id: Target agent (openclaw/hermes/claude)
            message: Message to send
            context: Optional context dict
            timeout: Timeout in seconds

        Returns:
            AgentResponse with success=True/False
        """
        if agent_id not in self._sessions:
            return AgentResponse(
                message_id=f"msg-{uuid.uuid4().hex[:8]}",
                request_id=f"req-{uuid.uuid4().hex[:8]}",
                success=False,
                error=f"Unknown agent: {agent_id}",
                agent_id=agent_id
            )

        session = self._sessions[agent_id]
        return session.invoke(message, context, timeout)

    def batch_invoke(self, requests: List[InvokeRequest]) -> List[AgentResponse]:
        """
        Invoke multiple agents in parallel.

        Args:
            requests: List of InvokeRequest objects

        Returns:
            List of AgentResponse objects (in same order as requests)
        """
        import concurrent.futures

        responses = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(requests)) as executor:
            future_to_request = {
                executor.submit(self.invoke, req.agent_id, req.message, req.context, req.timeout): req
                for req in requests
            }

            for req in requests:
                future = future_to_request[req]
                try:
                    response = future.result(timeout=req.timeout)
                except Exception as e:
                    response = AgentResponse(
                        message_id=f"msg-{uuid.uuid4().hex[:8]}",
                        request_id=req.request_id,
                        success=False,
                        error=str(e),
                        agent_id=req.agent_id
                    )
                responses.append(response)

        return responses

    def create_task_result(self, task_id: str, total_subtasks: int = 0) -> TaskResult:
        """Create a new task result tracker."""
        result = TaskResult(task_id=task_id, total_subtasks=total_subtasks)
        self._task_results[task_id] = result
        return result

    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """Get a task result by ID."""
        return self._task_results.get(task_id)

    def add_subtask_result(self, task_result: TaskResult, subtask_result: SubtaskResult) -> None:
        """Add a subtask result to a task result."""
        task_result.add_subtask_result(subtask_result)

    def shutdown(self) -> None:
        """Shutdown all agent sessions."""
        logger.info("Shutting down AgentBridge")
        for session in self._sessions.values():
            try:
                session.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down session {session.agent_id}: {e}")
        self._sessions.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/test_bridge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge
git add backend/src/across_agents_assistant/agent_bridge/bridge.py backend/tests/agent_bridge/test_bridge.py
git commit -m "feat(agent_bridge): implement AgentBridge main interface"
```

---

## TASK 6: Update TaskDispatcher to Use AgentBridge

**Files:**
- Modify: `backend/src/across_agents_assistant/task_manager/dispatcher.py`

- [ ] **Step 1: Read current dispatcher.py**

Read the current dispatcher.py to understand how it calls agents.

- [ ] **Step 2: Update dispatcher to use AgentBridge**

The current dispatcher calls `self._openclaw.send()` directly. Update it to use `AgentBridge` instead.

Add to imports:
```python
from ..agent_bridge.bridge import AgentBridge
from ..agent_bridge.result import SubtaskResult, ResultStatus
```

Update `__init__`:
```python
def __init__(self, state: TaskState, openclaw_client: UniversalAgentClient):
    self._state = state
    self._openclaw = openclaw_client
    # Use AgentBridge for agent communication
    self._agent_bridge = AgentBridge(openclaw_client)
    # ... rest unchanged
```

Update `_execute_agent_job`:
```python
def _execute_agent_job(self, job: Job, subtask: SubTask, target_agent: str) -> JobResult:
    """Execute a job using the specified agent via AgentBridge."""
    try:
        self._state.update_job_progress(job.job_id, 0.1, f"Connecting to {target_agent} agent...")
        self._notify_progress(job.job_id, JobStatus.RUNNING, 0.1, "Connecting...")

        # Use AgentBridge instead of direct openclaw call
        response = self._agent_bridge.invoke(
            agent_id=target_agent,
            message=subtask.description,
            context={},
            timeout=120.0
        )

        self._state.update_job_progress(job.job_id, 0.9, "Processing response...")
        self._notify_progress(job.job_id, JobStatus.RUNNING, 0.9, "Processing...")

        if response.is_success:
            return JobResult(job_id=job.job_id, success=True, output=response.output)
        else:
            return JobResult(job_id=job.job_id, success=False, error=response.error)

    except Exception as e:
        return JobResult(job_id=job.job_id, success=False, error=str(e))
```

- [ ] **Step 3: Test imports**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -c "from across_agents_assistant.task_manager.dispatcher import TaskDispatcher; print('Imports OK')"`

- [ ] **Step 4: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge
git add backend/src/across_agents_assistant/task_manager/dispatcher.py
git commit -m "feat(dispatcher): use AgentBridge for agent communication"
```

---

## TASK 7: Add Tests for Agent Bridge Integration

**Files:**
- Create: `backend/tests/agent_bridge/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# backend/tests/agent_bridge/test_integration.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from across_agents_assistant.agent_bridge.bridge import AgentBridge
from across_agents_assistant.agent_bridge.protocol import InvokeRequest
from across_agents_assistant.agent_bridge.result import TaskResult, ResultStatus, SubtaskResult

def test_bridge_full_invoke_flow():
    """Test complete flow: create request, invoke, get response."""
    mock_client = MagicMock()
    mock_client.send = AsyncMock(return_value=MagicMock(text="Analysis complete", session_id="sess-1"))

    bridge = AgentBridge(openclaw_client=mock_client)

    # Invoke
    response = bridge.invoke("claude", "Analyze this code")

    # Verify
    assert response.success == True
    assert response.output == "Analysis complete"
    assert response.agent_id == "claude"

def test_bridge_batch_invoke_parallel():
    """Test batch invoke runs in parallel."""
    mock_client = MagicMock()
    mock_client.send = AsyncMock(return_value=MagicMock(text="Done", session_id="sess-1"))

    bridge = AgentBridge(openclaw_client=mock_client)

    requests = [
        InvokeRequest.new("openclaw", "Task 1"),
        InvokeRequest.new("hermes", "Task 2"),
        InvokeRequest.new("claude", "Task 3"),
    ]

    responses = bridge.batch_invoke(requests)

    assert len(responses) == 3
    assert all(r.success for r in responses)

def test_bridge_task_result_tracking():
    """Test task result aggregation."""
    mock_client = MagicMock()
    mock_client.send = AsyncMock(return_value=MagicMock(text="Done", session_id="sess-1"))

    bridge = AgentBridge(openclaw_client=mock_client)

    # Create task with 2 subtasks
    task_result = bridge.create_task_result("task-1", total_subtasks=2)

    # Add subtask results
    bridge.add_subtask_result(task_result, SubtaskResult(
        subtask_id="st-1",
        agent_id="claude",
        status=ResultStatus.COMPLETED,
        output="Part 1 done"
    ))

    assert task_result.completed_count == 1
    assert task_result.is_complete == False

    bridge.add_subtask_result(task_result, SubtaskResult(
        subtask_id="st-2",
        agent_id="openclaw",
        status=ResultStatus.COMPLETED,
        output="Part 2 done"
    ))

    assert task_result.is_complete == True
    assert task_result.progress == 1.0
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge/backend && python3 -m pytest tests/agent_bridge/ -v`

- [ ] **Step 3: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge
git add backend/tests/agent_bridge/test_integration.py
git commit -m "test(agent_bridge): add integration tests"
```

---

## TASK 8: Update Documentation

**Files:**
- Create: `docs/superpowers/plans/2026-04-26-agent-bridge-spec.md`

- [ ] **Step 1: Create spec document**

```markdown
# Agent Bridge Specification

## Overview

Agent Bridge provides a structured communication protocol between App (Manager) and Agents, replacing the direct CLI invocation with a proper abstraction layer.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       AgentBridge                           │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │openclaw     │  │hermes      │  │claude       │        │
│  │Session      │  │Session      │  │Session      │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │
│         └────────────────┼────────────────┘                │
│                          │                                 │
│                    UniversalAgentClient                     │
└─────────────────────────────────────────────────────────────┘
```

## Protocol

### Message Types
- `INVOKE`: Request to execute a task
- `RESPONSE`: Result of execution
- `HEARTBEAT`: Liveness check
- `CANCEL`: Cancellation request
- `ERROR`: Error notification

### AgentResponse
```python
@dataclass
class AgentResponse:
    message_id: str
    request_id: str
    success: bool
    output: Optional[str]
    error: Optional[str]
    agent_id: str
    elapsed_sec: Optional[float]
```

## Error Types

| Error | Description |
|-------|-------------|
| TIMEOUT | Agent did not respond within timeout |
| UNAVAILABLE | Agent is not ready |
| CANCELLED | Request was cancelled |
| INVALID_RESPONSE | Agent returned unparseable response |
| PROTOCOL_ERROR | Message format error |
| UNKNOWN | Unclassified error |

## Result Aggregation

### TaskResult
Tracks multiple subtask results and computes:
- `is_complete`: All subtasks finished
- `has_failures`: Any subtask failed
- `progress`: Completion percentage

## API

### AgentBridge
```python
class AgentBridge:
    def invoke(agent_id: str, message: str, context: dict = None) -> AgentResponse
    def batch_invoke(requests: List[InvokeRequest]) -> List[AgentResponse]
    def create_task_result(task_id: str, total_subtasks: int) -> TaskResult
    def shutdown()
```

## Phase 2 Limitations

- Still uses UniversalAgentClient internally
- No persistence of task results
- No retry with backoff (yet)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/fanhcy/Documents/projects/across-agents-assistant/.claude/worktrees/feat+agent-bridge
git add docs/superpowers/plans/2026-04-26-agent-bridge-spec.md
git commit -m "docs: add Agent Bridge specification"
```

---

## Acceptance Criteria

### Functional Requirements

| ID | Criteria | Verification |
|----|----------|---------------|
| AB1 | AgentMessage protocol format works | Unit tests pass |
| AB2 | AgentError types defined correctly | Unit tests pass |
| AB3 | AgentSession manages lifecycle | Unit tests pass |
| AB4 | AgentBridge.invoke() works | Unit tests pass |
| AB5 | AgentBridge.batch_invoke() works | Unit tests pass |
| AB6 | TaskResult aggregation works | Unit tests pass |
| AB7 | TaskDispatcher uses AgentBridge | Integration test pass |
| AB8 | Documentation complete | Spec doc created |

### Technical Requirements

- [ ] All dataclasses use consistent field naming
- [ ] Error types are properly classified
- [ ] All tests pass
- [ ] TaskDispatcher updated to use AgentBridge
- [ ] Documentation complete
```

---

## Estimated Effort

| Task | Description | Time |
|------|-------------|------|
| 1 | Module structure and protocol | 20 min |
| 2 | Error types | 15 min |
| 3 | Result aggregation | 20 min |
| 4 | Agent session | 25 min |
| 5 | AgentBridge interface | 30 min |
| 6 | Update TaskDispatcher | 20 min |
| 7 | Integration tests | 20 min |
| 8 | Documentation | 10 min |

**Total Phase 2: ~2.5 hours**

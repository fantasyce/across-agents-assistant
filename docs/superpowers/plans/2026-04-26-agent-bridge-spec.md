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

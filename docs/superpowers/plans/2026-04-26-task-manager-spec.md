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

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/tasks | Create and decompose a task |
| GET | /api/tasks | List all tasks |
| GET | /api/tasks/{task_id} | Get task details |
| POST | /api/tasks/{task_id}/dispatch | Dispatch subtasks |
| GET | /api/tasks/{task_id}/jobs/{job_id} | Get job details |
| POST | /api/tasks/{task_id}/jobs/{job_id}/cancel | Cancel a job |

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

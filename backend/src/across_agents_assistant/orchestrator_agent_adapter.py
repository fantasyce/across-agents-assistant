from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def build_orchestrator_agent_message(task: dict[str, Any], subtask: dict[str, Any]) -> str:
    path = str(subtask.get("path") or "README.md")
    lines = [
        f"Task goal: {task.get('goal') or ''}",
        f"Subtask goal: {subtask.get('goal') or subtask.get('description') or f'Produce {path}.'}",
        f"Required output file: {path}",
    ]
    dependencies = subtask.get("dependencies") or []
    if dependencies:
        lines.append("Dependency subtask ids: " + ", ".join(str(item) for item in dependencies))
    wave = subtask.get("wave")
    if wave:
        lines.append(f"Wave: {wave}")
    lines.extend(
        [
            "",
            "Complete only this subtask. Create or edit the required output file inside the project directory.",
            "Do not complete downstream subtasks unless they are explicitly part of this subtask.",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="across-agents-assistant-orchestrator-agent-adapter")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)

    try:
        task = _json_env("ACROSS_TASK_JSON")
        subtask = _json_env("ACROSS_SUBTASK_JSON")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    agent_id = str(args.agent or subtask.get("agent") or task.get("agent") or "").strip().lower()
    if not agent_id or agent_id == "demo":
        print(f"AAA host adapter requires a non-demo agent id, got: {agent_id or '<empty>'}", file=sys.stderr)
        return 2

    project_dir = str(task.get("project_root") or os.getcwd())
    subtask_id = str(subtask.get("subtask_id") or "")
    path = str(subtask.get("path") or "README.md")
    context = {
        "task_id": str(task.get("task_id") or ""),
        "subtask_id": subtask_id,
        "allowed_writable_files": [path],
        "orchestrator_task": task,
        "orchestrator_subtask": subtask,
    }

    response = build_agent_bridge().invoke(
        agent_id,
        build_orchestrator_agent_message(task, subtask),
        context=context,
        timeout=args.timeout,
        project_dir=project_dir,
    )
    if not response or not response.is_success:
        error = getattr(response, "error", None) or "AAA host agent adapter failed"
        print(str(error), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "agent": agent_id,
                "subtask_id": subtask_id,
                "path": path,
                "output": response.output or "",
                "metadata": response.metadata or {},
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_agent_bridge():
    from .agent_bridge.bridge import AgentBridge
    from .agent_manager import AgentManager
    from .llm_gateway.gateway import get_gateway
    from .local_agent.client import UniversalAgentClient

    manager = AgentManager()
    return AgentBridge(
        UniversalAgentClient(manager),
        llm_gateway=get_gateway(),
    )


def _json_env(name: str) -> dict[str, Any]:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} is required")
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())

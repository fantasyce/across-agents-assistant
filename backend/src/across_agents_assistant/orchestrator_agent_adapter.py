from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import threading
import time
from typing import Any


_HOST_AGENT_HEARTBEAT_INTERVAL_SECONDS = 15.0
_KIMI_MAX_ATTEMPTS = 2
_KIMI_INTERNAL_FAILURE_RE = re.compile(
    r"logger\s+write\s+failed|internal\s+error|eperm\b[^\r\n]{0,80}\boperation\s+not\s+permitted|大脑没有返回任何内容",
    re.IGNORECASE,
)


def build_orchestrator_agent_message(task: dict[str, Any], subtask: dict[str, Any]) -> str:
    path = str(subtask.get("path") or "README.md")
    read_only = _is_read_only_task(task)
    lines = [
        f"Task goal: {task.get('goal') or ''}",
        f"Subtask goal: {subtask.get('goal') or subtask.get('description') or f'Produce {path}.'}",
    ]
    if read_only:
        lines.append(f"Inspection anchor (read-only): {path}")
    else:
        lines.append(f"Required output file: {path}")
    dependencies = subtask.get("dependencies") or []
    if dependencies:
        lines.append("Dependency subtask ids: " + ", ".join(str(item) for item in dependencies))
    wave = subtask.get("wave")
    if wave:
        lines.append(f"Wave: {wave}")
    lines.append("")
    if read_only:
        lines.extend(
            [
                "Complete this as a read-only analysis. Do not create, edit, rename, or delete any project file.",
                "Return the requested report in your final response; the host will preserve it as task evidence.",
            ]
        )
    else:
        lines.append(
            "Complete only this subtask. Create or edit the required output file inside the project directory."
        )
    lines.append("Do not complete downstream subtasks unless they are explicitly part of this subtask.")
    return "\n".join(lines)


def _is_read_only_task(task: dict[str, Any]) -> bool:
    metadata = task.get("metadata") or {}
    host_metadata = metadata.get("host_metadata") or {}
    return str(host_metadata.get("intent_mode") or "").strip().lower() == "read_only_analysis"


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
    read_only = _is_read_only_task(task)
    context = {
        "task_id": str(task.get("task_id") or ""),
        "subtask_id": subtask_id,
        "allowed_writable_files": [] if read_only else [path],
        "read_only": read_only,
        "orchestrator_task": task,
        "orchestrator_subtask": subtask,
    }

    invoke_kwargs = {
        "context": context,
        "timeout": args.timeout,
        "project_dir": project_dir,
    }
    message = build_orchestrator_agent_message(task, subtask)
    bridge = build_agent_bridge()
    restore_signal_handlers = _install_termination_handlers(bridge)
    try:
        if agent_id == "kimi":
            response = None
            for attempt in range(_KIMI_MAX_ATTEMPTS):
                try:
                    response = _invoke_with_heartbeat(bridge, agent_id, message, **invoke_kwargs)
                except Exception:
                    response = None
                if response and response.is_success and not _KIMI_INTERNAL_FAILURE_RE.search(str(response.output or "")):
                    break
                if attempt + 1 < _KIMI_MAX_ATTEMPTS:
                    time.sleep(1)
        else:
            response = _invoke_with_heartbeat(bridge, agent_id, message, **invoke_kwargs)
    finally:
        restore_signal_handlers()
    if not response or not response.is_success:
        error = (
            "Kimi host agent adapter failed"
            if agent_id == "kimi"
            else getattr(response, "error", None) or "AAA host agent adapter failed"
        )
        print(str(error), file=sys.stderr)
        return 1
    if agent_id == "kimi" and _KIMI_INTERNAL_FAILURE_RE.search(str(response.output or "")):
        print("Kimi host agent reported an internal runtime failure", file=sys.stderr)
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


def _invoke_with_heartbeat(bridge, agent_id: str, message: str, **kwargs):
    stop = threading.Event()

    def emit_heartbeats() -> None:
        while not stop.wait(_HOST_AGENT_HEARTBEAT_INTERVAL_SECONDS):
            try:
                print(
                    json.dumps(
                        {"type": "heartbeat", "agent": agent_id, "status": "running"},
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
            except (BrokenPipeError, OSError):
                return

    heartbeat_thread = threading.Thread(target=emit_heartbeats, daemon=True)
    heartbeat_thread.start()
    try:
        return bridge.invoke(agent_id, message, **kwargs)
    finally:
        stop.set()
        heartbeat_thread.join()


def build_agent_bridge():
    from .agent_bridge.bridge import AgentBridge
    from .agent_bridge.host_mcp_proxy import HostMCPToolProvider
    from .agent_manager import AgentManager
    from .llm_gateway.gateway import get_gateway
    from .local_agent.client import UniversalAgentClient

    manager = AgentManager()
    return AgentBridge(
        UniversalAgentClient(manager),
        llm_gateway=get_gateway(),
        host_tool_provider=HostMCPToolProvider(),
    )


def _terminate_bridge_on_signal(bridge, signum: int) -> None:
    client = getattr(bridge, "_client", None)
    shutdown_client = getattr(client, "shutdown", None)
    if callable(shutdown_client):
        shutdown_client()
    bridge.shutdown()
    raise SystemExit(128 + signum)


def _install_termination_handlers(bridge):
    previous = {}

    def handle(signum, _frame):
        _terminate_bridge_on_signal(bridge, signum)

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, handle)

    def restore() -> None:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    return restore


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

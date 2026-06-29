"""Protocol surfaces for optional local coding-agent interoperability.

This module is intentionally command-contract only. It does not start local
agents, does not read transcripts, and does not import agent implementations.
AAA remains the host that owns credentials, settings, and approval decisions.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .local_agent_health import resolve_local_agent_executable


LOCAL_AGENT_PROTOCOLS_SCHEMA = "across-local-agent-protocols/1.0"


def render_local_agent_protocol_contract() -> dict[str, Any]:
    kimi = _resolve_known_agent("kimi")
    qwen = _resolve_qwen_code()
    claude = _resolve_known_agent("claude")
    return {
        "schema_version": LOCAL_AGENT_PROTOCOLS_SCHEMA,
        "status": "passed",
        "kimi_code": {
            "agent_id": "kimi",
            "acp": "optional",
            "native_protocol": "kimi acp",
            "available": bool(kimi),
            "command": _command(kimi, "kimi", ["acp"]),
            "fallback": "cli_spawn",
            "fallback_command": _command(kimi, "kimi", ["-p", "{message}", "--output-format", "stream-json"]),
            "product_mode_imports": False,
        },
        "qwen_code": {
            "agent_id": "qwen-code",
            "daemon": "optional",
            "auto_memory": "optional",
            "auto_skills": "optional",
            "candidate_workspace_executor": "optional",
            "available": bool(qwen),
            "command": _command(qwen, "qwen", ["daemon"]),
            "status_command": _command(qwen, "qwen", ["daemon", "status"]),
            "product_mode_imports": False,
        },
        "claude_code": {
            "agent_id": "claude",
            "checkpoint_bridge": "optional",
            "available": bool(claude),
            "event_stream_projection": True,
            "replay": {
                "source": "orchestrator_event_stream",
                "checkpoint_concept": "Esc+Esc",
                "raw_transcripts_included": False,
            },
            "rewind": {
                "mode": "host_approved",
                "approval_required": True,
                "command": _command(claude, "claude", ["--resume", "{claude_session_id}"]),
            },
            "product_mode_imports": False,
        },
        "boundaries": {
            "product_paths_required": "~/.across",
            "host_owns_credentials": True,
            "raw_transcripts_included": False,
            "raw_secrets_included": False,
            "implementation_imports": False,
            "default_execution": "disabled_until_user_action",
        },
    }


def _resolve_known_agent(agent_id: str) -> str | None:
    path = resolve_local_agent_executable(agent_id)
    return path if path and _is_executable(path) else None


def _resolve_qwen_code() -> str | None:
    for name in ("qwen", "qwen-code", "qwen-code-daemon"):
        found = shutil.which(name)
        if found and _is_executable(found):
            return found
    for directory in ("~/.qwen-code/bin", "~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin"):
        for name in ("qwen", "qwen-code", "qwen-code-daemon"):
            candidate = Path(os.path.expanduser(directory)) / name
            if _is_executable(str(candidate)):
                return str(candidate)
    return None


def _command(path: str | None, fallback: str, args: list[str]) -> dict[str, Any]:
    return {
        "executable": path or fallback,
        "args": list(args),
        "requires_user_configuration": path is None,
    }


def _is_executable(path: str) -> bool:
    return os.path.isfile(os.path.expanduser(path)) and os.access(os.path.expanduser(path), os.X_OK)

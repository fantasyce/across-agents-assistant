from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any


AGENT_PLUGIN_RUNTIME_SCHEMA_VERSION = "across-aaa-agent-plugin-runtime/1.0"

DEFAULT_DOWNSTREAM_COMMANDS: dict[str, list[str]] = {
    "orchestrator": ["across-orchestrator", "external-agents", "list", "--json"],
    "autopilot": ["across-autopilot", "ecosystem-roadmap", "--json"],
    "context": ["across-context", "context-packs", "--all-projects", "--json"],
}

COMMAND_ENV_KEYS: dict[str, str] = {
    "orchestrator": "ACROSS_ORCHESTRATOR_EXTERNAL_AGENTS_CMD",
    "autopilot": "ACROSS_AUTOPILOT_ECOSYSTEM_ROADMAP_CMD",
    "context": "ACROSS_CONTEXT_CONTEXT_PACKS_CMD",
}


def probe_agent_plugin_runtime_status(
    *,
    commands: Mapping[str, list[str]] | None = None,
    env: Mapping[str, str] | None = None,
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    source_env = dict(env or os.environ)
    effective_commands = _effective_commands(commands, source_env)
    results = {
        name: _run_json_command(name, command, source_env, timeout_seconds=timeout_seconds)
        for name, command in effective_commands.items()
    }
    return build_agent_plugin_runtime_status(
        orchestrator=results.get("orchestrator", {}),
        autopilot=results.get("autopilot", {}),
        context=results.get("context", {}),
    )


def build_agent_plugin_runtime_status(
    *,
    orchestrator: Mapping[str, Any] | None = None,
    autopilot: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    orchestrator_section = _orchestrator_section(_dict(orchestrator))
    autopilot_section = _autopilot_section(_dict(autopilot))
    context_section = _context_section(_dict(context))
    sections = {
        "orchestrator_external_agents": orchestrator_section,
        "autopilot_agent_plugin_runtime": autopilot_section,
        "context_agent_packs": context_section,
    }
    statuses = [section["status"] for section in sections.values()]
    failed = [status for status in statuses if status == "failed"]
    attention = [status for status in statuses if status in {"attention", "unavailable", "unknown"}]
    external_agent_count = _first_int(orchestrator_section["summary"].get("agent_count"))
    healthy_external_agent_count = _first_int(orchestrator_section["summary"].get("healthy_agent_count"))
    autopilot_agent_plugin_count = _first_int(autopilot_section["summary"].get("agent_plugin_count"))
    ready_autopilot_agent_plugin_count = _first_int(autopilot_section["summary"].get("ready_agent_plugin_count"))
    context_agent_plugin_count = _first_int(context_section["summary"].get("agent_plugin_count"))
    agent_plugin_count = max(
        external_agent_count,
        _first_int(orchestrator_section["summary"].get("agent_count")),
        autopilot_agent_plugin_count,
        context_agent_plugin_count,
    )
    ready_agent_plugin_count = max(
        healthy_external_agent_count,
        ready_autopilot_agent_plugin_count,
    )
    return {
        "schema_version": AGENT_PLUGIN_RUNTIME_SCHEMA_VERSION,
        "status": "failed" if failed else "attention" if attention else "passed",
        "generated_at": _now(),
        "summary": {
            "downstream_count": len(sections),
            "downstream_ready_count": sum(1 for status in statuses if status == "passed"),
            "agent_plugin_count": agent_plugin_count,
            "external_agent_count": external_agent_count,
            "healthy_external_agent_count": healthy_external_agent_count,
            "ready_agent_plugin_count": ready_agent_plugin_count,
            "context_pack_count": _first_int(context_section["summary"].get("context_pack_count")),
            "context_memory_count": _first_int(context_section["summary"].get("memory_count")),
        },
        "sections": sections,
        "security": {
            "shell_execution": False,
            "secrets_included": False,
            "credentials_stay_with_host": True,
        },
    }


def _orchestrator_section(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = _dict(result.get("payload")) if "payload" in result else result
    summary = _dict(payload.get("summary"))
    agents = _list(payload.get("agents"))
    status = _inventory_status_from_probe(
        result,
        payload.get("status") or "passed",
        total_count=_first_int(summary.get("agent_count"), len(agents)),
        ready_count=_first_int(summary.get("healthy_agent_count"), len(agents)),
    )
    return {
        "id": "orchestrator_external_agents",
        "title": "Orchestrator External Agent Registry",
        "status": status,
        "summary": {
            "agent_count": _first_int(summary.get("agent_count"), len(agents)),
            "healthy_agent_count": _first_int(summary.get("healthy_agent_count")),
            "plugin_count": _first_int(summary.get("plugin_count"), len(agents)),
            "generic_schema": summary.get("generic_schema") or "across-agent-plugin/1.0",
        },
        "items": [
            {
                "id": item.get("plugin_id") or item.get("agent_id"),
                "agent_id": item.get("agent_id"),
                "name": item.get("display_name") or item.get("name"),
                "status": _nested(item, "health", "status") or item.get("status") or "unknown",
                "mutation_boundary": _nested(item, "trust", "mutation_boundary"),
            }
            for item in [_dict(agent) for agent in agents[:12]]
        ],
    }


def _autopilot_section(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = _dict(result.get("payload")) if "payload" in result else result
    section = _dict(_dict(payload.get("sections")).get("agent_plugin_runtime"))
    summary = _dict(section.get("summary"))
    agent_plugin_count = _first_int(summary.get("agent_plugin_count"))
    status = _inventory_status_from_probe(
        result,
        section.get("status") or payload.get("status") or "passed",
        total_count=agent_plugin_count,
        ready_count=_first_int(summary.get("ready_agent_plugin_count")),
    )
    return {
        "id": "autopilot_agent_plugin_runtime",
        "title": "Autopilot Generic Agent Plugin Runtime",
        "status": status,
        "summary": {
            "agent_plugin_count": agent_plugin_count,
            "ready_agent_plugin_count": _first_int(summary.get("ready_agent_plugin_count")),
            "dry_run_only": bool(summary.get("dry_run_only", True)),
            "generic_schema": summary.get("generic_schema") or "across-agent-plugin/1.0",
        },
        "items": _list(section.get("items")),
    }


def _context_section(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = _dict(result.get("payload")) if "payload" in result else result
    summary = _dict(payload.get("summary"))
    packs = _list(payload.get("packs"))
    status = _inventory_status_from_probe(
        result,
        payload.get("status") or "passed",
        total_count=_first_int(summary.get("agent_plugin_count")),
    )
    return {
        "id": "context_agent_packs",
        "title": "Context Agent Plugin Packs",
        "status": status,
        "summary": {
            "context_pack_count": _first_int(summary.get("context_pack_count"), len(packs)),
            "memory_count": _first_int(summary.get("memory_count")),
            "pending_count": _first_int(summary.get("pending_count")),
            "agent_plugin_count": _first_int(summary.get("agent_plugin_count")),
            "filtered_agent_plugin_id": summary.get("filtered_agent_plugin_id"),
        },
        "items": packs[:12],
    }


def _run_json_command(name: str, command: list[str], env: Mapping[str, str], *, timeout_seconds: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1, min(int(timeout_seconds), 20)),
            check=False,
            env=dict(env),
        )
    except (FileNotFoundError, PermissionError) as exc:
        return {"status": "unavailable", "source": name, "error": _redact(str(exc))}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "source": name, "error": "downstream command timed out"}
    if result.returncode != 0:
        return {"status": "failed", "source": name, "exit_code": result.returncode, "error": _redact((result.stderr or result.stdout)[:800])}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "failed", "source": name, "error": "downstream command did not return JSON"}
    return {"status": "passed", "source": name, "payload": _public_payload(payload)}


def _effective_commands(commands: Mapping[str, list[str]] | None, env: Mapping[str, str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for name, default in DEFAULT_DOWNSTREAM_COMMANDS.items():
        if commands and name in commands:
            result[name] = list(commands[name])
            continue
        env_value = str(env.get(COMMAND_ENV_KEYS[name]) or "").strip()
        result[name] = shlex.split(env_value) if env_value else _managed_default_command(default, env)
    return result


def _managed_default_command(default: list[str], env: Mapping[str, str]) -> list[str]:
    if not default:
        return []
    across_home = Path(str(env.get("ACROSS_HOME") or "~/.across")).expanduser()
    managed_binary = across_home / "bin" / default[0]
    if managed_binary.is_file() and os.access(managed_binary, os.X_OK):
        return [str(managed_binary), *default[1:]]
    return list(default)


def _status_from_probe(result: Mapping[str, Any], payload_status: Any) -> str:
    probe_status = str(result.get("status") or "").strip()
    if probe_status in {"failed", "unavailable"}:
        return probe_status
    status = str(payload_status or "unknown").strip()
    return status if status in {"passed", "attention", "failed", "unavailable", "unknown"} else "unknown"


def _inventory_status_from_probe(
    result: Mapping[str, Any],
    payload_status: Any,
    *,
    total_count: int,
    ready_count: int | None = None,
) -> str:
    status = _status_from_probe(result, payload_status)
    if status == "failed":
        return "failed"
    if str(result.get("status") or "").strip() in {"failed", "unavailable"}:
        return status
    if total_count == 0 and status in {"attention", "unavailable", "unknown"}:
        return "passed"
    if ready_count is not None and total_count > 0 and ready_count < total_count:
        return "attention"
    return status if status in {"passed", "attention", "failed"} else "passed"


def _public_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _public_payload(item) for key, item in value.items() if str(key).lower() not in {"secret", "token", "password", "api_key", "apikey"}}
    if isinstance(value, list):
        return [_public_payload(item) for item in value[:200]]
    if isinstance(value, str):
        return _redact(value)
    return value


def _redact(value: str) -> str:
    return value.replace(os.path.expanduser("~"), "~")


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first_int(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

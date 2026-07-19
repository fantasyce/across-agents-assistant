from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
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
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    source_env = dict(env or os.environ)
    effective_commands = _effective_commands(commands, source_env)
    results: dict[str, dict[str, Any]] = {}
    pending_commands: dict[str, list[str]] = {}
    for name, command in effective_commands.items():
        empty_inventory = _default_empty_inventory_result(
            name,
            command,
            source_env,
            commands_are_explicit=commands is not None,
        )
        if empty_inventory is not None:
            results[name] = empty_inventory
        else:
            pending_commands[name] = command
    # Packaged native plugin commands may need a few seconds to cold-start on
    # first use. Probe the three independent producers concurrently so a slow
    # healthy command neither becomes a false failure nor adds its latency to
    # every other producer probe.
    with ThreadPoolExecutor(max_workers=max(1, len(pending_commands))) as executor:
        futures = {
            name: executor.submit(
                _run_json_command,
                name,
                command,
                source_env,
                timeout_seconds=timeout_seconds,
            )
            for name, command in pending_commands.items()
        }
        results.update({name: future.result() for name, future in futures.items()})
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


def _default_empty_inventory_result(
    name: str,
    command: list[str],
    env: Mapping[str, str],
    *,
    commands_are_explicit: bool,
) -> dict[str, Any] | None:
    """Return the canonical optional empty state without cold-starting a frozen CLI.

    The packaged Orchestrator executable is intentionally isolated from AAA,
    but a one-file executable can take longer than the host's bounded probe
    timeout to cold-start. When the host-managed external-agent registry is
    definitely empty, launching that executable cannot reveal any additional
    health information: an empty optional registry is already a valid state.
    Explicit/custom commands and non-empty registries always run normally.
    """
    if name != "orchestrator" or commands_are_explicit:
        return None
    if str(env.get(COMMAND_ENV_KEYS["orchestrator"]) or "").strip():
        return None
    if not command:
        return None
    executable = Path(command[0]).expanduser()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return None
    registry_dir = _orchestrator_registry_dir(env)
    try:
        if registry_dir.is_dir() and any(registry_dir.glob("*.json")):
            return None
    except OSError:
        return None
    return {
        "status": "passed",
        "source": "orchestrator",
        "payload": {
            "status": "unavailable",
            "summary": {
                "agent_count": 0,
                "healthy_agent_count": 0,
                "plugin_count": 0,
                "generic_schema": "across-agent-plugin/1.0",
            },
            "agents": [],
        },
    }


def _orchestrator_registry_dir(env: Mapping[str, str]) -> Path:
    home = Path(str(env.get("HOME") or Path.home())).expanduser()
    across_home_value = str(env.get("ACROSS_HOME") or "").strip()
    across_home = _expand_home(across_home_value, home) if across_home_value else home / ".across"
    orchestrator_home_value = str(env.get("ACROSS_ORCHESTRATOR_HOME") or "").strip()
    orchestrator_home = (
        _expand_home(orchestrator_home_value, home)
        if orchestrator_home_value
        else across_home / "data" / "across-orchestrator"
    )
    return orchestrator_home / "external-agents"


def _expand_home(value: str, home: Path) -> Path:
    if value == "~":
        return home
    if value.startswith("~/"):
        return home / value[2:]
    return Path(value).expanduser()


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
    if str(result.get("status") or "").strip() in {"failed", "unavailable"}:
        return status
    # A reachable inventory with zero configured extensions is a valid empty
    # state. Some producer versions report that state as ``failed`` even
    # though the probe itself succeeded; absence of an optional extension must
    # not become a host health failure.
    if total_count == 0 and status in {"attention", "failed", "unavailable", "unknown"}:
        return "passed"
    if status == "failed":
        return "failed"
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

"""Read-only readiness snapshot for future agent workspaces.

This module describes what the host can support before any workspace mutation
exists.  It must not create worktrees or start agent runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .agent_capabilities import get_agent_capability_store
from .agent_ids import LOCAL_CLI_AGENT_IDS
from .local_agent_health import detect_local_agents
from .local_agent.status import build_operational_status
from .paths import COMPONENT_ID, component_data_home, ecosystem_home


WORKSPACE_DIR_NAME = "agent-workspaces"


SUPPORTED_FEATURES: List[Dict[str, Any]] = [
    {
        "id": "readonly_readiness_snapshot",
        "name": "Read-only readiness snapshot",
        "enabled": True,
        "mutation": False,
        "description": "Report host readiness without creating worktrees or starting agents.",
    },
    {
        "id": "local_agent_detection",
        "name": "Local agent detection",
        "enabled": True,
        "mutation": False,
        "description": "Reuse the existing lightweight local_agent_health detection boundary.",
    },
    {
        "id": "non_secret_agent_capabilities",
        "name": "Non-secret agent capabilities",
        "enabled": True,
        "mutation": False,
        "description": "Reuse the agent_capabilities export boundary without custom instructions or credentials.",
    },
    {
        "id": "workspace_root_policy",
        "name": "Workspace root policy",
        "enabled": True,
        "mutation": False,
        "description": "Reserve future agent workspaces under the Across runtime root.",
    },
    {
        "id": "isolated_git_worktrees",
        "name": "Isolated git worktrees",
        "enabled": True,
        "mutation": True,
        "description": "Create one detached worktree per selected local agent under the managed runtime root.",
    },
    {
        "id": "durable_review_lifecycle",
        "name": "Durable review lifecycle",
        "enabled": True,
        "mutation": True,
        "description": "Persist redacted events, comparison evidence, comments, cancellation, and approval state.",
    },
    {
        "id": "human_approved_promotion",
        "name": "Human-approved promotion",
        "enabled": True,
        "mutation": True,
        "description": "Validate base, files, diff, tests, risk, conflicts, evidence, and approval before applying a candidate.",
    },
]


FUTURE_ROUTES: List[Dict[str, Any]] = [
    {
        "method": "POST",
        "path": "/api/agent-workspaces",
        "enabled": True,
        "mutation": True,
        "description": "Create an isolated workspace set and launch selected local agents.",
    },
    {
        "method": "GET",
        "path": "/api/agent-workspaces/{workspace_id}/events",
        "enabled": True,
        "mutation": False,
        "description": "Read durable redacted events or stream them with SSE.",
    },
    {
        "method": "POST",
        "path": "/api/agent-workspaces/{workspace_id}/cancel",
        "enabled": True,
        "mutation": True,
        "description": "Cancel active candidate processes without touching the source repository.",
    },
    {
        "method": "POST",
        "path": "/api/agent-workspaces/{workspace_id}/comment",
        "enabled": True,
        "mutation": True,
        "description": "Send bounded human review feedback to one isolated candidate.",
    },
    {
        "method": "POST",
        "path": "/api/agent-workspaces/{workspace_id}/line-reviews",
        "enabled": True,
        "mutation": True,
        "description": "Send redacted, version-anchored line review comments to one candidate.",
    },
    {
        "method": "GET",
        "path": "/api/agent-workspaces/agent-status",
        "enabled": True,
        "mutation": False,
        "description": "Read explicit account, auth, model, provider, usage, rate-limit, and capability status.",
    },
    {
        "method": "POST",
        "path": "/api/agent-workspaces/{workspace_id}/promote",
        "enabled": True,
        "mutation": True,
        "description": "Apply a validated candidate only after explicit human approval.",
    },
    {
        "method": "DELETE",
        "path": "/api/agent-workspaces/{workspace_id}",
        "enabled": True,
        "mutation": True,
        "description": "Remove retained isolated worktrees after all candidates stop.",
    },
]


def agent_workspace_root() -> Path:
    """Return the reserved workspace root path without creating it."""
    return component_data_home(COMPONENT_ID) / WORKSPACE_DIR_NAME


def build_agent_workspace_readiness(
    *,
    refresh: bool = False,
    repo_root: Optional[str] = None,
    selected_agent_ids: Optional[Sequence[str]] = None,
    repo_access: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a non-secret, read-only readiness snapshot."""
    workspace_root = agent_workspace_root()
    across_home = ecosystem_home()
    local_agent_health = detect_local_agents(force=refresh)
    host_registry = _host_capability_registry()
    host_agents = {
        str(agent.get("agent_id")): agent
        for agent in host_registry.get("agents", [])
        if isinstance(agent, dict) and agent.get("agent_id")
    }

    local_agents = [
        _public_local_agent(agent_id, local_agent_health.get(agent_id) or {}, host_agents.get(agent_id) or {})
        for agent_id in LOCAL_CLI_AGENT_IDS
    ]
    available_local_agents = [
        agent
        for agent in local_agents
        if agent.get("available") is True
    ]
    selected_ids = _dedupe_strings(selected_agent_ids)
    selected_missing = [
        agent_id
        for agent_id in selected_ids
        if not any(agent.get("agent_id") == agent_id and agent.get("available") for agent in local_agents)
    ]
    git_available = shutil.which("git") is not None
    repository = _repository_readiness(repo_root, repo_access=repo_access)
    missing_prerequisites = _missing_prerequisites(
        workspace_root=workspace_root,
        across_home=across_home,
        local_agents=local_agents,
        available_local_agents=available_local_agents,
    )
    if not git_available:
        missing_prerequisites.append(
            {
                "id": "git_unavailable",
                "scope": "workspace_isolation",
                "severity": "error",
                "required_for_future_mutation": True,
                "message": "git is required for isolated agent workspaces.",
            }
        )
    for agent_id in selected_missing:
        missing_prerequisites.append(
            {
                "id": f"selected_agent_{agent_id}_unavailable",
                "scope": "local_agents",
                "agent_id": agent_id,
                "severity": "error",
                "required_for_future_mutation": True,
                "message": "A selected local agent is unavailable.",
            }
        )
    if repository and not repository.get("ready"):
        missing_prerequisites.append(
            {
                "id": str(repository.get("error_code") or "repository_not_ready"),
                "scope": "repository",
                "severity": "error",
                "required_for_future_mutation": True,
                "message": str(repository.get("message") or "Repository is not ready for isolated workspaces."),
            }
        )
    blocking_missing = [
        item
        for item in missing_prerequisites
        if item.get("required_for_future_mutation") is True and item.get("severity") == "error"
    ]

    missing_prerequisite_ids = _missing_prerequisite_ids(missing_prerequisites)
    workspace_creation_missing = [
        str(item.get("id"))
        for item in blocking_missing
        if item.get("id")
    ]

    can_create = not blocking_missing
    status = "blocked" if blocking_missing else ("ready" if repository and repository.get("ready") else "partial")

    return {
        "schema_version": "agent-workspace-readiness/1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "readiness": "ready" if status == "ready" else ("blocked" if status == "blocked" else "limited"),
        "readonly": True,
        "mutation_enabled": can_create,
        "repo_root": repository.get("repo_root") if repository else None,
        "repository": repository,
        "prompt": None,
        "prompt_required_for_creation": True,
        "selected_agent_ids": selected_ids,
        "execution_strategy": "parallel_worktrees",
        "workspace": {
            "root": str(workspace_root),
            "exists": workspace_root.exists(),
            "is_dir": workspace_root.is_dir(),
            "under_across_home": _is_relative_to(workspace_root, across_home),
            "across_home": str(across_home),
            "creation_enabled": can_create,
        },
        "workspace_isolation": {
            "status": "ready" if can_create else "blocked",
            "mode": "detached_git_worktrees",
            "supports_git_worktree": git_available,
            "can_create_isolated_workspaces": can_create,
            "missing_prerequisites": workspace_creation_missing,
            "reason": None if can_create else "One or more host or request prerequisites are missing.",
        },
        "agents": [_agent_workspace_readiness(agent) for agent in local_agents],
        "agent_operational_status": [agent["operational_status"] for agent in local_agents],
        "local_agents": local_agents,
        "available_local_agents": available_local_agents,
        "supported_features": [dict(feature) for feature in SUPPORTED_FEATURES],
        "missing_prerequisites": missing_prerequisites,
        "missing_prerequisite_ids": missing_prerequisite_ids,
        "unsupported_features": ["source_mutation_without_approval", "raw_transcript_persistence", "credential_persistence"],
        "routes": {
            "create": "/api/agent-workspaces",
            "events": "/api/agent-workspaces/{workspace_id}/events",
            "diff": "/api/agent-workspaces/{workspace_id}/comparison",
            "evidence": "/api/agent-workspaces/{workspace_id}/comparison",
            "cancel": "/api/agent-workspaces/{workspace_id}/cancel",
            "comment": "/api/agent-workspaces/{workspace_id}/comment",
            "line_review": "/api/agent-workspaces/{workspace_id}/line-reviews",
            "agent_status": "/api/agent-workspaces/agent-status",
            "select": "/api/agent-workspaces/{workspace_id}/select",
            "promote": "/api/agent-workspaces/{workspace_id}/promote",
        },
        "future_routes": [dict(route) for route in FUTURE_ROUTES],
        "security": {
            "secrets_included": False,
            "custom_instructions_included": False,
            "install_paths_included": False,
            "credential_fields_redacted": True,
            "prompt_included": False,
            "transcripts_included": False,
        },
        "repository_access_contract": _repository_access_contract(),
    }


def _repository_readiness(
    repo_root: Optional[str],
    *,
    repo_access: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not str(repo_root or "").strip():
        return None
    try:
        from .agent_workspaces import inspect_git_repository

        repository = inspect_git_repository(str(repo_root), repo_access=repo_access)
    except Exception as exc:
        code = getattr(exc, "code", "repository_not_ready")
        message = getattr(exc, "message", "Repository is not ready for isolated workspaces.")
        return {
            "repo_root": None,
            "ready": False,
            "error_code": str(code),
            "message": str(message),
        }
    return {
        "repo_root": repository["repo_root"],
        "base_sha": repository["base_sha"],
        "branch": repository["branch"],
        "clean": repository["clean"],
        "ready": bool(repository["clean"]),
        "error_code": None if repository["clean"] else "source_not_clean",
        "message": None if repository["clean"] else "Source repository must be clean before workspace creation.",
        "access": repository.get("access"),
    }


def _host_capability_registry() -> Dict[str, Any]:
    store = get_agent_capability_store()
    native_states = store.get_native_skill_states()
    native_skills_by_agent = {
        agent_id: [
            skill
            for skill in _iter_native_skills(state)
            if isinstance(skill, dict)
        ]
        for agent_id, state in native_states.items()
        if isinstance(state, dict)
    }
    return store.build_host_registry(
        tool_schemas=[],
        native_skills_by_agent=native_skills_by_agent,
    )


def _iter_native_skills(state: Mapping[str, Any]) -> Iterable[Any]:
    skills = state.get("skills")
    return skills if isinstance(skills, list) else []


def _public_local_agent(
    agent_id: str,
    health: Mapping[str, Any],
    capability: Mapping[str, Any],
) -> Dict[str, Any]:
    result = {
        "agent_id": agent_id,
        "display_name": str(
            health.get("display_name")
            or capability.get("display_name")
            or agent_id
        ),
        "agent_type": "local_cli",
        "found": bool(health.get("found")),
        "available": bool(health.get("available")),
        "status": str(health.get("status") or "unknown"),
        "version": _string_or_none(health.get("version")),
        "supported_workspace_modes": ["parallel_git_worktree"] if health.get("available") else [],
        "missing_prerequisites": [] if health.get("available") else [f"local_agent_{agent_id}_unavailable"],
        "reason": None if health.get("available") else str(health.get("status") or "unavailable"),
        "capabilities": _dedupe_strings(capability.get("capabilities")),
        "configured_skill_ids": _dedupe_strings(capability.get("configured_skill_ids")),
        "configured_skill_names": _dedupe_strings(capability.get("configured_skill_names")),
        "enabled_plugin_ids": _dedupe_strings(capability.get("enabled_plugin_ids")),
        "enabled_tool_names": _dedupe_strings(capability.get("enabled_tool_names")),
        "native_skill_ids": _dedupe_strings(capability.get("native_skill_ids")),
        "strict_tool_scope": bool(capability.get("strict_tool_scope", False)),
        "warnings": _dedupe_strings(capability.get("warnings")),
    }
    result["operational_status"] = build_operational_status(agent_id, health, capability)
    return result


def _missing_prerequisites(
    *,
    workspace_root: Path,
    across_home: Path,
    local_agents: List[Dict[str, Any]],
    available_local_agents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    missing: List[Dict[str, Any]] = []
    if not _is_relative_to(workspace_root, across_home):
        missing.append(
            {
                "id": "workspace_root_outside_across_home",
                "scope": "workspace",
                "severity": "error",
                "required_for_future_mutation": True,
                "message": "Workspace root must stay under the Across runtime home.",
            }
        )
    if workspace_root.exists() and not workspace_root.is_dir():
        missing.append(
            {
                "id": "workspace_root_not_directory",
                "scope": "workspace",
                "severity": "error",
                "required_for_future_mutation": True,
                "message": "Workspace root path exists but is not a directory.",
            }
        )
    elif not workspace_root.exists():
        missing.append(
            {
                "id": "workspace_root_missing",
                "scope": "workspace",
                "severity": "info",
                "required_for_future_mutation": False,
                "message": "Workspace root has not been created yet; this readiness route is read-only.",
            }
        )
    if not available_local_agents:
        missing.append(
            {
                "id": "no_available_local_agents",
                "scope": "local_agents",
                "severity": "error",
                "required_for_future_mutation": True,
                "message": "At least one lightweight-detected local agent is required before agent workspaces can run.",
            }
        )
    for agent in local_agents:
        if agent.get("available") is True:
            continue
        missing.append(
            {
                "id": f"local_agent_{agent.get('agent_id')}_unavailable",
                "scope": "local_agents",
                "agent_id": agent.get("agent_id"),
                "severity": "warning",
                "required_for_future_mutation": False,
                "status": agent.get("status") or "unknown",
                "message": "Local agent is not available according to lightweight detection.",
            }
        )
    return missing


def _agent_workspace_readiness(agent: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "agent_id": agent.get("agent_id"),
        "display_name": agent.get("display_name"),
        "agent_type": agent.get("agent_type") or "local_cli",
        "status": "ready" if agent.get("available") is True else "unavailable",
        "available": agent.get("available") is True,
        "supported_workspace_modes": _dedupe_strings(agent.get("supported_workspace_modes")),
        "missing_prerequisites": _dedupe_strings(agent.get("missing_prerequisites")),
        "reason": agent.get("reason"),
        "operational_status": agent.get("operational_status"),
    }


def _repository_access_contract() -> Dict[str, Any]:
    return {
        "schema_version": "agent-workspace-repository-access/1.0",
        "request_field": "repo_access",
        "mode_values": ["implicit", "security_scoped"],
        "swift_responsibilities": [
            "resolve_stale_bookmark",
            "start_accessing_before_request",
            "keep_access_active_for_workspace_lifecycle",
            "stop_accessing_after_terminal_cleanup",
        ],
        "accepted_metadata": ["mode", "security_scope_active", "grant_id"],
        "bookmark_data_accepted": False,
        "credentials_accepted": False,
        "command_timeout_policy": {
            "idle_timeout_seconds": 30,
            "default_total_timeout_seconds": 30,
            "idle_resets_on_output_activity": True,
        },
        "failure_codes": [
            "repository_access_denied",
            "repository_access_not_authorized",
            "repository_access_timeout",
            "command_idle_timeout",
            "command_total_timeout",
        ],
    }


def _missing_prerequisite_ids(items: Iterable[Mapping[str, Any]]) -> List[str]:
    return sorted(_dedupe_strings(item.get("id") for item in items if isinstance(item, Mapping)))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _dedupe_strings(values: Any) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values or []:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _string_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None

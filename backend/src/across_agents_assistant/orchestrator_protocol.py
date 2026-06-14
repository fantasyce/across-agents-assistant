from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence

from .orchestrator_release_evidence import evaluate_app_grade_quality

_TASK_SUBMIT_KEYS = {
    "goal": "goal",
    "project_root": "projectRoot",
    "deliverables": "deliverables",
    "agent": "agent",
    "strict_dependency": "strictDependency",
    "task_types": "taskTypes",
    "subtasks": "subtasks",
    "run_label": "runLabel",
    "allowed_subtask_agents": "allowedSubtaskAgents",
}


def normalize_task_types(task_types: Optional[Sequence[Any]]) -> List[str]:
    """Normalize a protocol-level task-type list from either AA or external payloads."""
    clean: List[str] = []
    seen: set[str] = set()
    for item in task_types or []:
        value = str(item or "").strip().lower()
        if not value or value in seen:
            continue
        clean.append(value)
        seen.add(value)
    return clean


def normalize_external_agent_ids(agent_ids: Optional[Sequence[Any]]) -> List[str]:
    """Normalize allowed agent ids for Orchestrator protocol submission payloads."""
    clean: List[str] = []
    seen: set[str] = set()
    for item in agent_ids or []:
        value = str(item or "").strip().lower()
        if not value or value in seen or value.endswith("-agent"):
            continue
        clean.append(value)
        seen.add(value)
    return clean


def build_external_task_submission_payload(
    *,
    goal: str,
    project_root: str,
    deliverables: Optional[Sequence[str]] = None,
    agent: str = "demo",
    strict_dependency: bool = False,
    task_types: Optional[Sequence[Any]] = None,
    subtasks: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the explicit HTTP/CLI payload for submitting a generic external task."""
    payload: Dict[str, Any] = {
        _TASK_SUBMIT_KEYS["goal"]: goal,
        _TASK_SUBMIT_KEYS["project_root"]: project_root,
        _TASK_SUBMIT_KEYS["agent"]: agent,
        _TASK_SUBMIT_KEYS["deliverables"]: list(deliverables or ["README.md"]),
        _TASK_SUBMIT_KEYS["strict_dependency"]: bool(strict_dependency),
    }
    clean_task_types = normalize_task_types(task_types)
    if clean_task_types:
        payload[_TASK_SUBMIT_KEYS["task_types"]] = clean_task_types
    if subtasks:
        payload[_TASK_SUBMIT_KEYS["subtasks"]] = list(subtasks)
    return payload


def build_external_release_e2e_submission_payload(
    *,
    project_root: str,
    run_label: Optional[str] = None,
    allowed_subtask_agents: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Build the explicit HTTP/CLI payload for submitting Release-E2E tasks."""
    payload: Dict[str, Any] = {
        _TASK_SUBMIT_KEYS["project_root"]: project_root,
    }
    if run_label:
        payload[_TASK_SUBMIT_KEYS["run_label"]] = run_label
    clean_agents = normalize_external_agent_ids(allowed_subtask_agents)
    if clean_agents:
        payload[_TASK_SUBMIT_KEYS["allowed_subtask_agents"]] = clean_agents
    return payload


DEFAULT_APP_GRADE_EXECUTOR_AGENTS = ["openclaw", "hermes", "claude", "deepseek", "minimax"]


def _public_agent_card(card: Any) -> Dict[str, Any]:
    if not isinstance(card, dict):
        return {}
    return {
        "name": card.get("name"),
        "version": card.get("version"),
        "capabilities": card.get("capabilities"),
        "protocols": card.get("protocols"),
    }


def _status_progress(status: str) -> float:
    value = str(status or "pending").lower()
    if value == "completed":
        return 1.0
    if value == "running":
        return 0.5
    if value in {"failed", "cancelled"}:
        return 1.0
    return 0.0


def _app_status(status: str) -> str:
    value = str(status or "pending").lower()
    if value in {"pending", "running", "completed", "failed", "cancelled", "paused"}:
        return value
    return "pending"


def _clean_task_types(task_types: Optional[List[Any]]) -> List[str]:
    # Backward-compatible internal name kept for existing call sites.
    return normalize_task_types(task_types)


def _clean_agent_ids(agent_ids: Optional[Sequence[Any]]) -> List[str]:
    # Backward-compatible internal name kept for existing call sites.
    return normalize_external_agent_ids(agent_ids)


def _subtask_to_app(subtask: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    status = _app_status(str(subtask.get("status") or "pending"))
    return {
        "subtask_id": str(subtask.get("subtask_id") or subtask.get("id") or subtask.get("path") or ""),
        "description": str(subtask.get("goal") or subtask.get("description") or ""),
        "agent_id": str(subtask.get("agent") or subtask.get("agent_id") or "app-grade"),
        "priority": int(subtask.get("priority") or 1),
        "status": status,
        "progress": _status_progress(status),
        "dependencies": list(subtask.get("dependencies") or []),
        "output_file": subtask.get("path") or subtask.get("output_file"),
        "duration": subtask.get("duration"),
        "error_message": subtask.get("error"),
        "fix_plan": None,
        "wave_number": int(subtask.get("wave") or subtask.get("wave_number") or 1),
        "owner_decision": None,
        "waiting_on_dependencies": [],
        "blocked_reason": None,
        "running_for_seconds": None,
        "contract": {
            "task_id": task_id,
            "required_artifact": subtask.get("path"),
            "source": "across_orchestrator",
        },
    }


def _waves_from_subtasks(subtasks: List[Dict[str, Any]], task_id: str) -> List[Dict[str, Any]]:
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for subtask in subtasks:
        grouped.setdefault(int(subtask.get("wave_number") or 1), []).append(subtask)
    waves: List[Dict[str, Any]] = []
    for wave_number in sorted(grouped):
        items = grouped[wave_number]
        statuses = {item.get("status") for item in items}
        if statuses == {"completed"}:
            status = "completed"
            governance_status = "approved"
        elif "running" in statuses:
            status = "running"
            governance_status = "pending"
        elif "failed" in statuses:
            status = "failed"
            governance_status = "blocked"
        else:
            status = "pending"
            governance_status = "pending"
        waves.append(
            {
                "wave_id": f"external-wave-{task_id}-{wave_number}",
                "wave_number": wave_number,
                "subtasks": items,
                "status": status,
                "is_blocked": governance_status == "blocked",
                "governance_status": governance_status,
                "blocked_by_wave": None,
                "is_revalidating": False,
                "owner_decision": None,
            }
        )
    return waves


def _required_files(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> List[str]:
    app_grade = (evidence or {}).get("app_grade") if isinstance(evidence, dict) else None
    if isinstance(app_grade, dict) and app_grade.get("required_files"):
        return [str(item) for item in app_grade.get("required_files") or []]
    contract = task.get("contract") or {}
    return [str(item) for item in contract.get("requiredArtifacts") or task.get("deliverables") or []]


def _artifact_rows(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if evidence and isinstance(evidence.get("artifacts"), list):
        rows = []
        for item in evidence.get("artifacts") or []:
            path = str(item.get("path") or "")
            rows.append(
                {
                    "artifact_id": f"external-{path}",
                    "name": path,
                    "path": str(Path(task.get("project_root") or task.get("project_dir") or "") / path) if path else "",
                    "path_hint": path,
                    "status": "accepted" if item.get("present") else "missing",
                    "size": item.get("size"),
                    "sha256": item.get("sha256"),
                    "source": "across_orchestrator",
                }
            )
        return rows
    return [
        {
            "artifact_id": f"external-{path}",
            "name": path,
            "path": str(Path(task.get("project_root") or "") / path),
            "path_hint": path,
            "status": "expected",
            "source": "across_orchestrator",
        }
        for path in _required_files(task, evidence)
    ]


def _external_app_grade_executors(task: Dict[str, Any]) -> List[str]:
    candidates: List[Any] = []
    metadata = task.get("metadata")
    if isinstance(metadata, dict):
        request = metadata.get("app_grade_request")
        if isinstance(request, dict):
            request_body = request.get("request")
            if isinstance(request_body, dict):
                candidates.extend(request_body.get("executor_agents") or [])
    contract = task.get("contract")
    if isinstance(contract, dict):
        candidates.extend(contract.get("executor_agents") or [])
    for subtask in task.get("subtasks") or []:
        if isinstance(subtask, dict):
            candidates.append(subtask.get("agent") or subtask.get("agent_id"))
    clean: List[str] = []
    for item in candidates:
        value = str(item or "").strip().lower()
        if value and value not in clean and value != "app-grade" and not value.endswith("-agent"):
            clean.append(value)
    return clean or list(DEFAULT_APP_GRADE_EXECUTOR_AGENTS)


def _legacy_role_from_agent(agent: str) -> Optional[str]:
    value = str(agent or "").strip().lower()
    if value.endswith("-agent"):
        return value.removesuffix("-agent")
    return None


def _is_app_grade(task: Dict[str, Any]) -> bool:
    return (task.get("contract") or {}).get("engine") == "app_grade_release_e2e"


def _normalize_external_task_for_app(task: Dict[str, Any]) -> Dict[str, Any]:
    if not _is_app_grade(task):
        return task
    normalized = dict(task)
    normalized["subtasks"] = [dict(item) for item in task.get("subtasks") or [] if isinstance(item, dict)]
    executors = _external_app_grade_executors(normalized)
    agent = str(normalized.get("agent") or "")
    if agent == "app-grade" or agent.endswith("-agent"):
        normalized["agent"] = executors[0]
    for index, subtask in enumerate(normalized["subtasks"]):
        role = _legacy_role_from_agent(str(subtask.get("agent") or subtask.get("agent_id") or ""))
        if not role:
            continue
        subtask.setdefault("capability_role", role)
        subtask["agent"] = executors[index % len(executors)]
    return normalized


def _external_metadata(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    task_metadata = task.get("metadata")
    if isinstance(task_metadata, dict):
        metadata.update(task_metadata)
    contract = task.get("contract")
    if isinstance(contract, dict):
        for key in ("task_types", "delivery_mode"):
            if key in contract and key not in metadata:
                metadata[key] = contract[key]
    if isinstance(evidence, dict):
        evidence_metadata = evidence.get("metadata")
        if isinstance(evidence_metadata, dict):
            metadata.update(evidence_metadata)
        for key in ("task_types", "delivery_mode"):
            if key in evidence and key not in metadata:
                metadata[key] = evidence[key]
    return metadata


def _external_task_types(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> List[str]:
    metadata = _external_metadata(task, evidence)
    task_types = _clean_task_types(metadata.get("task_types") if isinstance(metadata.get("task_types"), list) else None)
    if task_types:
        return task_types
    if _is_app_grade(task):
        return ["functional", "artifact"]
    return ["artifact"]


def _external_delivery_mode(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> str:
    metadata = _external_metadata(task, evidence)
    explicit = str(metadata.get("delivery_mode") or "").strip().lower()
    if explicit:
        return explicit
    task_types = _external_task_types(task, evidence)
    if len(task_types) > 1:
        return "composite"
    return task_types[0] if task_types else "artifact"


def external_task_to_summary(task: Dict[str, Any]) -> Dict[str, Any]:
    task = _normalize_external_task_for_app(task)
    subtasks = task.get("subtasks") or []
    completed = sum(1 for item in subtasks if item.get("status") == "completed")
    total = len(subtasks)
    status = _app_status(str(task.get("status") or "pending"))
    return {
        "task_id": str(task.get("task_id") or ""),
        "description": str(task.get("goal") or task.get("description") or ""),
        "status": status,
        "external_task": True,
        "progress": completed / total if total else _status_progress(status),
        "completed_count": completed,
        "total_count": total,
        "created_at": float(task.get("created_at") or time.time()),
        "updated_at": float(task.get("updated_at") or time.time()),
        "project_dir": task.get("project_root") or task.get("project_dir"),
        "owner_agent": task.get("agent") or "app-grade",
        "delivery_mode": _external_delivery_mode(task),
    }


def external_task_to_app_info(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    task = _normalize_external_task_for_app(task)
    task_id = str(task.get("task_id") or "")
    status = _app_status(str(task.get("status") or "pending"))
    subtasks = [_subtask_to_app(item, task_id) for item in task.get("subtasks") or []]
    completed = sum(1 for item in subtasks if item.get("status") == "completed")
    total = len(subtasks)
    required_files = _required_files(task, evidence)
    quality = (evidence and (evidence.get("quality") or evidence.get("app_grade") or {})) or {"status": status}
    if isinstance(quality, dict) and not quality.get("quality_report"):
        from .orchestrator_release_evidence import evaluate_app_grade_quality
        quality = evaluate_app_grade_quality(
            evidence or {"status": status, "contract": task.get("contract") or {}}
        )
    artifacts = _artifact_rows(task, evidence)
    task_types = _external_task_types(task, evidence)
    delivery_mode = _external_delivery_mode(task, evidence)
    return {
        "task_id": task_id,
        "description": str(task.get("goal") or task.get("description") or ""),
        "status": status,
        "external_task": True,
        "task_types": task_types,
        "delivery_mode": delivery_mode,
        "owner_delivery_contract": task.get("contract") or {},
        "owner_agent": task.get("agent") or "app-grade",
        "allowed_subtask_agents": sorted({str(item.get("agent") or "app-grade") for item in task.get("subtasks") or []}),
        "project_dir": task.get("project_root") or task.get("project_dir"),
        "subtasks": subtasks,
        "waves": _waves_from_subtasks(subtasks, task_id),
        "artifacts": artifacts,
        "artifact_versions": {item["name"]: 1 for item in artifacts if item.get("name")},
        "acceptance_records": [],
        "owner_session_id": None,
        "last_owner_decision": {
            "decision": "external_orchestrator",
            "delivery_quality": quality,
        },
        "can_handle_directly": False,
        "direct_response": None,
        "progress": completed / total if total else _status_progress(status),
        "completed_count": completed,
        "total_count": total,
        "created_at": float(task.get("created_at") or time.time()),
        "updated_at": float(task.get("updated_at") or time.time()),
        "error": task.get("error"),
        "requirement_manifest": {
            "task_id": task_id,
            "project_dir": task.get("project_root") or task.get("project_dir"),
            "deliverables": [
                {"path": path, "status": "accepted" if status == "completed" else "assigned"}
                for path in required_files
            ],
        },
        "quality_health": {
            "manifest_total": len(required_files),
            "manifest_accepted": len(required_files) if quality["status"] == "passed" else 0,
            "quality_gate": quality["status"],
            "delivery_quality": quality["status"],
            "delivery_quality_report": quality,
            "orchestration_health": "passed" if status == "completed" else status,
        },
        "delivery_report": {
            "status": quality["status"],
            "source": "across_orchestrator",
            "required_files": required_files,
            "checks": quality.get("checks", {}),
            "failures": quality.get("failures", []),
        },
        "observability": {
            "orchestrator_plugin": {
                "implementation": "external",
                "source": "across_orchestrator",
            }
        },
    }

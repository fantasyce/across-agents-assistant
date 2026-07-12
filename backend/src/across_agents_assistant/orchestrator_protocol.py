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
    "agent_adapters": "agentAdapters",
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
    agent_adapters: Optional[Dict[str, Dict[str, Any]]] = None,
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
    if agent_adapters:
        payload[_TASK_SUBMIT_KEYS["agent_adapters"]] = dict(agent_adapters)
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
    return normalize_task_types(task_types)


def _clean_agent_ids(agent_ids: Optional[Sequence[Any]]) -> List[str]:
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


def _format_artifact_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _artifact_size_label(raw_size: Any, full_path: str) -> str:
    if isinstance(raw_size, bool):
        size_bytes: Optional[int] = None
    elif isinstance(raw_size, (int, float)) and raw_size >= 0:
        size_bytes = int(raw_size)
    elif isinstance(raw_size, str):
        clean = raw_size.strip()
        if not clean:
            size_bytes = None
        elif clean.isdigit():
            size_bytes = int(clean)
        else:
            return clean
    else:
        size_bytes = None

    if size_bytes is None and full_path:
        try:
            candidate = Path(full_path)
            if candidate.is_file():
                size_bytes = candidate.stat().st_size
        except OSError:
            size_bytes = None

    return _format_artifact_size(size_bytes) if size_bytes is not None else "0 B"


def _artifact_rows(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    project_root = str(task.get("project_root") or task.get("project_dir") or "")
    if evidence and isinstance(evidence.get("artifacts"), list):
        rows = []
        for item in evidence.get("artifacts") or []:
            path = str(item.get("path") or "")
            full_path = str(Path(project_root) / path) if path else ""
            file_size = _artifact_size_label(item.get("size"), full_path)
            rows.append(
                {
                    "artifact_id": f"external-{path}",
                    "id": f"external-{path}",
                    "name": path,
                    "file_name": path,
                    "path": full_path,
                    "file_path": full_path,
                    "content_ref": full_path,
                    "normalized_content_ref": full_path,
                    "path_hint": path,
                    "status": "accepted" if item.get("present") else "missing",
                    "size": item.get("size"),
                    "file_size": file_size,
                    "sha256": item.get("sha256"),
                    "source": "across_orchestrator",
                }
            )
        return rows
    return [
        {
            "artifact_id": f"external-{path}",
            "id": f"external-{path}",
            "name": path,
            "file_name": path,
            "path": str(Path(project_root) / path),
            "file_path": str(Path(project_root) / path),
            "content_ref": str(Path(project_root) / path),
            "normalized_content_ref": str(Path(project_root) / path),
            "path_hint": path,
            "status": "expected",
            "file_size": _artifact_size_label(None, str(Path(project_root) / path)),
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


def _capability_role_from_agent_id(agent: str) -> Optional[str]:
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
        role = _capability_role_from_agent_id(str(subtask.get("agent") or subtask.get("agent_id") or ""))
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


def _external_quality_summary(
    task: Dict[str, Any],
    *,
    evidence: Optional[Dict[str, Any]],
    status: str,
    required_files: List[str],
    artifacts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    quality = (evidence and (evidence.get("quality") or evidence.get("app_grade") or {})) or {}
    if isinstance(quality, dict) and quality.get("quality_report"):
        return quality
    if _is_app_grade(task):
        return evaluate_app_grade_quality(
            evidence or {"status": status, "contract": task.get("contract") or {}}
        )

    artifact_statuses = {
        str(item.get("name") or item.get("path_hint") or item.get("path") or ""): str(item.get("status") or "")
        for item in artifacts
        if item.get("name") or item.get("path_hint") or item.get("path")
    }
    missing_files = [
        path
        for path in required_files
        if artifact_statuses.get(path) == "missing"
        or (artifact_statuses.get(path) not in {"accepted", "expected"} and status == "completed")
    ]
    passed = status == "completed" and not missing_files
    return {
        "status": "passed" if passed else ("failed" if status == "failed" else status),
        "quality_gate": "passed" if passed else ("failed" if status == "failed" else status),
        "delivery_quality": "passed" if passed else ("failed" if status == "failed" else status),
        "quality_score": 100 if passed else 0,
        "checks": {
            "artifact_integrity": passed,
        },
        "failures": [f"{path} is missing" for path in missing_files],
        "produced_files": [
            path
            for path in required_files
            if path not in missing_files and status == "completed"
        ],
        "required_files": required_files,
        "gate_results": {},
    }


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
    artifacts = _artifact_rows(task, evidence)
    quality = _external_quality_summary(
        task,
        evidence=evidence,
        status=status,
        required_files=required_files,
        artifacts=artifacts,
    )
    task_types = _external_task_types(task, evidence)
    delivery_mode = _external_delivery_mode(task, evidence)
    acceptance_records = _external_acceptance_records(
        task=task,
        task_id=task_id,
        status=status,
        required_files=required_files,
        artifacts=artifacts,
        quality=quality,
    )
    quality_status = str(quality.get("status") or quality.get("quality_gate") or status)
    quality_failures = [str(item) for item in quality.get("failures") or [] if str(item).strip()]
    missing_required = [
        str(item.get("name") or item.get("path_hint") or item.get("path") or "")
        for item in artifacts
        if str(item.get("status") or "").lower() == "missing"
    ]
    accepted_required = sum(
        1 for item in artifacts
        if str(item.get("status") or "").lower() == "accepted"
    )
    quality_report = quality.get("quality_report") or {
        "quality_gate": quality_status,
        "can_complete": quality_status == "passed" and not quality_failures and not missing_required,
        "generated_quality_score": quality.get("quality_score"),
        "final_quality_score": quality.get("quality_score"),
        "required_failed_count": len(quality_failures) + len(missing_required),
        "manual_required_count": 0,
        "skipped_required_count": 0,
    }
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
        "acceptance_records": acceptance_records,
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
            "manifest_required": len(required_files),
            "manifest_accepted": len(required_files) if quality_status == "passed" else 0,
            "manifest_missing": len(missing_required),
            "quality_gate": quality_status,
            "delivery_quality": quality_status,
            "delivery_quality_report": {
                "missing_required": missing_required,
                "failed_constraints": quality_failures,
            },
            "orchestration_health": "passed" if status == "completed" else status,
        },
        "delivery_report": {
            "quality_gate": quality_status,
            "final_status": status,
            "summary": (
                "All required deliverables were produced and accepted."
                if quality_status == "passed"
                else "Required delivery checks still need attention."
            ),
            "required_total": len(required_files),
            "accepted_total": accepted_required,
            "missing_required": missing_required,
            "failed_constraints": quality_failures,
            "quality_report": quality_report,
            "status": quality_status,
            "source": "across_orchestrator",
            "required_files": required_files,
            "checks": quality.get("checks", {}),
            "failures": quality_failures,
        },
        "observability": {
            "orchestrator_plugin": {
                "implementation": "external",
                "source": "across_orchestrator",
            }
        },
    }


def _external_acceptance_records(
    *,
    task: Dict[str, Any],
    task_id: str,
    status: str,
    required_files: List[str],
    artifacts: List[Dict[str, Any]],
    quality: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if status not in {"completed", "completed_with_failures", "failed"}:
        return []
    if not required_files and not artifacts:
        return []

    produced = {
        str(item.get("name") or item.get("path_hint") or item.get("file_name") or "").strip()
        for item in artifacts
        if item.get("name") or item.get("path_hint") or item.get("file_name")
    }
    missing = [path for path in required_files if path not in produced]
    failures = [str(item) for item in quality.get("failures") or [] if str(item).strip()]
    passed = quality.get("status") == "passed" and not missing and not failures
    artifact_ids = [
        str(item.get("artifact_id") or item.get("id") or item.get("name") or "")
        for item in artifacts
        if item.get("artifact_id") or item.get("id") or item.get("name")
    ]
    artifact_ids = list(dict.fromkeys(artifact_ids))
    return [
        {
            "acceptance_id": f"acc-external-{task_id}",
            "task_id": task_id,
            "level": "task",
            "decision": "approve" if passed else "fix",
            "deterministic_passed": passed,
            "judge_passed": passed,
            "subtask_id": None,
            "wave_number": None,
            "failed_checks": failures,
            "missing_artifacts": missing,
            "feedback": "External Orchestrator delivery quality passed." if passed else "External Orchestrator delivery quality needs attention.",
            "root_cause_scope": "unknown",
            "root_cause_wave": None,
            "root_cause_artifact_ids": artifact_ids,
            "recommended_action": "approve" if passed else "fix",
            "preferred_agent": task.get("agent") or "app-grade",
            "owner_session_id": None,
            "created_at": _external_acceptance_created_at(task),
        }
    ]


def _external_acceptance_created_at(task: Dict[str, Any]) -> Optional[float]:
    for key in ("updated_at", "created_at"):
        value = task.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None

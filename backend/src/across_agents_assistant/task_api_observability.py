from __future__ import annotations

from typing import Any, Dict, List, Optional


def path_hints_from_required(value: Any) -> List[str]:
    paths: List[str] = []
    if not isinstance(value, list):
        return paths
    for item in value:
        if isinstance(item, str):
            hint = item.strip()
        elif isinstance(item, dict):
            hint = str(
                item.get("path_hint")
                or item.get("path")
                or item.get("name")
                or ""
            ).strip()
        else:
            hint = ""
        if hint and hint not in paths:
            paths.append(hint)
    return paths


def probe_types_from_payload(payload: Dict[str, Any]) -> List[str]:
    delivery_quality = (
        (payload.get("quality_health") or {}).get("delivery_quality_report")
        or (payload.get("last_owner_decision") or {}).get("delivery_quality")
        or {}
    )
    quality_report = delivery_quality.get("quality_report") or {}
    probes: List[Dict[str, Any]] = []
    for item in delivery_quality.get("probe_results") or []:
        if isinstance(item, dict):
            probes.append(item)
    for item in quality_report.get("gate_results") or []:
        if isinstance(item, dict):
            probes.append(item)
    probe_types: List[str] = []
    for item in probes:
        probe_type = str(
            item.get("probe_type")
            or item.get("adapter_id")
            or item.get("gate_id")
            or item.get("id")
            or ""
        ).strip()
        if probe_type and probe_type not in probe_types:
            probe_types.append(probe_type)
    return probe_types


def expected_files_from_payload(payload: Dict[str, Any]) -> List[str]:
    delivery_quality = (
        (payload.get("quality_health") or {}).get("delivery_quality_report")
        or (payload.get("last_owner_decision") or {}).get("delivery_quality")
        or {}
    )
    paths = path_hints_from_required(delivery_quality.get("produced_required"))
    if paths:
        return paths
    contract = payload.get("owner_delivery_contract") or {}
    return path_hints_from_required(contract.get("deliverables"))


def read_obj_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def status_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def extract_quality_report_from_decision(decision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(decision, dict):
        return {}
    delivery_quality = decision.get("delivery_quality")
    if not isinstance(delivery_quality, dict):
        return {}
    report = delivery_quality.get("quality_report")
    return report if isinstance(report, dict) else {}


def extract_agent_mix_from_gates(gate_results: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    empty = {"actual_agents": [], "local_agents": [], "cloud_agents": []}
    for gate in gate_results:
        if gate.get("adapter_id") != "agent_mix" and gate.get("gate_id") != "gate-agent-mix":
            continue
        evidence = gate.get("evidence") or {}
        constraints = evidence.get("satisfied_constraints") or []
        for constraint in constraints:
            details = (constraint or {}).get("evidence") or {}
            if isinstance(details, dict):
                return {
                    "actual_agents": list(details.get("actual_agents") or []),
                    "local_agents": list(details.get("local_agents") or []),
                    "cloud_agents": list(details.get("cloud_agents") or []),
                }
    return empty


def build_task_observability_snapshot(
    *,
    task_id: str,
    description: str,
    status: str,
    subtasks: List[Any],
    waves: List[Any],
    last_owner_decision: Optional[Dict[str, Any]],
    created_at: Optional[float] = None,
    updated_at: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a compact, read-only evidence timeline for task details.

    The snapshot intentionally derives only from already-loaded task state. It
    never resumes tasks, runs probes, or touches the project directory.
    """
    decision = last_owner_decision if isinstance(last_owner_decision, dict) else {}
    quality_report = extract_quality_report_from_decision(decision)
    gate_results = [
        dict(item)
        for item in (quality_report.get("gate_results") or [])
        if isinstance(item, dict)
    ]
    quality_gates = [
        {
            "gate_id": str(gate.get("gate_id") or gate.get("id") or ""),
            "adapter_id": str(gate.get("adapter_id") or gate.get("probe_type") or "unknown"),
            "status": str(gate.get("status") or "unknown"),
            "required": bool(gate.get("required", True)),
            "summary": str(gate.get("summary") or gate.get("output_tail") or "")[:300],
        }
        for gate in gate_results
    ]
    timeline: List[Dict[str, Any]] = [
        {
            "kind": "task_created",
            "label": "Task created",
            "task_id": task_id,
            "status": status,
            "at": created_at,
            "summary": description[:180],
        }
    ]

    for wave in sorted(waves or [], key=lambda item: int(read_obj_value(item, "wave_number", 0) or 0)):
        wave_number = int(read_obj_value(wave, "wave_number", 0) or 0)
        governance = str(read_obj_value(wave, "governance_status", "") or "")
        wave_status = status_text(read_obj_value(wave, "status", ""))
        is_blocked = bool(read_obj_value(wave, "is_blocked", False))
        if governance == "approved":
            kind = "wave_approved"
        elif is_blocked or governance == "blocked":
            kind = "wave_blocked"
        elif governance == "revalidating" or bool(read_obj_value(wave, "is_revalidating", False)):
            kind = "wave_revalidating"
        else:
            kind = "wave_status"
        timeline.append({
            "kind": kind,
            "label": f"Wave {wave_number}",
            "wave_number": wave_number,
            "status": governance or wave_status or "pending",
        })

    for subtask in sorted(
        subtasks or [],
        key=lambda item: (
            int(read_obj_value(item, "wave_number", 0) or 0),
            str(read_obj_value(item, "subtask_id", "")),
        ),
    ):
        subtask_status = status_text(read_obj_value(subtask, "status", "pending"))
        if subtask_status not in {"running", "completed", "failed", "cancelled"}:
            continue
        kind = {
            "running": "subtask_running",
            "completed": "subtask_completed",
            "failed": "subtask_failed",
            "cancelled": "subtask_cancelled",
        }.get(subtask_status, "subtask_status")
        timeline.append({
            "kind": kind,
            "label": str(read_obj_value(subtask, "description", ""))[:120],
            "subtask_id": str(read_obj_value(subtask, "subtask_id", "")),
            "agent_id": str(read_obj_value(subtask, "agent_id", "")),
            "wave_number": int(read_obj_value(subtask, "wave_number", 1) or 1),
            "status": subtask_status,
        })

    for gate in quality_gates:
        status_value = gate["status"]
        timeline.append({
            "kind": f"quality_gate_{status_value}",
            "label": gate["adapter_id"],
            "gate_id": gate["gate_id"],
            "status": status_value,
            "required": gate["required"],
            "summary": gate["summary"],
        })

    remediation_attempts = dict(decision.get("quality_remediation_attempts") or {})
    if remediation_attempts:
        timeline.append({
            "kind": "remediation_attempted",
            "label": "Quality remediation",
            "status": "attempted",
            "attempts_by_requirement": remediation_attempts,
        })

    return {
        "timeline": timeline,
        "quality_gates": quality_gates,
        "agent_mix": extract_agent_mix_from_gates(gate_results),
        "remediation": {
            "attempted": bool(remediation_attempts),
            "attempts_by_requirement": remediation_attempts,
            "max_attempts": decision.get("max_quality_remediation_attempts", 4),
            "deterministic_repair_attempted": bool(decision.get("deterministic_delivery_repair_attempted")),
        },
        "quality_score": quality_report.get("final_quality_score"),
        "updated_at": updated_at,
    }

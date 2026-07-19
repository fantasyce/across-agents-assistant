from __future__ import annotations

from typing import Any, Dict, List, Optional


REQUIRED_APP_GRADE_GATES = [
    "artifact_integrity",
    "workspace_hygiene",
    "security_privacy",
    "agent_mix",
    "static_web_smoke",
    "browser_e2e",
    "api_service",
    "cli_generic",
]

DEFAULT_RELEASE_REQUIRED_PROBES = [
    "workspace_hygiene",
    "security_privacy",
    "static_web_smoke",
    "browser_e2e",
    "api_service",
    "cli_generic",
]


def _status_is_passed(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"passed", "pass", "ok", "true", "success"}


def _gate_statuses(evidence: Dict[str, Any]) -> Dict[str, Any]:
    statuses: Dict[str, Any] = {}
    app_grade = evidence.get("app_grade") or {}
    quality_report = app_grade.get("quality_report") or evidence.get("quality") or {}
    for result in quality_report.get("gate_results") or quality_report.get("gateResults") or []:
        gate_id = result.get("adapter_id") or result.get("gate_id") or result.get("id") or result.get("name")
        if gate_id:
            statuses[str(gate_id)] = result.get("status") or result.get("passed")
    for probe in quality_report.get("probe_results") or quality_report.get("probeResults") or []:
        probe_id = probe.get("probe_type") or probe.get("adapter_id") or probe.get("id")
        if probe_id:
            statuses[str(probe_id)] = probe.get("status") or probe.get("passed")
    for key, value in (quality_report.get("gates") or {}).items():
        statuses[str(key)] = value
    return statuses


def _artifact_integrity_passed(evidence: Dict[str, Any], expected_files: List[str]) -> bool:
    app_grade = evidence.get("app_grade") or {}
    exact_files = [str(item) for item in app_grade.get("exact_files") or []]
    if expected_files and exact_files:
        return sorted(exact_files) == sorted(expected_files)
    artifacts = evidence.get("artifacts") or []
    present = {str(item.get("path")) for item in artifacts if item.get("present")}
    return all(path in present for path in expected_files)


def _is_app_grade_evidence(evidence: Dict[str, Any]) -> bool:
    contract = evidence.get("contract") or {}
    return bool(evidence.get("app_grade")) or contract.get("engine") == "app_grade_release_e2e"


def _evaluate_generic_orchestrator_quality(
    evidence: Dict[str, Any],
    *,
    expected_files: Optional[List[str]] = None,
    required_probes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    contract = evidence.get("contract") or {}
    quality = evidence.get("quality") or {}
    expected = list(expected_files or contract.get("requiredArtifacts") or [])
    gate_statuses = dict(quality.get("gates") or {})
    checks: Dict[str, bool] = {
        "task_completed": str(evidence.get("status") or "").strip().lower() == "completed",
        "artifact_integrity": _artifact_integrity_passed(evidence, expected),
        "orchestrator_quality": _status_is_passed(quality.get("status")),
    }
    probes = list(required_probes or [])
    for probe in probes:
        checks[probe] = _status_is_passed(gate_statuses.get(probe))
    failures = [f"{check} did not pass" for check, passed in checks.items() if not passed]
    passed = all(checks.values())
    produced_files = sorted(
        str(item.get("path"))
        for item in evidence.get("artifacts") or []
        if item.get("present") and item.get("path")
    )
    return {
        "status": "passed" if passed else "failed",
        "quality_gate": "passed" if passed else "failed",
        "delivery_quality": "passed" if passed else "failed",
        "quality_score": 100 if passed else int(100 * sum(checks.values()) / max(1, len(checks))),
        "checks": checks,
        "failures": failures,
        "produced_files": produced_files,
        "required_files": expected,
        "required_probes": probes,
        "gate_results": gate_statuses,
    }


def evaluate_app_grade_quality(
    evidence: Dict[str, Any],
    *,
    expected_files: Optional[List[str]] = None,
    required_probes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    evidence = evidence or {}
    app_grade = evidence.get("app_grade") or {}
    contract = evidence.get("contract") or {}
    expected = list(expected_files or app_grade.get("required_files") or contract.get("requiredArtifacts") or [])
    gate_statuses = _gate_statuses(evidence)
    checks: Dict[str, bool] = {}
    checks["artifact_integrity"] = _artifact_integrity_passed(evidence, expected)

    required_gates = list(REQUIRED_APP_GRADE_GATES)
    for gate in required_gates:
        if gate == "artifact_integrity":
            continue
        raw = gate_statuses.get(gate)
        if raw is None and gate == "static_web_smoke":
            raw = gate_statuses.get("static_web")
        checks[gate] = _status_is_passed(raw)

    probes = list(required_probes or DEFAULT_RELEASE_REQUIRED_PROBES)
    for probe in probes:
        if probe == "static_web" and "static_web_smoke" in checks:
            continue
        if probe not in checks:
            checks[probe] = _status_is_passed(gate_statuses.get(probe))

    delivery_quality = app_grade.get("delivery_quality") or (evidence.get("quality") or {}).get("status")
    delivery_quality_passed = True if delivery_quality in {None, ""} else _status_is_passed(delivery_quality)
    produced_files = [str(item) for item in app_grade.get("exact_files") or []]
    if not produced_files:
        produced_files = [str(item.get("path")) for item in evidence.get("artifacts") or [] if item.get("present")]

    failures = [f"{gate} did not pass" for gate, passed in checks.items() if not passed]
    if not delivery_quality_passed:
        failures.append(f"delivery_quality is {delivery_quality}")
    passed = all(checks.values()) and delivery_quality_passed
    score = 100 if passed else int(100 * sum(1 for ok in checks.values() if ok) / max(1, len(checks)))
    return {
        "status": "passed" if passed else "failed",
        "quality_gate": "passed" if passed else "failed",
        "delivery_quality": "passed" if passed else "failed",
        "quality_score": score,
        "checks": checks,
        "failures": failures,
        "produced_files": sorted(produced_files),
        "required_files": expected,
        "required_probes": probes,
        "gate_results": gate_statuses,
    }


def build_external_quality_benchmark(
    evidence: Dict[str, Any],
    *,
    expected_files: Optional[List[str]] = None,
    required_probes: Optional[List[str]] = None,
    min_quality_score: int = 70,
    max_remediation_attempts: int = 2,
    benchmark_id: str,
    app_version: Optional[str] = None,
) -> Dict[str, Any]:
    quality = (
        evaluate_app_grade_quality(
            evidence,
            expected_files=expected_files,
            required_probes=required_probes,
        )
        if _is_app_grade_evidence(evidence)
        else _evaluate_generic_orchestrator_quality(
            evidence,
            expected_files=expected_files,
            required_probes=required_probes,
        )
    )
    status = "passed" if quality["status"] == "passed" and quality["quality_score"] >= min_quality_score else "failed"
    scenario = {
        "task_id": evidence.get("task_id") or "",
        "status": status,
        "quality_gate": quality["quality_gate"],
        "final_status": evidence.get("status") or "unknown",
        "quality_score": quality["quality_score"],
        "remediation_attempts": 0,
        "produced_files": quality["produced_files"],
        "checks": quality["checks"],
        "failures": quality["failures"],
    }
    return {
        "benchmark_id": benchmark_id,
        "benchmark_version": "external-orchestrator-1.0",
        "app_version": app_version,
        "status": status,
        "summary": {
            "scenario_count": 1,
            "passed_scenarios": 1 if status == "passed" else 0,
            "failed_scenarios": 0 if status == "passed" else 1,
            "min_quality_score": quality["quality_score"],
            "max_remediation_attempts": 0,
        },
        "scenarios": [scenario],
        "external_quality": quality,
        "policy": {
            "min_quality_score": min_quality_score,
            "max_remediation_attempts": max_remediation_attempts,
        },
    }


def external_evidence_to_app_bundle(
    evidence: Dict[str, Any],
    *,
    expected_files: Optional[List[str]] = None,
    required_probes: Optional[List[str]] = None,
    min_quality_score: int = 70,
    max_remediation_attempts: int = 2,
    benchmark_id: str,
    app_version: Optional[str] = None,
) -> Dict[str, Any]:
    expected = list(
        expected_files
        or (evidence.get("app_grade") or {}).get("required_files")
        or (evidence.get("contract") or {}).get("requiredArtifacts")
        or []
    )
    app_grade = _is_app_grade_evidence(evidence)
    probes = list(required_probes or (DEFAULT_RELEASE_REQUIRED_PROBES if app_grade else []))
    benchmark = build_external_quality_benchmark(
        evidence,
        expected_files=expected,
        required_probes=probes,
        min_quality_score=min_quality_score,
        max_remediation_attempts=max_remediation_attempts,
        benchmark_id=benchmark_id,
        app_version=app_version,
    )
    return {
        "schema_version": "1.0",
        "app_version": app_version,
        "generated_at": __import__("time").time(),
        "task_id": evidence.get("task_id") or "",
        "description": evidence.get("goal"),
        "task_status": evidence.get("status") or "unknown",
        "task_types": list((evidence.get("metadata") or {}).get("task_types") or ["functional", "artifact"]),
        "delivery_mode": str((evidence.get("metadata") or {}).get("delivery_mode") or "composite"),
        "project_dir": evidence.get("project_root"),
        "owner_agent": (
            (evidence.get("contract") or {}).get("engine")
            or next(
                (str(item.get("agent")) for item in evidence.get("subtasks") or [] if item.get("agent")),
                "across-orchestrator",
            )
        ),
        "allowed_subtask_agents": sorted({str(item.get("agent") or "app-grade") for item in evidence.get("subtasks") or []}),
        "delivery_contract": evidence.get("contract") or {},
        "requirement_manifest": {
            "task_id": evidence.get("task_id") or "",
            "project_dir": evidence.get("project_root"),
            "deliverables": [{"path": path, "status": "accepted"} for path in expected],
        },
        "last_owner_decision": {
            "decision": "external_orchestrator",
            "delivery_quality": benchmark.get("external_quality") or {},
        },
        "quality_health": {
            "quality_gate": benchmark["status"],
            "delivery_quality": benchmark["status"],
            "delivery_quality_report": benchmark.get("external_quality") or {},
        },
        "delivery_report": {
            "status": benchmark["status"],
            "source": "across_orchestrator",
            "checks": (benchmark.get("external_quality") or {}).get("checks", {}),
        },
        "observability": {"orchestrator_plugin": {"implementation": "external"}},
        "artifacts": evidence.get("artifacts") or [],
        "acceptance_records": [],
        "benchmark": benchmark,
        "audit": {
            "read_only": True,
            "repair_or_resume_triggered": False,
            "secrets_redacted": True,
            "expected_files": expected,
            "required_files": expected,
            "required_probes": probes,
        },
    }

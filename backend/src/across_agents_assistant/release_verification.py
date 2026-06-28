from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
import json
import re
import time

from .paths import app_subdir


RELEASE_E2E_DESCRIPTION_MARKER = "Release E2E scenario:"
RELEASE_E2E_SCENARIO_MARKERS = {
    "Scenario ID: cross_agent_full_delivery_v1",
    "Scenario ID: host_agent_full_delivery_v1",
}
RELEASE_VERIFICATION_EXPECTED_FILES = [
    "README.md",
    "web/index.html",
    "web/styles.css",
    "web/app.js",
    "api/server.mjs",
    "cli/quality-check.mjs",
    "tests/e2e-smoke.mjs",
]
RELEASE_VERIFICATION_REQUIRED_PROBES = [
    "workspace_hygiene",
    "security_privacy",
    "static_web_smoke",
    "browser_e2e",
    "api_service",
    "cli_generic",
]
PRE_RELEASE_GATE_EVIDENCE_PATTERNS = [
    "*-gate-evidence.json",
    "live-e2e-evidence.json",
]
PRE_RELEASE_GATE_EVIDENCE_ENV = "ACROSS_AGENTS_PRE_RELEASE_GATE_EVIDENCE_PATHS"

PRE_RELEASE_GATE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "backend_regression",
        "label": "Backend regression",
        "source": "local",
        "command": "PYTHONPATH=backend/src backend/.venv/bin/python -m pytest backend/tests --ignore=backend/tests/e2e -q",
        "detail": "Backend regression suite excluding live E2E, which is covered by the dedicated Live E2E gate.",
        "paths": ["backend/tests"],
        "status_when_configured": "configured",
        "required": True,
        "readiness_impact": "required",
    },
    {
        "id": "open_source_check",
        "label": "Open-source check",
        "source": "local_script",
        "command": "bash scripts/open_source_check.sh",
        "detail": "Repository hygiene, sensitive-text scanning, README assets, icon attribution, and shell syntax checks.",
        "paths": ["scripts/open_source_check.sh"],
        "status_when_configured": "configured",
        "required": True,
        "readiness_impact": "required",
    },
    {
        "id": "swift_behavior_checks",
        "label": "Swift behavior checks",
        "source": "local_script",
        "command": "bash scripts/run_swift_behavior_checks.sh",
        "detail": "Standalone Swift model and localization behavior checks used by Quality CI.",
        "paths": ["scripts/run_swift_behavior_checks.sh"],
        "status_when_configured": "configured",
        "required": True,
        "readiness_impact": "required",
    },
    {
        "id": "swift_package_gate",
        "label": "Swift package gate",
        "source": "local_script",
        "command": "bash scripts/verify_swift_package_lock.sh && swift build --package-path macOS-Client --skip-update && swift test --package-path macOS-Client --skip-update",
        "detail": "Swift package lock consistency, macOS client build, and SwiftPM test gate.",
        "paths": ["scripts/verify_swift_package_lock.sh", "macOS-Client/Package.swift"],
        "status_when_configured": "configured",
        "required": True,
        "readiness_impact": "required",
    },
    {
        "id": "quality_ci",
        "label": "Quality CI",
        "source": "github_actions",
        "command": "gh pr checks <release-pr-number>",
        "detail": "Pull request CI runs open-source checks, backend regression, Swift lock/build, and Swift behavior checks.",
        "paths": [".github/workflows/quality.yml"],
        "status_when_configured": "configured",
        "required": True,
        "readiness_impact": "required",
    },
    {
        "id": "local_live_e2e",
        "label": "Local Live E2E",
        "source": "local_script",
        "command": "bash scripts/run_live_e2e.sh all",
        "detail": "Temporary AAA backend plus external Across Orchestrator sidecar, tiered E2E, and legacy socket API E2E.",
        "paths": ["scripts/run_live_e2e.sh"],
        "status_when_configured": "manual_required",
        "required": True,
        "readiness_impact": "manual",
    },
    {
        "id": "github_live_e2e",
        "label": "GitHub Live E2E",
        "source": "github_actions",
        "command": "gh workflow run \"Live E2E\" -f tier=all --ref main",
        "detail": "Manual workflow_dispatch gate that installs Across Orchestrator and runs the same live E2E runner remotely.",
        "paths": [".github/workflows/live-e2e.yml"],
        "status_when_configured": "manual_required",
        "required": True,
        "readiness_impact": "manual",
    },
]
PUBLIC_PRE_RELEASE_GATE_PATHS = sorted(
    {
        str(path)
        for definition in PRE_RELEASE_GATE_DEFINITIONS
        for path in (definition.get("paths") or [])
    }
)


SENSITIVE_EVIDENCE_KEY_RE = re.compile(
    r"(api[_-]?key|secret|token|password|credential|authorization|private[_-]?key|access[_-]?key)",
    re.IGNORECASE,
)


def _redact_sensitive_evidence(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if SENSITIVE_EVIDENCE_KEY_RE.search(key_text):
                sanitized[key_text] = "[redacted]"
            else:
                sanitized[key_text] = _redact_sensitive_evidence(item)
        return sanitized
    if isinstance(value, list):
        return [_redact_sensitive_evidence(item) for item in value]
    if isinstance(value, str) and re.search(
        r"((?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{16,}|AKIA[0-9A-Z]{16})",
        value,
    ):
        return "[redacted]"
    return value


def _pydantic_dump(model: Any, **kwargs: Any) -> Dict[str, Any]:
    return model.model_dump(**kwargs) if hasattr(model, "model_dump") else model.dict(**kwargs)


def _row_task_id(row: Any) -> Optional[str]:
    if isinstance(row, dict):
        task_id = row.get("task_id")
        return str(task_id) if task_id else None
    return None


def _task_row_for_release_evaluation(task: Any) -> Dict[str, Any]:
    """Normalize internal ``Task`` objects into release-evaluation rows."""
    if not task:
        return {}

    status = getattr(task, "status", "created")
    status_value = getattr(status, "value", status)

    return {
        "task_id": getattr(task, "task_id", None),
        "description": getattr(task, "description", None) or "",
        "status": status_value,
        "progress": getattr(task, "progress", 0.0),
        "completed_count": getattr(task, "completed_count", 0),
        "total_count": getattr(task, "total_count", 0),
        "created_at": getattr(task, "created_at", 0.0),
        "updated_at": getattr(task, "updated_at", 0.0),
        "project_dir": getattr(task, "project_dir", None),
        "owner_agent": getattr(task, "owner_agent", None),
        "allowed_subtask_agents": list(getattr(task, "allowed_subtask_agents", []) or []),
        "task_types": list(getattr(task, "task_types", []) or []),
        "delivery_mode": getattr(task, "delivery_mode", "external") or "external",
        "last_owner_decision": getattr(task, "last_owner_decision", None) or {},
    }


def _collect_rows_from_storage(task_state: Any, limit: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    persistence = getattr(task_state, "_persistence", None)
    if persistence and hasattr(persistence, "get_task_summaries"):
        persisted_rows, _total = persistence.get_task_summaries(limit=limit, offset=0)
    elif persistence and hasattr(persistence, "get_all_tasks"):
        all_rows = persistence.get_all_tasks()
        persisted_rows = all_rows[:limit]
    else:
        persisted_rows = []

    for row in persisted_rows or []:
        if isinstance(row, dict):
            rows.append(dict(row))
    return rows


def _collect_rows_from_runtime(task_state: Any, task_row_mapper: Optional[Callable[[Any], Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    mapper = task_row_mapper or _task_row_for_release_evaluation

    get_all = getattr(task_state, "get_all_tasks", None)
    if callable(get_all):
        rows.extend(mapper(row) for row in (get_all() or []))

    return rows


def _collect_release_task_rows(
    safe_limit: int = 100,
    *,
    task_state: Optional[Any] = None,
    external_task_rows: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None,
    task_row_mapper: Optional[Callable[[Any], Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Collect normalized task rows for release evaluation and verification."""
    rows: List[Dict[str, Any]] = []
    seen_task_ids: set[str] = set()

    if task_state is None:
        return rows

    for row in _collect_rows_from_storage(task_state, safe_limit):
        task_id = _row_task_id(row)
        if task_id and task_id not in seen_task_ids:
            rows.append(dict(row))
            seen_task_ids.add(task_id)

    for row in _collect_rows_from_runtime(task_state, task_row_mapper=task_row_mapper):
        task_id = _row_task_id(row)
        if task_id and task_id not in seen_task_ids:
            rows.append(row)
            seen_task_ids.add(task_id)

    if external_task_rows:
        try:
            for row in external_task_rows() or []:
                row = dict(row or {})
                task_id = _row_task_id(row)
                if task_id and task_id in seen_task_ids:
                    continue
                rows.append(
                    {
                        "task_id": task_id,
                        "description": row.get("description") or "",
                        "status": row.get("status") or "pending",
                        "progress": row.get("progress") or 0.0,
                        "completed_count": row.get("completed_count") or 0,
                        "total_count": row.get("total_count") or 0,
                        "created_at": row.get("created_at") or 0.0,
                        "updated_at": row.get("updated_at") or 0.0,
                        "project_dir": row.get("project_dir"),
                        "owner_agent": row.get("owner_agent"),
                        "allowed_subtask_agents": row.get("allowed_subtask_agents") or [],
                        "task_types": list(row.get("task_types") or ["functional", "artifact"]),
                        "delivery_mode": row.get("delivery_mode") or "composite",
                        "last_owner_decision": row.get("last_owner_decision") or {},
                    }
                )
                if task_id:
                    seen_task_ids.add(task_id)
        except Exception:
            pass

    return rows[:safe_limit]


def _release_evaluation_row_from_task_payload(payload: Dict[str, Any], fallback_row: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a full task payload back into the release-evaluation row shape."""
    row = dict(fallback_row)
    for key in [
        "task_id",
        "description",
        "status",
        "progress",
        "completed_count",
        "total_count",
        "created_at",
        "updated_at",
        "project_dir",
        "owner_agent",
        "allowed_subtask_agents",
        "task_types",
        "delivery_mode",
        "last_owner_decision",
        "quality_health",
        "delivery_report",
        "observability",
    ]:
        if key in payload and payload.get(key) is not None:
            row[key] = payload.get(key)
    return row


def _upsert_release_evaluation_row(rows: List[Dict[str, Any]], enriched_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    task_id = _row_task_id(enriched_row)
    if not task_id:
        return rows
    result: List[Dict[str, Any]] = []
    replaced = False
    for row in rows:
        if _row_task_id(row) == task_id:
            result.append(enriched_row)
            replaced = True
        else:
            result.append(row)
    if not replaced:
        result.append(enriched_row)
    result.sort(key=lambda row: row.get("updated_at") or row.get("created_at") or 0, reverse=True)
    return result


def _latest_release_e2e_row(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    release_rows = _release_e2e_rows(rows, limit=1)
    return release_rows[0] if release_rows else None


def _release_e2e_rows(rows: List[Dict[str, Any]], *, limit: int = 3) -> List[Dict[str, Any]]:
    release_rows = [
        dict(row)
        for row in rows
        if _is_release_e2e_description(str(row.get("description") or ""))
    ]
    if not release_rows:
        return []
    return sorted(
        release_rows,
        key=lambda row: row.get("updated_at") or row.get("created_at") or 0,
        reverse=True,
    )[: max(1, limit)]


def _is_release_e2e_description(description: str) -> bool:
    text = description.lower()
    if RELEASE_E2E_DESCRIPTION_MARKER.lower() in text:
        return True
    return any(marker.lower() in text for marker in RELEASE_E2E_SCENARIO_MARKERS)


def _repository_root() -> Path:
    # This module currently lives under backend/src/across_agents_assistant.
    # Keep the parent index in sync if release_verification.py moves.
    return Path(__file__).resolve().parents[3]


def _looks_like_source_repository(root: Path) -> bool:
    return (
        (root / "backend" / "src" / "across_agents_assistant").exists()
        and (root / "macOS-Client" / "Package.swift").exists()
    )


def _build_pre_release_gates(repo_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    root = repo_root or _repository_root()
    source_repository_available = _looks_like_source_repository(root)
    gates: List[Dict[str, Any]] = []
    for definition in PRE_RELEASE_GATE_DEFINITIONS:
        paths = list(definition.get("paths") or [])
        missing_paths = [path for path in paths if source_repository_available and not (root / path).exists()]
        status = "missing" if missing_paths else str(definition.get("status_when_configured") or "configured")
        detail = str(definition.get("detail") or "")
        if missing_paths:
            detail = f"Missing release gate path(s): {', '.join(missing_paths)}"
        elif not source_repository_available and paths:
            detail = f"{detail} Source checkout paths are unavailable in this runtime; attach gate evidence instead."
        gates.append(
            {
                "id": definition["id"],
                "label": definition["label"],
                "status": status,
                "source": definition["source"],
                "command": definition["command"],
                "detail": detail,
                "paths": paths,
                "required": bool(definition.get("required", True)),
                "readiness_impact": definition.get("readiness_impact") or "required",
                "source_checkout_available": source_repository_available,
            }
        )
    return gates


def _coerce_gate_evidence_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"passed", "pass", "success", "succeeded", "ok", "true"}:
        return "passed"
    if status in {"failed", "failure", "error", "errored", "false"}:
        return "failed"
    if status in {"blocked", "cancelled", "canceled", "timed_out", "timeout"}:
        return "blocked"
    if status in {"manual_required", "attention", "warning"}:
        return status
    return "unknown"


def _gate_evidence_timestamp(evidence: Dict[str, Any]) -> str:
    for key in ("completed_at", "generated_at", "started_at"):
        value = evidence.get(key)
        if value:
            return str(value)
    return ""


def _normalize_pre_release_gate_evidence(raw: Any, *, evidence_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    candidates: List[Any]
    if isinstance(raw.get("gates"), list):
        candidates = raw.get("gates") or []
    elif isinstance(raw.get("gate_results"), list):
        candidates = raw.get("gate_results") or []
    else:
        candidates = [raw]

    normalized: List[Dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        gate_id = candidate.get("gate_id") or candidate.get("id")
        if not gate_id:
            continue
        status = _coerce_gate_evidence_status(candidate.get("status") or candidate.get("gate_status"))
        evidence = {
            "schema_version": str(candidate.get("schema_version") or raw.get("schema_version") or "1.0"),
            "gate_id": str(gate_id),
            "status": status,
            "source": str(candidate.get("source") or raw.get("source") or ""),
            "summary": str(candidate.get("summary") or candidate.get("detail") or ""),
            "generated_at": candidate.get("generated_at") or raw.get("generated_at"),
            "started_at": candidate.get("started_at") or raw.get("started_at"),
            "completed_at": candidate.get("completed_at") or raw.get("completed_at"),
            "duration_seconds": candidate.get("duration_seconds") or raw.get("duration_seconds"),
            "tier": candidate.get("tier") or raw.get("tier"),
            "run_url": candidate.get("run_url") or raw.get("run_url"),
            "workflow_run_url": candidate.get("workflow_run_url") or raw.get("workflow_run_url"),
            "commit_sha": candidate.get("commit_sha") or raw.get("commit_sha"),
            "runner": candidate.get("runner") or raw.get("runner"),
            "orchestrator_command": candidate.get("orchestrator_command") or raw.get("orchestrator_command"),
            "workspace_dirty": (
                candidate.get("workspace_dirty")
                if candidate.get("workspace_dirty") is not None
                else raw.get("workspace_dirty")
            ),
        }
        if evidence_path is not None:
            evidence["evidence_path"] = evidence_path.name
        normalized.append(
            _redact_sensitive_evidence(
                {key: value for key, value in evidence.items() if value is not None and value != ""}
            )
        )
    return normalized


def _configured_pre_release_gate_evidence_paths() -> List[Path]:
    raw_paths = os.environ.get(PRE_RELEASE_GATE_EVIDENCE_ENV, "")
    paths: List[Path] = []
    for item in raw_paths.split(os.pathsep):
        item = item.strip()
        if item:
            paths.append(Path(item).expanduser())
    return paths


def _pre_release_gate_parse_error(path: Path) -> Dict[str, str]:
    return {
        "evidence_path": path.name,
        "error_type": "ParseError",
        "message": "Could not parse pre-release gate evidence; see local report for details.",
    }


def _load_pre_release_gate_evidence(report_directory: Path) -> tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]]]:
    candidate_paths: List[Path] = []
    candidate_paths.extend(_configured_pre_release_gate_evidence_paths())
    for pattern in PRE_RELEASE_GATE_EVIDENCE_PATTERNS:
        candidate_paths.extend(sorted(report_directory.glob(pattern)))

    evidence_by_gate: Dict[str, Dict[str, Any]] = {}
    parse_errors: List[Dict[str, str]] = []
    for path in candidate_paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            parse_errors.append(_pre_release_gate_parse_error(path))
            continue
        for evidence in _normalize_pre_release_gate_evidence(raw, evidence_path=path):
            gate_id = str(evidence.get("gate_id") or "")
            if not gate_id:
                continue
            previous = evidence_by_gate.get(gate_id)
            if previous and _gate_evidence_timestamp(previous) > _gate_evidence_timestamp(evidence):
                continue
            evidence_by_gate[gate_id] = evidence
    return evidence_by_gate, parse_errors


def _apply_pre_release_gate_evidence(
    gates: Sequence[Dict[str, Any]],
    evidence_by_gate: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    updated: List[Dict[str, Any]] = []
    for gate in gates:
        enriched = dict(gate)
        evidence = evidence_by_gate.get(str(gate.get("id") or ""))
        if evidence:
            status = _coerce_gate_evidence_status(evidence.get("status"))
            enriched["evidence"] = evidence
            if status in {"passed", "failed", "blocked", "attention", "warning", "manual_required"}:
                enriched["status"] = status
            if status in {"failed", "blocked"}:
                summary = evidence.get("summary") or "Gate evidence did not pass."
                enriched["detail"] = str(summary)
        updated.append(enriched)
    return updated


def _pre_release_gate_summary(gates: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "total": len(gates),
        "passed": sum(1 for gate in gates if gate.get("status") == "passed"),
        "configured": sum(1 for gate in gates if gate.get("status") == "configured"),
        "manual_required": sum(1 for gate in gates if gate.get("status") == "manual_required"),
        "missing": sum(1 for gate in gates if gate.get("status") == "missing"),
        "failed": sum(1 for gate in gates if gate.get("status") in {"failed", "blocked"}),
        "required_missing": sum(
            1
            for gate in gates
            if gate.get("required") is True and gate.get("status") == "missing"
        ),
        "required_manual": sum(
            1
            for gate in gates
            if gate.get("required") is True and gate.get("status") == "manual_required"
        ),
        "required_failed": sum(
            1
            for gate in gates
            if gate.get("required") is True and gate.get("status") in {"failed", "blocked"}
        ),
        "required_unverified": sum(
            1
            for gate in gates
            if gate.get("required") is True and gate.get("status") == "configured"
        ),
    }


def _missing_required_gate_paths(gates: Sequence[Dict[str, Any]]) -> List[str]:
    missing_paths = {
        str(path)
        for gate in gates
        if gate.get("required") is True and gate.get("status") == "missing"
        for path in (gate.get("paths") or [])
    }
    return sorted(missing_paths)


def _release_verification_status(
    startup_status: str,
    latest_release_e2e: Optional[Dict[str, Any]],
    pre_release_gate_summary: Optional[Dict[str, int]] = None,
    release_evaluation_readiness: str = "unknown",
) -> tuple[str, List[str]]:
    remediations: List[str] = []
    if startup_status == "blocked":
        remediations.append("Resolve failed startup diagnostics before release approval.")

    if (pre_release_gate_summary or {}).get("required_missing", 0) > 0:
        remediations.append("Restore missing pre-release verification gates before release approval.")
    if (pre_release_gate_summary or {}).get("required_failed", 0) > 0:
        remediations.append("Review failed pre-release verification gate evidence before release approval.")
    if (pre_release_gate_summary or {}).get("required_manual", 0) > 0:
        remediations.append("Run required manual pre-release gates and attach their evidence before release approval.")
    if (pre_release_gate_summary or {}).get("required_unverified", 0) > 0:
        remediations.append("Attach passing evidence for configured pre-release verification gates before release approval.")

    if latest_release_e2e is None:
        remediations.append("Run the fixed Release E2E scenario from the frontend and wait for passing evidence.")
    else:
        benchmark_status = str((latest_release_e2e.get("benchmark") or {}).get("status") or "unknown")
        if benchmark_status != "passed":
            remediations.append("Review the latest Release E2E benchmark failures and rerun remediation.")

    release_readiness = str(release_evaluation_readiness or "unknown")
    if release_readiness == "blocked":
        remediations.append("Review blocked release evaluation risks before release approval.")
    elif release_readiness != "ready":
        remediations.append("Collect passing release evaluation evidence before release approval.")

    if startup_status == "blocked":
        return "blocked", remediations
    if (pre_release_gate_summary or {}).get("required_failed", 0) > 0:
        return "blocked", remediations
    if release_readiness == "blocked":
        return "blocked", remediations
    if (pre_release_gate_summary or {}).get("required_missing", 0) > 0:
        return "attention", remediations
    if (pre_release_gate_summary or {}).get("required_manual", 0) > 0:
        return "attention", remediations
    if (pre_release_gate_summary or {}).get("required_unverified", 0) > 0:
        return "attention", remediations
    if latest_release_e2e is not None:
        benchmark_status = str((latest_release_e2e.get("benchmark") or {}).get("status") or "unknown")
        if benchmark_status != "passed":
            return "blocked", remediations
    if release_readiness != "ready":
        return "attention", remediations
    if startup_status == "attention" or latest_release_e2e is None:
        return "attention", remediations
    return "ready", remediations


def _build_latest_release_e2e_verification(
    row: Dict[str, Any],
    *,
    load_task_payload: Callable[[str], Any],
    serialize_task_payload: Callable[[Any], Dict[str, Any]] = _pydantic_dump,
    redact_sensitive: Callable[[Any], Any] = _redact_sensitive_evidence,
    expected_files: Optional[Sequence[str]] = None,
    required_probes: Optional[Sequence[str]] = None,
    app_version: Optional[str] = None,
) -> Dict[str, Any]:
    from .task_review.quality_benchmark import evaluate_delivery_benchmark

    task_id = row.get("task_id")
    if not task_id:
        raise ValueError("release E2E row does not include a task_id")

    task_info = serialize_task_payload(load_task_payload(str(task_id)))
    benchmark = evaluate_delivery_benchmark(
        [task_info],
        benchmark_id=f"task-{task_id}-rc-verification",
        expected_files=list(expected_files or RELEASE_VERIFICATION_EXPECTED_FILES),
        required_probes=list(required_probes or RELEASE_VERIFICATION_REQUIRED_PROBES),
        min_quality_score=70,
        max_remediation_attempts=2,
    )

    if app_version:
        benchmark["app_version"] = app_version

    sanitized_benchmark = redact_sensitive(benchmark)
    scenario = (sanitized_benchmark.get("scenarios") or [{}])[0]
    return {
        "task_id": str(task_id),
        "description": task_info.get("description") or row.get("description") or "",
        "task_status": task_info.get("status") or row.get("status") or "unknown",
        "project_dir": task_info.get("project_dir"),
        "updated_at": row.get("updated_at") or task_info.get("updated_at"),
        "benchmark": sanitized_benchmark,
        "summary": {
            "status": sanitized_benchmark.get("status") or "unknown",
            "quality_score": scenario.get("quality_score"),
            "remediation_attempts": scenario.get("remediation_attempts", 0),
            "failed_scenarios": (sanitized_benchmark.get("summary") or {}).get("failed_scenarios", 0),
        },
    }


def _release_verification_markdown(report: Dict[str, Any]) -> str:
    startup_summary = report.get("startup", {}).get("summary", {})
    release_evaluation = report.get("release_evaluation") or {}
    latest = report.get("latest_release_e2e")
    pre_release_gates = report.get("pre_release_gates") or []
    pre_release_summary = report.get("pre_release_gate_summary") or {}
    pre_release_missing_paths = report.get("pre_release_gate_missing_paths") or []
    pre_release_parse_errors = report.get("pre_release_gate_parse_errors") or []
    lines = [
        "# Across Agents Assistant RC Verification",
        "",
        f"Status: {report.get('status')}",
        f"App version: {report.get('app_version')}",
        f"Generated at: {report.get('generated_at')}",
        "",
        "## Startup Diagnostics",
        (
            f"Status {startup_summary.get('status')} · "
            f"{startup_summary.get('passed', 0)} passed · "
            f"{startup_summary.get('warnings', 0)} warnings · "
            f"{startup_summary.get('failed', 0)} failed"
        ),
        "",
        "## Latest Release E2E",
    ]
    if latest:
        scenario = (latest.get("benchmark", {}).get("scenarios") or [{}])[0]
        lines.extend([
            f"Task: {latest.get('task_id')}",
            f"Task status: {latest.get('task_status')}",
            f"Benchmark: {latest.get('benchmark', {}).get('status')}",
            f"Quality score: {scenario.get('quality_score')}",
            f"Remediation attempts: {scenario.get('remediation_attempts', 0)}",
        ])
        failures = scenario.get("failures") or []
        if failures:
            lines.extend(["", "Failures:"])
            lines.extend([f"- {failure}" for failure in failures])
    else:
        lines.append("No Release E2E evidence was found.")

    lines.extend([
        "",
        "## Release Evaluation",
        f"Readiness: {release_evaluation.get('release_readiness')}",
        (
            f"Evidence: {release_evaluation.get('passed_evidence_count', 0)}/"
            f"{release_evaluation.get('release_evidence_count', 0)}"
        ),
        f"Agent interop E2E: {release_evaluation.get('agent_interop_e2e_status') or 'unknown'}",
    ])
    supplemental_evidence = release_evaluation.get("supplemental_evidence") or []
    if supplemental_evidence:
        lines.append("Supplemental evidence:")
        for evidence in supplemental_evidence:
            lines.append(
                (
                    f"- {evidence.get('kind')}: {evidence.get('status')} "
                    f"({evidence.get('passed_count', 0)} passed, "
                    f"{evidence.get('failed_count', 0)} failed)"
                )
            )

    lines.extend([
        "",
        "## Pre-Release Gates",
        (
            f"{pre_release_summary.get('passed', 0)} passed · "
            f"{pre_release_summary.get('configured', 0)} configured · "
            f"{pre_release_summary.get('manual_required', 0)} manual · "
            f"{pre_release_summary.get('missing', 0)} missing · "
            f"{pre_release_summary.get('failed', 0)} failed"
        ),
        f"Required missing: {pre_release_summary.get('required_missing', 0)}",
        f"Required manual: {pre_release_summary.get('required_manual', 0)}",
        f"Required failed: {pre_release_summary.get('required_failed', 0)}",
        f"Required unverified: {pre_release_summary.get('required_unverified', 0)}",
    ])
    if pre_release_missing_paths:
        lines.extend(["", "Missing required gate paths:"])
        lines.extend([f"- {path}" for path in pre_release_missing_paths])
    if pre_release_parse_errors:
        lines.extend(["", "Gate evidence parse errors:"])
        for error in pre_release_parse_errors:
            lines.append(
                f"- {error.get('evidence_path')}: {error.get('error_type')} ({error.get('message')})"
            )
    for gate in pre_release_gates:
        lines.append(
            f"- {gate.get('label')}: {gate.get('status')} ({gate.get('source')})"
        )
        command = gate.get("command")
        if command:
            lines.append(f"  - Command: `{command}`")
        evidence = gate.get("evidence") or {}
        if evidence:
            lines.append(f"  - Evidence: {evidence.get('status')}")
            if evidence.get("completed_at"):
                lines.append(f"  - Completed at: {evidence.get('completed_at')}")
            run_url = evidence.get("run_url") or evidence.get("workflow_run_url")
            if run_url:
                lines.append(f"  - Run URL: {run_url}")
            if evidence.get("commit_sha"):
                lines.append(f"  - Commit: {evidence.get('commit_sha')}")
            if "workspace_dirty" in evidence:
                lines.append(f"  - Workspace dirty: {str(evidence.get('workspace_dirty')).lower()}")
            if evidence.get("runner"):
                lines.append(f"  - Runner: {evidence.get('runner')}")
            if evidence.get("orchestrator_command"):
                lines.append(f"  - Orchestrator command: {evidence.get('orchestrator_command')}")

    remediations = report.get("remediations") or []
    lines.extend(["", "## Remediation"])
    if remediations:
        lines.extend([f"- {item}" for item in remediations])
    else:
        lines.append("No remediation required.")

    audit = report.get("audit") or {}
    lines.extend([
        "",
        "## Audit",
        f"Read only: {audit.get('read_only')}",
        f"Repair or resume triggered: {audit.get('repair_or_resume_triggered')}",
        f"Secrets redacted: {audit.get('secrets_redacted')}",
        "",
    ])
    return "\n".join(lines)


def _write_release_verification_report(report: Dict[str, Any], *, report_directory: Optional[Path] = None) -> Dict[str, str]:
    generated_at = str(report.get("generated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    safe_stamp = generated_at.replace("-", "").replace(":", "").replace(".", "").replace("+", "Z")
    safe_stamp = safe_stamp.replace("T", "T").replace("Z", "Z")

    report_dir = report_directory or app_subdir("release-reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    json_name = f"rc-verification-{safe_stamp}.json"
    markdown_name = f"rc-verification-{safe_stamp}.md"
    json_path = report_dir / json_name
    markdown_path = report_dir / markdown_name

    report["report_files"] = {
        "directory": str(report_dir),
        "json_name": json_name,
        "json_path": str(json_path),
        "markdown_name": markdown_name,
        "markdown_path": str(markdown_path),
    }
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_release_verification_markdown(report), encoding="utf-8")
    return report["report_files"]


def _public_text(value: Any, *, default: str = "", limit: int = 500) -> str:
    text = str(value if value is not None else default)
    if "Traceback (most recent call last)" in text or "\n  File " in text:
        return "See local report for details."
    return re.sub(r"[\r\n\t]+", " ", text).strip()[:limit]


def _public_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _public_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _public_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "passed", "pass", "success", "succeeded", "ok"}:
        return True
    if text in {"false", "0", "no", "n", "failed", "failure", "none", "null", ""}:
        return False
    return bool(value)


def _public_str_list(value: Any, *, limit: int = 50) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_public_text(item, limit=240) for item in value[:limit]]


def _public_int_dict(value: Any) -> Dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {_public_text(key, limit=120): _public_int(item) for key, item in value.items()}


def _public_startup_report(startup: Any, *, app_version: str, generated_at: str) -> Dict[str, Any]:
    startup = startup if isinstance(startup, dict) else {}
    summary = startup.get("summary") if isinstance(startup.get("summary"), dict) else {}
    paths = startup.get("paths") if isinstance(startup.get("paths"), dict) else {}
    runtime = startup.get("runtime") if isinstance(startup.get("runtime"), dict) else {}
    keys = startup.get("keys") if isinstance(startup.get("keys"), dict) else {}
    providers = keys.get("providers") if isinstance(keys.get("providers"), dict) else {}

    checks = []
    for check in startup.get("checks") or []:
        if not isinstance(check, dict):
            continue
        status = _public_text(check.get("status") or "info", limit=80)
        if status == "passed":
            detail = "Check passed."
        elif status in {"failed", "blocked"}:
            detail = "Check failed; see startup diagnostics for details."
        elif status in {"warning", "attention"}:
            detail = "Check requires attention; see startup diagnostics for details."
        else:
            detail = "Check status recorded."
        checks.append(
            {
                "id": _public_text(check.get("id") or "startup_check", limit=120),
                "title": _public_text(check.get("title") or "Startup check", limit=160),
                "status": status,
                "detail": detail,
                "remediation": None,
                "metadata": {},
            }
        )

    readiness_blockers = []
    if keys.get("readiness_blockers"):
        readiness_blockers = ["See startup diagnostics for provider readiness details."]

    return {
        "schema_version": _public_text(startup.get("schema_version") or "1.0", limit=40),
        "app_version": _public_text(startup.get("app_version") or app_version, limit=80),
        "generated_at": _public_text(startup.get("generated_at") or generated_at, limit=80),
        "status": _public_text(startup.get("status") or summary.get("status") or "attention", limit=80),
        "summary": {
            "status": _public_text(summary.get("status") or startup.get("status") or "attention", limit=80),
            "passed": _public_int(summary.get("passed")),
            "warnings": _public_int(summary.get("warnings")),
            "failed": _public_int(summary.get("failed")),
            "check_count": _public_int(summary.get("check_count"), len(checks)),
        },
        "paths": {
            "app_home": _public_text(paths.get("app_home"), limit=500),
            "logs_dir": _public_text(paths.get("logs_dir"), limit=500),
            "run_dir": _public_text(paths.get("run_dir"), limit=500),
            "tmp_dir": _public_text(paths.get("tmp_dir"), limit=500),
            "evidence_dir": _public_text(paths.get("evidence_dir"), limit=500),
            "socket_path": _public_text(paths.get("socket_path"), limit=500),
            "database_path": _public_text(paths.get("database_path"), limit=500),
        },
        "runtime": {
            "pid": _public_int(runtime.get("pid")),
            "started_at": _public_float(runtime.get("started_at")) or 0.0,
            "uptime_sec": _public_float(runtime.get("uptime_sec")) or 0.0,
            "known_tasks": _public_int(runtime.get("known_tasks")),
            "persistence_initialized": _public_bool(runtime.get("persistence_initialized")),
        },
        "keys": {
            "has_any_key": _public_bool(keys.get("has_any_key")),
            "providers": {
                _public_text(key, limit=80): _public_text(value, limit=80)
                for key, value in providers.items()
            },
            "readiness_blockers": readiness_blockers,
        },
        "checks": checks,
    }


def _public_release_evaluation(summary: Any) -> Dict[str, Any]:
    summary = summary if isinstance(summary, dict) else {}
    return {
        "release_readiness": _public_text(summary.get("release_readiness") or "unknown", limit=80),
        "generated_at": _public_float(summary.get("generated_at")),
        "release_evidence_count": _public_int(summary.get("release_evidence_count")),
        "passed_evidence_count": _public_int(summary.get("passed_evidence_count")),
        "agent_interop_e2e_status": _public_text(summary.get("agent_interop_e2e_status"), limit=80),
        "evaluated_task_count": _public_int(summary.get("evaluated_task_count")),
        "terminal_task_count": _public_int(summary.get("terminal_task_count")),
        "passed_task_count": _public_int(summary.get("passed_task_count")),
        "blocked_task_count": _public_int(summary.get("blocked_task_count")),
        "manual_task_count": _public_int(summary.get("manual_task_count")),
        "skipped_task_count": _public_int(summary.get("skipped_task_count")),
        "pass_rate": _public_float(summary.get("pass_rate")) or 0.0,
        "average_final_quality_score": (
            None
            if summary.get("average_final_quality_score") is None
            else _public_int(summary.get("average_final_quality_score"))
        ),
        "total_remediation_count": _public_int(summary.get("total_remediation_count")),
        "recommendation": _public_text(summary.get("recommendation"), limit=500) if summary.get("recommendation") else None,
        "top_risks": _public_release_risks(summary.get("top_risks")),
        "recent_evaluations": [],
        "quality_trend": None,
        "agent_mix_summary": None,
        "probe_coverage": None,
        "readiness_checks": _public_readiness_checks(summary.get("readiness_checks")),
        "supplemental_evidence": _public_supplemental_evidence(summary.get("supplemental_evidence")),
        "gate_breakdown": _public_int_dict(summary.get("gate_breakdown")),
        "stack_coverage": _public_int_dict(summary.get("stack_coverage")),
        "agent_coverage": _public_int_dict(summary.get("agent_coverage")),
    }


def _public_supplemental_evidence(value: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "id": _public_text(item.get("id"), limit=120),
                "kind": _public_text(item.get("kind"), limit=120),
                "status": _public_text(item.get("status"), limit=80),
                "quality_gate": _public_text(item.get("quality_gate"), limit=80),
                "passed_count": _public_int(item.get("passed_count")),
                "failed_count": _public_int(item.get("failed_count")),
                "host_target_count": _public_int(item.get("host_target_count")),
                "mcp_server_count": _public_int(item.get("mcp_server_count")),
                "protocol_readiness_score": _public_int(item.get("protocol_readiness_score")),
                "endpoint": _public_text(item.get("endpoint"), limit=180),
            }
        )
    return result[:8]


def _public_release_risks(value: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "kind": _public_text(item.get("kind"), limit=120),
                "severity": _public_text(item.get("severity") or "medium", limit=80),
                "count": _public_int(item.get("count")) if item.get("count") is not None else None,
                "message": _public_text(item.get("message"), limit=500),
            }
        )
    return result[:8]


def _public_readiness_checks(value: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        label = item.get("label") or item.get("title") or item.get("id") or "Readiness check"
        result.append(
            {
                "id": _public_text(item.get("id"), limit=120),
                "status": _public_text(item.get("status") or "unknown", limit=80),
                "label": _public_text(label, limit=160),
                "message": _public_text(item.get("message"), limit=500),
                "severity": _public_text(item.get("severity") or "medium", limit=80),
            }
        )
    return result[:16]


def _public_benchmark(benchmark: Any) -> Dict[str, Any]:
    benchmark = benchmark if isinstance(benchmark, dict) else {}
    summary = benchmark.get("summary") if isinstance(benchmark.get("summary"), dict) else {}
    scenarios = []
    for scenario in benchmark.get("scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        checks = scenario.get("checks") if isinstance(scenario.get("checks"), dict) else {}
        failure_count = len(scenario.get("failures") or [])
        scenarios.append(
            {
                "task_id": _public_text(scenario.get("task_id"), limit=160),
                "status": _public_text(scenario.get("status") or "unknown", limit=80),
                "quality_gate": _public_text(scenario.get("quality_gate"), limit=80),
                "final_status": _public_text(scenario.get("final_status"), limit=80),
                "quality_score": _public_int(scenario.get("quality_score")),
                "remediation_attempts": _public_int(scenario.get("remediation_attempts")),
                "produced_files": _public_str_list(scenario.get("produced_files")),
                "checks": {_public_text(key, limit=120): bool(value) for key, value in checks.items()},
                "failures": (
                    ["Release benchmark recorded failed checks; see local report for details."]
                    if failure_count
                    else []
                ),
            }
        )
        break

    return {
        "benchmark_id": _public_text(benchmark.get("benchmark_id"), limit=180),
        "benchmark_version": _public_text(benchmark.get("benchmark_version"), limit=80),
        "app_version": _public_text(benchmark.get("app_version"), limit=80),
        "status": _public_text(benchmark.get("status") or "unknown", limit=80),
        "summary": {
            "scenario_count": _public_int(summary.get("scenario_count")),
            "passed_scenarios": _public_int(summary.get("passed_scenarios")),
            "failed_scenarios": _public_int(summary.get("failed_scenarios")),
            "min_quality_score": _public_int(summary.get("min_quality_score")),
            "max_remediation_attempts": _public_int(summary.get("max_remediation_attempts")),
        },
        "scenarios": scenarios,
    }


def _public_latest_release_e2e(latest: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(latest, dict):
        return None
    summary = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
    return {
        "task_id": _public_text(latest.get("task_id"), limit=160),
        "description": _public_text(latest.get("description"), limit=500),
        "task_status": _public_text(latest.get("task_status") or "unknown", limit=80),
        "project_dir": _public_text(latest.get("project_dir"), limit=500),
        "updated_at": _public_float(latest.get("updated_at")),
        "benchmark": _public_benchmark(latest.get("benchmark")),
        "summary": {
            "status": _public_text(summary.get("status") or "unknown", limit=80),
            "quality_score": (
                None if summary.get("quality_score") is None else _public_int(summary.get("quality_score"))
            ),
            "remediation_attempts": _public_int(summary.get("remediation_attempts")),
            "failed_scenarios": _public_int(summary.get("failed_scenarios")),
        },
    }


def _public_gate_evidence(gate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    evidence = gate.get("evidence")
    if not isinstance(evidence, dict):
        return None
    status = _public_text(evidence.get("status") or "unknown", limit=80)
    label = _public_text(gate.get("label") or gate.get("id") or "Pre-release gate", limit=160)
    return {
        "schema_version": _public_text(evidence.get("schema_version") or "1.0", limit=40),
        "gate_id": _public_text(evidence.get("gate_id") or gate.get("id"), limit=120),
        "status": status,
        "source": _public_text(evidence.get("source") or gate.get("source"), limit=120),
        "summary": f"{label} evidence status: {status}.",
        "generated_at": _public_text(evidence.get("generated_at"), limit=120) or None,
        "started_at": _public_text(evidence.get("started_at"), limit=120) or None,
        "completed_at": _public_text(evidence.get("completed_at"), limit=120) or None,
        "duration_seconds": (
            None if evidence.get("duration_seconds") is None else _public_int(evidence.get("duration_seconds"))
        ),
        "tier": _public_text(evidence.get("tier"), limit=80) or None,
        "run_url": _public_text(evidence.get("run_url"), limit=500) or None,
        "workflow_run_url": _public_text(evidence.get("workflow_run_url"), limit=500) or None,
        "commit_sha": _public_text(evidence.get("commit_sha"), limit=120) or None,
        "runner": _public_text(evidence.get("runner"), limit=240) or None,
        "orchestrator_command": _public_text(evidence.get("orchestrator_command"), limit=240) or None,
        "workspace_dirty": _public_bool(evidence.get("workspace_dirty")),
        "evidence_path": _public_text(evidence.get("evidence_path"), limit=240) or None,
    }


def _public_pre_release_gates(gates: Any) -> List[Dict[str, Any]]:
    public_gates: List[Dict[str, Any]] = []
    for gate in gates or []:
        if not isinstance(gate, dict):
            continue
        status = _public_text(gate.get("status") or "unknown", limit=80)
        detail = "Pre-release gate is configured."
        if status == "manual_required":
            detail = "Manual evidence is required before release approval."
        elif status == "missing":
            detail = "Required gate files are missing."
        elif status in {"failed", "blocked"}:
            detail = "Gate evidence did not pass; see local report for details."
        public_gate = {
            "id": _public_text(gate.get("id"), limit=120),
            "label": _public_text(gate.get("label") or gate.get("id"), limit=160),
            "status": status,
            "source": _public_text(gate.get("source") or "unknown", limit=120),
            "command": _public_text(gate.get("command"), limit=500),
            "detail": detail,
            "paths": _public_str_list(gate.get("paths")),
            "required": _public_bool(gate.get("required")),
            "readiness_impact": _public_text(gate.get("readiness_impact") or "required", limit=80),
        }
        evidence = _public_gate_evidence(gate)
        if evidence:
            public_gate["evidence"] = evidence
        public_gates.append(public_gate)
    return public_gates


def _public_parse_errors(parse_errors: Any) -> List[Dict[str, str]]:
    public_errors: List[Dict[str, str]] = []
    for error in parse_errors or []:
        if not isinstance(error, dict):
            continue
        public_errors.append(
            {
                "evidence_path": _public_text(error.get("evidence_path"), limit=240),
                "error_type": "ParseError",
                "message": "Could not parse pre-release gate evidence; see local report for details.",
            }
        )
    return public_errors


def _public_report_files(report_files: Any) -> Dict[str, str]:
    report_files = report_files if isinstance(report_files, dict) else {}
    return {
        "directory": _public_text(report_files.get("directory"), limit=500),
        "json_name": _public_text(report_files.get("json_name"), limit=240),
        "json_path": _public_text(report_files.get("json_path"), limit=500),
        "markdown_name": _public_text(report_files.get("markdown_name"), limit=240),
        "markdown_path": _public_text(report_files.get("markdown_path"), limit=500),
    }


def _public_audit(audit: Any) -> Dict[str, Any]:
    audit = audit if isinstance(audit, dict) else {}
    return {
        "read_only": _public_bool(audit.get("read_only")),
        "repair_or_resume_triggered": _public_bool(audit.get("repair_or_resume_triggered")),
        "secrets_redacted": _public_bool(audit.get("secrets_redacted")),
        "expected_files": _public_str_list(audit.get("expected_files")),
        "required_probes": _public_str_list(audit.get("required_probes")),
    }


def public_release_verification_api_response(report: Any) -> Dict[str, Any]:
    """Project an internal release report into the stable public API shape.

    The internal report is also written to the local release-report directory.
    The HTTP response intentionally avoids arbitrary diagnostic strings so
    exception text, stack traces, command output, and local file contents cannot
    cross the user-facing API boundary.
    """

    from . import __version__

    report = report if isinstance(report, dict) else {}
    startup = report.get("startup") if isinstance(report.get("startup"), dict) else {}
    startup_summary = startup.get("summary") if isinstance(startup.get("summary"), dict) else {}
    startup_runtime = startup.get("runtime") if isinstance(startup.get("runtime"), dict) else {}
    release_evaluation = report.get("release_evaluation") if isinstance(report.get("release_evaluation"), dict) else {}
    latest_release_e2e = report.get("latest_release_e2e") if isinstance(report.get("latest_release_e2e"), dict) else None
    gate_summary = report.get("pre_release_gate_summary") if isinstance(report.get("pre_release_gate_summary"), dict) else {}
    audit = report.get("audit") if isinstance(report.get("audit"), dict) else {}
    status = _public_status_literal(report.get("status"), default="attention")
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return {
        "schema_version": "1.0",
        "app_version": __version__,
        "generated_at": generated_at,
        "status": status,
        "startup": _public_api_startup(startup, startup_summary, startup_runtime, __version__, generated_at),
        "release_evaluation": _public_api_release_evaluation(release_evaluation),
        "latest_release_e2e": _public_api_latest_release_e2e(latest_release_e2e),
        "pre_release_gates": _public_api_pre_release_gates(report.get("pre_release_gates")),
        "pre_release_gate_summary": _public_int_dict(gate_summary),
        "pre_release_gate_missing_paths": _public_api_missing_gate_paths(report.get("pre_release_gate_missing_paths")),
        "pre_release_gate_parse_errors": _public_api_parse_errors(report.get("pre_release_gate_parse_errors")),
        "remediations": _public_api_remediations(
            latest_release_e2e=latest_release_e2e,
            gate_summary=gate_summary,
            release_evaluation=release_evaluation,
        ),
        "report_files": {
            "directory": "",
            "json_name": "",
            "json_path": "",
            "markdown_name": "",
            "markdown_path": "",
        },
        "audit": {
            "read_only": _public_bool(audit.get("read_only")),
            "repair_or_resume_triggered": _public_bool(audit.get("repair_or_resume_triggered")),
            "secrets_redacted": True,
            "expected_files": list(RELEASE_VERIFICATION_EXPECTED_FILES),
            "required_probes": list(RELEASE_VERIFICATION_REQUIRED_PROBES),
        },
    }


def _public_status_literal(value: Any, *, default: str = "unknown") -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if normalized == "ready":
        return "ready"
    if normalized in {"passed", "pass", "success", "succeeded", "ok"}:
        return "passed"
    if normalized in {"blocked", "failed", "failure", "error", "errored"}:
        return "blocked" if default == "attention" else "failed"
    if normalized in {"attention", "warning", "manual_required", "configured", "missing", "unknown"}:
        return normalized
    if normalized in {"running", "in_progress", "pending"}:
        return "running"
    return default


def _public_api_startup(
    startup: Dict[str, Any],
    summary: Dict[str, Any],
    runtime: Dict[str, Any],
    app_version: str,
    generated_at: str,
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    for index, check in enumerate(startup.get("checks") or [], start=1):
        if not isinstance(check, dict):
            continue
        check_status = _public_status_literal(check.get("status"), default="unknown")
        checks.append(
            {
                "id": f"startup_check_{index}",
                "title": "Startup check",
                "status": check_status,
                "detail": "Startup check passed." if check_status in {"ready", "passed"} else "Startup check needs local review.",
                "remediation": None,
                "metadata": {},
            }
        )
    status = _public_status_literal(startup.get("status") or summary.get("status"), default="attention")
    return {
        "schema_version": "1.0",
        "app_version": app_version,
        "generated_at": generated_at,
        "status": status,
        "summary": {
            "status": status,
            "passed": _public_int(summary.get("passed")),
            "warnings": _public_int(summary.get("warnings")),
            "failed": _public_int(summary.get("failed")),
            "check_count": _public_int(summary.get("check_count"), len(checks)),
        },
        "paths": {
            "app_home": "",
            "logs_dir": "",
            "run_dir": "",
            "tmp_dir": "",
            "evidence_dir": "",
            "socket_path": "",
            "database_path": "",
        },
        "runtime": {
            "pid": _public_int(runtime.get("pid")),
            "started_at": _public_float(runtime.get("started_at")) or 0.0,
            "uptime_sec": _public_float(runtime.get("uptime_sec")) or 0.0,
            "known_tasks": _public_int(runtime.get("known_tasks")),
            "persistence_initialized": _public_bool(runtime.get("persistence_initialized")),
        },
        "keys": {
            "has_any_key": False,
            "providers": {},
            "readiness_blockers": [],
        },
        "checks": checks[:16],
    }


def _public_api_release_evaluation(summary: Dict[str, Any]) -> Dict[str, Any]:
    readiness = _public_status_literal(summary.get("release_readiness"), default="unknown")
    interop_status = _public_status_literal(summary.get("agent_interop_e2e_status"), default="unknown")
    return {
        "release_readiness": readiness,
        "generated_at": _public_float(summary.get("generated_at")),
        "release_evidence_count": _public_int(summary.get("release_evidence_count")),
        "passed_evidence_count": _public_int(summary.get("passed_evidence_count")),
        "agent_interop_e2e_status": interop_status,
        "evaluated_task_count": _public_int(summary.get("evaluated_task_count")),
        "terminal_task_count": _public_int(summary.get("terminal_task_count")),
        "passed_task_count": _public_int(summary.get("passed_task_count")),
        "blocked_task_count": _public_int(summary.get("blocked_task_count")),
        "manual_task_count": _public_int(summary.get("manual_task_count")),
        "skipped_task_count": _public_int(summary.get("skipped_task_count")),
        "pass_rate": _public_float(summary.get("pass_rate")) or 0.0,
        "average_final_quality_score": (
            None
            if summary.get("average_final_quality_score") is None
            else _public_int(summary.get("average_final_quality_score"))
        ),
        "total_remediation_count": _public_int(summary.get("total_remediation_count")),
        "recommendation": None if readiness == "ready" else "Review the local release verification report before approval.",
        "top_risks": [],
        "recent_evaluations": [],
        "quality_trend": None,
        "agent_mix_summary": None,
        "probe_coverage": None,
        "readiness_checks": _public_api_readiness_checks(summary.get("readiness_checks")),
        "supplemental_evidence": _public_api_supplemental_evidence(summary.get("supplemental_evidence")),
        "gate_breakdown": _public_int_dict(summary.get("gate_breakdown")),
        "stack_coverage": _public_int_dict(summary.get("stack_coverage")),
        "agent_coverage": _public_int_dict(summary.get("agent_coverage")),
    }


def _public_api_readiness_checks(value: Any) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        status = _public_status_literal(item.get("status"), default="unknown")
        checks.append(
            {
                "id": f"readiness_check_{index}",
                "status": status,
                "label": "Readiness check",
                "message": "Readiness check passed." if status in {"ready", "passed"} else "Readiness check needs local review.",
                "severity": "medium",
            }
        )
    return checks[:16]


def _public_api_supplemental_evidence(value: Any) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        kind = "host_interop_e2e" if str(item.get("kind") or "") == "host_interop_e2e" else "supplemental_evidence"
        evidence.append(
            {
                "id": "agent_interop_e2e" if kind == "host_interop_e2e" else f"supplemental_evidence_{index}",
                "kind": kind,
                "status": _public_status_literal(item.get("status"), default="unknown"),
                "quality_gate": _public_status_literal(item.get("quality_gate"), default="unknown"),
                "passed_count": _public_int(item.get("passed_count")),
                "failed_count": _public_int(item.get("failed_count")),
                "host_target_count": _public_int(item.get("host_target_count")),
                "mcp_server_count": _public_int(item.get("mcp_server_count")),
                "protocol_readiness_score": _public_int(item.get("protocol_readiness_score")),
                "endpoint": "/api/autopilot/agent-interop-e2e" if kind == "host_interop_e2e" else "",
            }
        )
    return evidence[:8]


def _public_api_latest_release_e2e(latest: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(latest, dict):
        return None
    summary = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
    benchmark = latest.get("benchmark") if isinstance(latest.get("benchmark"), dict) else {}
    benchmark_summary = benchmark.get("summary") if isinstance(benchmark.get("summary"), dict) else {}
    benchmark_status = _public_status_literal(benchmark.get("status"), default="unknown")
    task_status = _public_status_literal(latest.get("task_status"), default="unknown")
    return {
        "task_id": "release-e2e-latest",
        "description": "Latest Release E2E scenario",
        "task_status": task_status,
        "project_dir": None,
        "updated_at": _public_float(latest.get("updated_at")),
        "benchmark": {
            "benchmark_id": "release-e2e-benchmark",
            "benchmark_version": None,
            "app_version": None,
            "status": benchmark_status,
            "summary": {
                "scenario_count": _public_int(benchmark_summary.get("scenario_count")),
                "passed_scenarios": _public_int(benchmark_summary.get("passed_scenarios")),
                "failed_scenarios": _public_int(benchmark_summary.get("failed_scenarios")),
                "min_quality_score": _public_int(benchmark_summary.get("min_quality_score")),
                "max_remediation_attempts": _public_int(benchmark_summary.get("max_remediation_attempts")),
            },
            "scenarios": [],
        },
        "summary": {
            "status": _public_status_literal(summary.get("status"), default="unknown"),
            "quality_score": None if summary.get("quality_score") is None else _public_int(summary.get("quality_score")),
            "remediation_attempts": _public_int(summary.get("remediation_attempts")),
            "failed_scenarios": _public_int(summary.get("failed_scenarios")),
        },
    }


def _public_api_pre_release_gates(gates: Any) -> List[Dict[str, Any]]:
    public_gates: List[Dict[str, Any]] = []
    for index, gate in enumerate(gates if isinstance(gates, list) else [], start=1):
        if not isinstance(gate, dict):
            continue
        status = _public_status_literal(gate.get("status"), default="unknown")
        source = str(gate.get("source") or "")
        source_value = source if source in {"local", "local_script", "github_actions"} else "unknown"
        public_gates.append(
            {
                "id": f"pre_release_gate_{index}",
                "label": "Pre-release gate",
                "status": status,
                "source": source_value,
                "command": "",
                "detail": "Pre-release gate passed." if status in {"ready", "passed"} else "Pre-release gate needs local review.",
                "paths": [],
                "required": _public_bool(gate.get("required")),
                "readiness_impact": "required",
                "evidence": _public_api_gate_evidence(gate, index),
            }
        )
    return public_gates


def _public_api_gate_evidence(gate: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    evidence = gate.get("evidence")
    if not isinstance(evidence, dict):
        return None
    status = _public_status_literal(evidence.get("status") or gate.get("status"), default="unknown")
    return {
        "schema_version": "1.0",
        "gate_id": f"pre_release_gate_{index}",
        "status": status,
        "source": "github_actions" if str(evidence.get("source") or gate.get("source") or "") == "github_actions" else "local",
        "summary": "Pre-release gate evidence passed." if status in {"ready", "passed"} else "Pre-release gate evidence needs local review.",
        "generated_at": None,
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "tier": None,
        "run_url": None,
        "workflow_run_url": None,
        "commit_sha": None,
        "runner": None,
        "orchestrator_command": None,
        "workspace_dirty": _public_bool(evidence.get("workspace_dirty")),
        "evidence_path": None,
    }


def _public_api_parse_errors(parse_errors: Any) -> List[Dict[str, str]]:
    errors = parse_errors if isinstance(parse_errors, list) else []
    return [
        {
            "evidence_path": "",
            "error_type": "ParseError",
            "message": "Could not parse pre-release gate evidence; see local report for details.",
        }
        for _item in errors[:8]
    ]


def _public_api_missing_gate_paths(value: Any) -> List[str]:
    reported = {str(item) for item in value} if isinstance(value, list) else set()
    return [path for path in PUBLIC_PRE_RELEASE_GATE_PATHS if path in reported]


def _public_api_remediations(
    *,
    latest_release_e2e: Optional[Dict[str, Any]],
    gate_summary: Dict[str, Any],
    release_evaluation: Dict[str, Any],
) -> List[str]:
    remediations: List[str] = []
    if latest_release_e2e is None:
        remediations.append("Run the fixed Release E2E scenario from the frontend and wait for passing evidence.")
    if _public_int(gate_summary.get("required_missing")) > 0:
        remediations.append("Restore missing pre-release verification gates before release approval.")
    if _public_int(gate_summary.get("required_failed")) > 0:
        remediations.append("Review failed pre-release verification gate evidence before release approval.")
    if _public_int(gate_summary.get("required_manual")) > 0:
        remediations.append("Run required manual pre-release gates and attach their evidence before release approval.")
    if _public_int(gate_summary.get("required_unverified")) > 0:
        remediations.append("Attach passing evidence for configured pre-release verification gates before release approval.")
    if _public_status_literal(release_evaluation.get("release_readiness"), default="unknown") not in {"ready", "passed"}:
        remediations.append("Collect passing release evaluation evidence before release approval.")
    return remediations


def _build_release_verification_report(
    *,
    write_report: bool = True,
    task_state: Optional[Any] = None,
    external_task_rows: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None,
    task_row_mapper: Optional[Callable[[Any], Dict[str, Any]]] = None,
    startup_diagnostics: Optional[Dict[str, Any]] = None,
    load_task_payload: Optional[Callable[[str], Any]] = None,
    serialize_task_payload: Callable[[Any], Dict[str, Any]] = _pydantic_dump,
    redact_sensitive: Callable[[Any], Any] = _redact_sensitive_evidence,
    app_version: Optional[str] = None,
    expected_files: Optional[Sequence[str]] = None,
    required_probes: Optional[Sequence[str]] = None,
    write_report_directory: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    agent_interop_e2e: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from .agent_interop_e2e import (
        augment_release_evaluation_with_agent_interop,
        load_agent_interop_e2e_latest,
    )
    from .task_review.release_evaluation import build_release_evaluation_summary

    from . import __version__

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    startup = startup_diagnostics or {
        "status": "attention",
        "summary": {
            "status": "attention",
            "passed": 0,
            "warnings": 1,
            "failed": 1,
        },
    }

    report_directory = write_report_directory or app_subdir("release-reports")
    rows = _collect_release_task_rows(
        100,
        task_state=task_state,
        external_task_rows=external_task_rows,
        task_row_mapper=task_row_mapper,
    )
    release_e2e_rows = _release_e2e_rows(rows, limit=3)
    latest_row = release_e2e_rows[0] if release_e2e_rows else None
    latest_release_e2e = None
    latest_task_payload = None
    if release_e2e_rows and load_task_payload:
        for release_e2e_row in release_e2e_rows:
            task_id = str(release_e2e_row.get("task_id") or "")
            if not task_id:
                continue
            try:
                raw_task_payload = load_task_payload(task_id)
                task_payload = serialize_task_payload(raw_task_payload)
            except Exception:
                continue
            rows = _upsert_release_evaluation_row(
                rows,
                _release_evaluation_row_from_task_payload(task_payload, release_e2e_row),
            )
            if latest_row and task_id == str(latest_row.get("task_id") or ""):
                latest_task_payload = task_payload

    if latest_row and latest_task_payload:
        latest_release_e2e = _build_latest_release_e2e_verification(
            latest_row,
            load_task_payload=lambda _task_id: latest_task_payload,
            serialize_task_payload=lambda value: dict(value) if isinstance(value, dict) else value,
            redact_sensitive=redact_sensitive,
            expected_files=expected_files or RELEASE_VERIFICATION_EXPECTED_FILES,
            required_probes=required_probes or RELEASE_VERIFICATION_REQUIRED_PROBES,
            app_version=app_version or __version__,
        )

    release_evaluation = build_release_evaluation_summary(rows)
    try:
        interop_evidence = agent_interop_e2e if agent_interop_e2e is not None else load_agent_interop_e2e_latest()
    except Exception:
        interop_evidence = {}
    release_evaluation = augment_release_evaluation_with_agent_interop(release_evaluation, interop_evidence)
    pre_release_gates = _build_pre_release_gates(repo_root=repo_root)
    pre_release_gate_evidence, pre_release_parse_errors = _load_pre_release_gate_evidence(report_directory)
    pre_release_gates = _apply_pre_release_gate_evidence(pre_release_gates, pre_release_gate_evidence)
    pre_release_summary = _pre_release_gate_summary(pre_release_gates)
    pre_release_missing_paths = _missing_required_gate_paths(pre_release_gates)

    status, remediations = _release_verification_status(
        str(startup.get("status") or "attention"),
        latest_release_e2e,
        pre_release_summary,
        str(release_evaluation.get("release_readiness") or "unknown"),
    )

    public_report: Dict[str, Any] = {
        "schema_version": "1.0",
        "app_version": app_version or __version__,
        "generated_at": generated_at,
        "status": status,
        "startup": _public_startup_report(
            startup,
            app_version=app_version or __version__,
            generated_at=generated_at,
        ),
        "release_evaluation": _public_release_evaluation(release_evaluation),
        "latest_release_e2e": _public_latest_release_e2e(latest_release_e2e),
        "pre_release_gates": _public_pre_release_gates(pre_release_gates),
        "pre_release_gate_summary": _public_int_dict(pre_release_summary),
        "pre_release_gate_missing_paths": _public_str_list(pre_release_missing_paths),
        "pre_release_gate_parse_errors": _public_parse_errors(pre_release_parse_errors),
        "remediations": _public_str_list(remediations),
        "report_files": {},
        "audit": _public_audit({
            "read_only": True,
            "repair_or_resume_triggered": False,
            "secrets_redacted": True,
            "expected_files": list(expected_files or RELEASE_VERIFICATION_EXPECTED_FILES),
            "required_probes": list(required_probes or RELEASE_VERIFICATION_REQUIRED_PROBES),
        }),
    }

    if write_report:
        _write_release_verification_report(public_report, report_directory=report_directory)
    return public_report

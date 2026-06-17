from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
import copy
import json
import re
import time

from .paths import app_subdir


RELEASE_E2E_DESCRIPTION_MARKER = "Release E2E scenario:"
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
    "static_web_smoke",
    "browser_e2e",
    "api_service",
    "cli_generic",
]


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


def _latest_release_e2e_row(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    release_rows = [
        dict(row)
        for row in rows
        if RELEASE_E2E_DESCRIPTION_MARKER.lower() in str(row.get("description") or "").lower()
    ]
    if not release_rows:
        return None
    return sorted(
        release_rows,
        key=lambda row: row.get("updated_at") or row.get("created_at") or 0,
        reverse=True,
    )[0]


def _release_verification_status(
    startup_status: str,
    latest_release_e2e: Optional[Dict[str, Any]],
) -> tuple[str, List[str]]:
    remediations: List[str] = []
    if startup_status == "blocked":
        remediations.append("Resolve failed startup diagnostics before release approval.")

    if latest_release_e2e is None:
        remediations.append("Run the fixed Release E2E scenario from the frontend and wait for passing evidence.")
    else:
        benchmark_status = str((latest_release_e2e.get("benchmark") or {}).get("status") or "unknown")
        if benchmark_status != "passed":
            remediations.append("Review the latest Release E2E benchmark failures and rerun remediation.")

    if startup_status == "blocked":
        return "blocked", remediations
    if latest_release_e2e is not None:
        benchmark_status = str((latest_release_e2e.get("benchmark") or {}).get("status") or "unknown")
        if benchmark_status != "passed":
            return "blocked", remediations
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
    latest = report.get("latest_release_e2e")
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
) -> Dict[str, Any]:
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

    rows = _collect_release_task_rows(
        100,
        task_state=task_state,
        external_task_rows=external_task_rows,
        task_row_mapper=task_row_mapper,
    )
    release_evaluation = build_release_evaluation_summary(rows)
    latest_row = _latest_release_e2e_row(rows)

    latest_release_e2e = None
    if latest_row and load_task_payload:
        latest_release_e2e = _build_latest_release_e2e_verification(
            latest_row,
            load_task_payload=load_task_payload,
            serialize_task_payload=serialize_task_payload,
            redact_sensitive=redact_sensitive,
            expected_files=expected_files or RELEASE_VERIFICATION_EXPECTED_FILES,
            required_probes=required_probes or RELEASE_VERIFICATION_REQUIRED_PROBES,
            app_version=app_version or __version__,
        )

    status, remediations = _release_verification_status(
        str(startup.get("status") or "attention"),
        latest_release_e2e,
    )

    report: Dict[str, Any] = {
        "schema_version": "1.0",
        "app_version": app_version or __version__,
        "generated_at": generated_at,
        "status": status,
        "startup": startup,
        "release_evaluation": copy.deepcopy(release_evaluation),
        "latest_release_e2e": latest_release_e2e,
        "remediations": remediations,
        "report_files": {},
        "audit": {
            "read_only": True,
            "repair_or_resume_triggered": False,
            "secrets_redacted": True,
            "expected_files": list(expected_files or RELEASE_VERIFICATION_EXPECTED_FILES),
            "required_probes": list(required_probes or RELEASE_VERIFICATION_REQUIRED_PROBES),
        },
    }

    if write_report:
        _write_release_verification_report(report, report_directory=write_report_directory)
    return report

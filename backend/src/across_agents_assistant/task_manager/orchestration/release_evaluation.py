from __future__ import annotations

from collections import Counter
from statistics import mean
import time
from typing import Any, Dict, Iterable, List, Optional


TERMINAL_STATUSES = {
    "completed",
    "completed_with_failures",
    "failed",
    "cancelled",
}

PASSING_GATES = {"passed"}
BLOCKING_GATES = {"failed", "inconsistent"}
ATTENTION_GATES = {"manual_required", "partial"}


def build_release_evaluation_summary(
    task_rows: Iterable[Dict[str, Any]],
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Summarize cached task quality reports into a release-candidate signal.

    This is intentionally read-only and probe-free. It consumes already stored
    delivery quality data so opening the task page cannot resume historical work
    or run expensive browser/build checks.
    """
    evaluated: List[Dict[str, Any]] = []
    terminal_task_count = 0
    stack_coverage: Counter[str] = Counter()
    agent_coverage: Counter[str] = Counter()

    for row in task_rows:
        status = str(row.get("status") or "created")
        if status in TERMINAL_STATUSES:
            terminal_task_count += 1

        quality = _extract_quality(row)
        if not quality:
            continue

        item = _build_evaluation_item(row, quality)
        evaluated.append(item)
        for stack in _task_stacks(row):
            stack_coverage[stack] += 1
        for agent_id in _task_agents(row):
            agent_coverage[agent_id] += 1

    evaluated.sort(
        key=lambda item: item.get("updated_at") or item.get("created_at") or 0,
        reverse=True,
    )

    evaluated_count = len(evaluated)
    passed_count = sum(1 for item in evaluated if item["quality_gate"] in PASSING_GATES)
    blocked_count = sum(1 for item in evaluated if item["is_blocked"])
    manual_count = sum(1 for item in evaluated if item["manual_required_count"] > 0)
    skipped_count = sum(1 for item in evaluated if item["skipped_required_count"] > 0)
    scores = [item["final_quality_score"] for item in evaluated if item["final_quality_score"] is not None]
    average_score = int(round(mean(scores))) if scores else None
    pass_rate = round(passed_count / evaluated_count, 4) if evaluated_count else 0.0
    total_remediation_count = sum(item["remediation_count"] for item in evaluated)
    gate_breakdown = Counter(item["quality_gate"] for item in evaluated)
    top_risks = _build_top_risks(
        evaluated,
        evaluated_count=evaluated_count,
        passed_count=passed_count,
        blocked_count=blocked_count,
        manual_count=manual_count,
        skipped_count=skipped_count,
        average_score=average_score,
    )
    readiness = _release_readiness(
        evaluated_count=evaluated_count,
        pass_rate=pass_rate,
        blocked_count=blocked_count,
        manual_count=manual_count,
        skipped_count=skipped_count,
        average_score=average_score,
    )

    return {
        "release_readiness": readiness,
        "generated_at": float(now if now is not None else time.time()),
        "evaluated_task_count": evaluated_count,
        "terminal_task_count": terminal_task_count,
        "passed_task_count": passed_count,
        "blocked_task_count": blocked_count,
        "manual_task_count": manual_count,
        "skipped_task_count": skipped_count,
        "pass_rate": pass_rate,
        "average_final_quality_score": average_score,
        "total_remediation_count": total_remediation_count,
        "gate_breakdown": dict(sorted(gate_breakdown.items())),
        "top_risks": top_risks,
        "recent_evaluations": evaluated[:10],
        "stack_coverage": dict(sorted(stack_coverage.items())),
        "agent_coverage": dict(sorted(agent_coverage.items())),
        "recommendation": _recommendation(readiness, top_risks),
    }


def _extract_quality(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    decision = row.get("last_owner_decision") or {}
    if not isinstance(decision, dict):
        return None
    delivery_quality = decision.get("delivery_quality")
    if not isinstance(delivery_quality, dict):
        return None
    quality_report = delivery_quality.get("quality_report")
    if not isinstance(quality_report, dict):
        quality_report = {}
    gate = (
        quality_report.get("quality_gate")
        or delivery_quality.get("delivery_quality")
        or delivery_quality.get("quality_gate")
    )
    if not gate:
        return None
    return {
        "delivery_quality": delivery_quality,
        "quality_report": quality_report,
        "quality_gate": str(gate),
    }


def _build_evaluation_item(row: Dict[str, Any], quality: Dict[str, Any]) -> Dict[str, Any]:
    quality_report = quality["quality_report"]
    gate = quality["quality_gate"]
    required_failed_count = _int_value(quality_report.get("required_failed_count"))
    manual_required_count = _int_value(quality_report.get("manual_required_count"))
    skipped_required_count = _int_value(
        quality_report.get("required_skipped_count", quality_report.get("skipped_required_count"))
    )
    remediation_count = _int_value(quality_report.get("remediation_count"))
    score = quality_report.get("final_quality_score")
    final_score = _optional_int(score)
    is_blocked = gate in BLOCKING_GATES or required_failed_count > 0

    return {
        "task_id": str(row.get("task_id") or ""),
        "description": str(row.get("description") or ""),
        "status": str(row.get("status") or "created"),
        "quality_gate": gate,
        "final_quality_score": final_score,
        "generated_quality_score": _optional_int(quality_report.get("generated_quality_score")),
        "required_failed_count": required_failed_count,
        "manual_required_count": manual_required_count,
        "skipped_required_count": skipped_required_count,
        "remediation_count": remediation_count,
        "is_blocked": is_blocked,
        "owner_agent": row.get("owner_agent"),
        "delivery_mode": row.get("delivery_mode") or "legacy",
        "task_types": list(row.get("task_types") or []),
        "score_breakdown": quality_report.get("score_breakdown") or {},
        "created_at": _optional_float(row.get("created_at")),
        "updated_at": _optional_float(row.get("updated_at")),
    }


def _task_stacks(row: Dict[str, Any]) -> List[str]:
    stacks: List[str] = []
    for value in row.get("task_types") or []:
        stack = str(value).strip().lower()
        if stack and stack not in stacks:
            stacks.append(stack)
    mode = str(row.get("delivery_mode") or "").strip().lower()
    if mode and mode != "legacy" and mode not in stacks:
        stacks.append(mode)
    return stacks or ["legacy"]


def _task_agents(row: Dict[str, Any]) -> List[str]:
    agents: List[str] = []
    owner = str(row.get("owner_agent") or "").strip()
    if owner and owner != "auto":
        agents.append(owner)
    for value in row.get("allowed_subtask_agents") or []:
        agent_id = str(value).strip()
        if agent_id and agent_id not in agents:
            agents.append(agent_id)
    return agents


def _build_top_risks(
    evaluated: List[Dict[str, Any]],
    *,
    evaluated_count: int,
    passed_count: int,
    blocked_count: int,
    manual_count: int,
    skipped_count: int,
    average_score: Optional[int],
) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []
    required_failures = sum(item["required_failed_count"] for item in evaluated)
    if required_failures:
        risks.append({
            "kind": "required_gate_failure",
            "severity": "high",
            "count": required_failures,
            "message": f"{required_failures} required quality gate failure(s) block release.",
        })
    if blocked_count and not required_failures:
        risks.append({
            "kind": "blocked_task",
            "severity": "high",
            "count": blocked_count,
            "message": f"{blocked_count} evaluated task(s) are blocked by delivery quality.",
        })
    manual_or_skipped = manual_count + skipped_count
    if manual_or_skipped:
        risks.append({
            "kind": "manual_or_skipped_gate",
            "severity": "medium",
            "count": manual_or_skipped,
            "message": f"{manual_or_skipped} task(s) still need manual or skipped gate resolution.",
        })
    if evaluated_count and passed_count < evaluated_count:
        risks.append({
            "kind": "pass_rate",
            "severity": "medium",
            "count": evaluated_count - passed_count,
            "message": "Not every quality-gated task has passed.",
        })
    if average_score is not None and average_score < 80:
        risks.append({
            "kind": "quality_score",
            "severity": "medium",
            "count": average_score,
            "message": f"Average final quality score is {average_score}, below the release target of 80.",
        })
    if evaluated_count and evaluated_count < 3:
        risks.append({
            "kind": "sample_size",
            "severity": "low",
            "count": evaluated_count,
            "message": "Fewer than three quality-gated tasks have been evaluated.",
        })
    return risks[:5]


def _release_readiness(
    *,
    evaluated_count: int,
    pass_rate: float,
    blocked_count: int,
    manual_count: int,
    skipped_count: int,
    average_score: Optional[int],
) -> str:
    if evaluated_count == 0:
        return "no_evidence"
    if blocked_count > 0 or pass_rate < 0.8:
        return "blocked"
    if (
        evaluated_count < 3
        or manual_count > 0
        or skipped_count > 0
        or average_score is None
        or average_score < 80
    ):
        return "attention"
    return "ready"


def _recommendation(readiness: str, risks: List[Dict[str, Any]]) -> str:
    if readiness == "ready":
        return "Release candidate quality is clean across recent evaluated tasks."
    if readiness == "no_evidence":
        return "Run at least three quality-gated E2E tasks before release."
    if risks:
        return risks[0]["message"]
    return "Review recent evaluated tasks before release."


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _int_value(value: Any) -> int:
    parsed = _optional_int(value)
    return parsed if parsed is not None else 0


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

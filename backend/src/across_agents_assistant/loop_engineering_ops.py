from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .autopilot_trigger_manager import build_trigger_registry_summary


OPS_DASHBOARD_SCHEMA_VERSION = "across-aaa-loop-engineering-ops-dashboard/1.0"


def build_loop_engineering_ops_dashboard(
    *,
    telemetry: Mapping[str, Any] | None = None,
    runs: Mapping[str, Any] | None = None,
    trigger_registry: Mapping[str, Any] | None = None,
    trigger_scheduler: Mapping[str, Any] | None = None,
    capability_pack: Mapping[str, Any] | None = None,
    registry_health: Mapping[str, Any] | None = None,
    self_iteration_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded operations dashboard payload for Loop Engineering."""

    telemetry = dict(telemetry or {})
    runs = dict(runs or {})
    trigger_scheduler = dict(trigger_scheduler or {})
    capability_pack = dict(capability_pack or {})
    registry_health = dict(registry_health or {})
    self_iteration_plan = dict(self_iteration_plan or {})
    platform_self_repair = _dict(self_iteration_plan.get("platform_self_repair"))
    trigger_summary = build_trigger_registry_summary(dict(trigger_registry or {}))
    recent_runs = _list(runs.get("runs"))
    latest_runs = _latest_runs_by_spec(recent_runs)
    run_count = int(telemetry.get("run_count") or _nested(telemetry, "runs", "total") or 0)
    completed = int(_nested(telemetry, "by_status", "completed") or _nested(telemetry, "runs", "completed") or 0)
    historical_failed = int(_nested(telemetry, "by_status", "failed") or _nested(telemetry, "runs", "failed") or 0)
    latest_failed = _count_status(latest_runs.values(), "failed") if latest_runs else historical_failed
    resolved_failed = _count_resolved_failed_runs(latest_runs.values(), self_iteration_plan=self_iteration_plan)
    current_failed = max(latest_failed - resolved_failed, 0)
    failed = current_failed
    historical_gate_failures = _mapping_size(telemetry.get("gate_failures"))
    gate_failures = historical_gate_failures if failed else 0
    adapter_failures = _mapping_size(telemetry.get("adapter_failures"))
    capability_ready = int(capability_pack.get("ready_count") or 0)
    registry_ok = registry_health.get("status") in {None, "passed"}
    status = "passed"
    if not registry_ok or failed > 0 or gate_failures > 0:
        status = "attention"
    if capability_ready < 25:
        status = "failed"
    return {
        "schema_version": OPS_DASHBOARD_SCHEMA_VERSION,
        "status": status,
        "summary": {
            "run_count": run_count,
            "completed": completed,
            "failed": failed,
            "historical_failed": historical_failed,
            "latest_failed": latest_failed,
            "resolved_failed": resolved_failed,
            "unresolved_failed": current_failed,
            "current_failed": current_failed,
            "completion_rate": round(completed / run_count, 4) if run_count else None,
            "capability_ready_count": capability_ready,
            "trigger_count": trigger_summary["total"],
            "active_trigger_count": trigger_summary["enabled"],
            "trigger_scheduler_running": bool(trigger_scheduler.get("running")),
            "registry_health_status": registry_health.get("status") or "unknown",
            "self_iteration_status": self_iteration_plan.get("status") or "unknown",
            "platform_self_repair_queued_count": int(platform_self_repair.get("queued_count") or 0),
        },
        "signals": {
            "adapter_failure_count": adapter_failures,
            "gate_failure_count": gate_failures,
            "historical_gate_failure_count": historical_gate_failures,
            "latest_failed_count": latest_failed,
            "resolved_failed_count": resolved_failed,
            "unresolved_failed_count": current_failed,
            "approval_requests": _mapping_size(telemetry.get("approval_requests")),
            "unresolved_risks": _mapping_size(telemetry.get("unresolved_risks")),
            "promotion_ready_count": _mapping_size(telemetry.get("promotion_ready_by_spec")),
        },
        "triggers": trigger_summary,
        "self_iteration_plan": {
            "plan_id": self_iteration_plan.get("plan_id"),
            "status": self_iteration_plan.get("status") or "unknown",
            "ready": bool(self_iteration_plan.get("ready")),
            "default_trigger_id": self_iteration_plan.get("default_trigger_id"),
            "spec": self_iteration_plan.get("spec"),
            "platform_self_repair": platform_self_repair,
        },
        "capability_pack": {
            "ready_count": capability_ready,
            "skill_candidate_count": capability_pack.get("skill_candidate_count"),
            "validation_only_count": capability_pack.get("validation_only_count"),
        },
        "trigger_scheduler": trigger_scheduler,
        "registry_health": registry_health,
        "next_actions": _next_actions(
            failed=failed,
            gate_failures=gate_failures,
            registry_ok=registry_ok,
            capability_ready=capability_ready,
            trigger_summary=trigger_summary,
            trigger_scheduler=trigger_scheduler,
            self_iteration_plan=self_iteration_plan,
        ),
    }


def _next_actions(
    *,
    failed: int,
    gate_failures: int,
    registry_ok: bool,
    capability_ready: int,
    trigger_summary: Mapping[str, Any],
    trigger_scheduler: Mapping[str, Any],
    self_iteration_plan: Mapping[str, Any],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if capability_ready < 25:
        actions.append({"priority": "high", "action": "restore_capability_pack", "reason": "ready capability count is below the release floor"})
    if not registry_ok:
        actions.append({"priority": "high", "action": "repair_unified_registry", "reason": "unified capability registry health is not passing"})
    if failed or gate_failures:
        actions.append({"priority": "medium", "action": "triage_failed_runs", "reason": "run or gate failures need evidence review"})
    if not trigger_summary.get("total"):
        actions.append({"priority": "low", "action": "register_trigger", "reason": "no production trigger is registered"})
    if self_iteration_plan.get("status") != "active":
        actions.append({"priority": "medium", "action": "ensure_self_iteration_plan", "reason": "continuous AAA self-iteration is not active"})
    if trigger_summary.get("total") and trigger_scheduler.get("running") is not True:
        actions.append({"priority": "medium", "action": "start_trigger_scheduler", "reason": "registered triggers need the local scheduler lifecycle running for unattended operation"})
    if not actions:
        actions.append({"priority": "low", "action": "continue_scheduled_e2e", "reason": "ops signals are healthy"})
    return actions


def _mapping_size(value: Any) -> int:
    return len(value) if isinstance(value, Mapping) else 0


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _latest_runs_by_spec(runs: list[Any]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    ordered_runs = sorted(runs, key=_run_sort_key, reverse=True) if any(_run_sort_key(run) for run in runs) else runs
    for run in ordered_runs:
        if not isinstance(run, Mapping):
            continue
        spec_id = str(run.get("spec_id") or run.get("spec") or run.get("run_id") or "").strip()
        if not spec_id or spec_id in latest:
            continue
        latest[spec_id] = run
    return latest


def _count_status(runs: Any, status: str) -> int:
    return sum(1 for run in runs if isinstance(run, Mapping) and str(run.get("status") or run.get("state") or "") == status)


def _count_resolved_failed_runs(runs: Any, *, self_iteration_plan: Mapping[str, Any]) -> int:
    return sum(1 for run in runs if _failed_run_is_resolved(run, self_iteration_plan=self_iteration_plan))


def _failed_run_is_resolved(run: Any, *, self_iteration_plan: Mapping[str, Any]) -> bool:
    if not isinstance(run, Mapping):
        return False
    status = str(run.get("status") or run.get("state") or "").lower()
    if status != "failed":
        return False
    spec_id = str(run.get("spec_id") or run.get("spec") or "").strip()
    platform_self_repair = _dict(self_iteration_plan.get("platform_self_repair"))
    repair_spec = str(platform_self_repair.get("spec") or "").strip()
    if spec_id and spec_id == repair_spec:
        latest_trigger = _dict(platform_self_repair.get("latest_trigger"))
        latest_trigger_status = str(latest_trigger.get("status") or "").lower()
        queued_count = int(platform_self_repair.get("queued_count") or 0)
        if queued_count == 0 and latest_trigger_status in {"completed", "obsolete", "cancelled", "skipped"}:
            return True
    return False


def _run_sort_key(run: Any) -> str:
    if not isinstance(run, Mapping):
        return ""
    return str(run.get("completed_at") or run.get("updated_at") or run.get("started_at") or run.get("created_at") or "")


def _nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current

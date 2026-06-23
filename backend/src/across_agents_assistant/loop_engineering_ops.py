from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .autopilot_trigger_manager import build_trigger_registry_summary


OPS_DASHBOARD_SCHEMA_VERSION = "across-aaa-loop-engineering-ops-dashboard/1.0"


def build_loop_engineering_ops_dashboard(
    *,
    telemetry: Mapping[str, Any] | None = None,
    trigger_registry: Mapping[str, Any] | None = None,
    trigger_scheduler: Mapping[str, Any] | None = None,
    capability_pack: Mapping[str, Any] | None = None,
    registry_health: Mapping[str, Any] | None = None,
    self_iteration_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded operations dashboard payload for Loop Engineering."""

    telemetry = dict(telemetry or {})
    trigger_scheduler = dict(trigger_scheduler or {})
    capability_pack = dict(capability_pack or {})
    registry_health = dict(registry_health or {})
    self_iteration_plan = dict(self_iteration_plan or {})
    trigger_summary = build_trigger_registry_summary(dict(trigger_registry or {}))
    run_count = int(telemetry.get("run_count") or _nested(telemetry, "runs", "total") or 0)
    completed = int(_nested(telemetry, "by_status", "completed") or _nested(telemetry, "runs", "completed") or 0)
    failed = int(_nested(telemetry, "by_status", "failed") or _nested(telemetry, "runs", "failed") or 0)
    gate_failures = _mapping_size(telemetry.get("gate_failures"))
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
            "completion_rate": round(completed / run_count, 4) if run_count else None,
            "capability_ready_count": capability_ready,
            "trigger_count": trigger_summary["total"],
            "active_trigger_count": trigger_summary["enabled"],
            "trigger_scheduler_running": bool(trigger_scheduler.get("running")),
            "registry_health_status": registry_health.get("status") or "unknown",
            "self_iteration_status": self_iteration_plan.get("status") or "unknown",
        },
        "signals": {
            "adapter_failure_count": adapter_failures,
            "gate_failure_count": gate_failures,
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


def _nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current

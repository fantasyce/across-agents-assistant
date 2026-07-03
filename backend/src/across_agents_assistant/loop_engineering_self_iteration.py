from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from .autopilot_trigger_manager import AutopilotTriggerRegistry, build_trigger_registry_summary


SELF_ITERATION_PLAN_SCHEMA_VERSION = "across-aaa-self-iteration-plan/1.0"
DEFAULT_SELF_ITERATION_SPEC = "aaa-autonomous-self-iteration"
DEFAULT_SELF_ITERATION_TRIGGER_ID = "aaa-continuous-self-iteration-daily"
DEFAULT_SELF_ITERATION_INTERVAL_SECONDS = 86_400
DEFAULT_SELF_ITERATION_DAILY_TIME = "10:00"
DEFAULT_SELF_ITERATION_TIMEZONE = "Asia/Shanghai"
DEFAULT_PLATFORM_SELF_REPAIR_SPEC = "aaa-platform-self-repair"


def build_self_iteration_plan(
    *,
    trigger_registry: Mapping[str, Any] | None = None,
    trigger_queue: Mapping[str, Any] | None = None,
    capability_pack: Mapping[str, Any] | None = None,
    source_mirrors: Mapping[str, Any] | None = None,
    spec: str = DEFAULT_SELF_ITERATION_SPEC,
    trigger_id: str = DEFAULT_SELF_ITERATION_TRIGGER_ID,
) -> dict[str, Any]:
    """Build the host-visible plan for continuous AAA self-iteration."""

    trigger_registry = dict(trigger_registry or {})
    trigger_queue = dict(trigger_queue or {})
    capability_pack = dict(capability_pack or {})
    source_mirrors = dict(source_mirrors or {})
    trigger = _find_trigger(trigger_registry, trigger_id)
    active = bool(trigger and trigger.get("enabled") is not False and trigger.get("paused") is not True)
    readiness = [
        _check("trigger_registered", trigger is not None, "Default self-iteration trigger is registered."),
        _check("trigger_active", active, "Default self-iteration trigger is enabled and not paused."),
        _check(
            "capability_pack_ready",
            int(capability_pack.get("ready_count") or 0) >= 40,
            "Loop Engineering capability pack exposes the continuous-iteration capabilities.",
            {"ready_count": capability_pack.get("ready_count")},
        ),
    ]
    if source_mirrors:
        readiness.append(
            _check(
                "source_mirrors_fresh",
                source_mirrors.get("status") == "passed",
                "Source mirrors are refreshed from the current A baseline before B candidate workspaces are created.",
                {
                    "root": source_mirrors.get("root"),
                    "missing_repos": source_mirrors.get("missing_repos"),
                    "dirty_repos": source_mirrors.get("dirty_repos"),
                    "unaligned_repos": source_mirrors.get("unaligned_repos"),
                    "drifted_repos": source_mirrors.get("drifted_repos"),
                    "manifest_created_at": source_mirrors.get("manifest_created_at"),
                },
            )
        )
    return {
        "schema_version": SELF_ITERATION_PLAN_SCHEMA_VERSION,
        "plan_id": "aaa-continuous-self-iteration",
        "status": "active" if active else "not_registered" if trigger is None else "paused",
        "continuous_iteration": True,
        "spec": spec,
        "default_trigger_id": trigger_id,
        "default_interval_seconds": DEFAULT_SELF_ITERATION_INTERVAL_SECONDS,
        "default_trigger": _default_trigger_config(spec=spec, trigger_id=trigger_id),
        "trigger": trigger,
        "trigger_summary": build_trigger_registry_summary(trigger_registry),
        "promotion_review": {
            "human_approval_required": True,
            "endpoint_template": "/api/autopilot/runs/{run_id}/promotion-review",
            "merge_release_signing_blocked": True,
        },
        "platform_self_repair": _platform_self_repair_status(trigger_queue),
        "source_mirrors": source_mirrors,
        "runtime_controls": {
            "scheduler_dispatch_mode": "enqueue_and_run_one_due_trigger_per_tick",
            "ensure_endpoint": "/api/autopilot/self-iteration-plan/ensure",
            "tick_endpoint": "/api/autopilot/trigger-configs/tick",
            "scheduler_status_endpoint": "/api/autopilot/trigger-scheduler",
            "scheduler_start_endpoint": "/api/autopilot/trigger-scheduler/start",
            "scheduler_stop_endpoint": "/api/autopilot/trigger-scheduler/stop",
            "run_queued_trigger_endpoint": "/api/autopilot/triggers/run",
            "ops_dashboard_endpoint": "/api/autopilot/ops-dashboard",
        },
        "readiness": readiness,
        "ready": all(item["status"] == "passed" for item in readiness),
        "today_start_policy": "ensure the default trigger, start the scheduler with queued-trigger dispatch enabled, then use promotion review for human approval",
        "updated_at": _now(),
    }


def ensure_self_iteration_plan(
    registry: AutopilotTriggerRegistry,
    *,
    spec: str = DEFAULT_SELF_ITERATION_SPEC,
    interval_seconds: int = DEFAULT_SELF_ITERATION_INTERVAL_SECONDS,
    daily_time: str = DEFAULT_SELF_ITERATION_DAILY_TIME,
    timezone: str = DEFAULT_SELF_ITERATION_TIMEZONE,
    enabled: bool = True,
    actor: str = "aaa-self-iteration",
    source: str = "aaa-self-iteration-plan",
    trigger_id: str = DEFAULT_SELF_ITERATION_TRIGGER_ID,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Ensure the default continuous self-iteration trigger exists."""

    interval = max(60, int(interval_seconds or DEFAULT_SELF_ITERATION_INTERVAL_SECONDS))
    return registry.ensure(
        spec=spec or DEFAULT_SELF_ITERATION_SPEC,
        trigger_type="cron",
        payload={
            "scenario": "aaa_continuous_self_iteration",
            "topic": "research current LLM and agent architecture signals, compare them to AAA, and produce one bounded product improvement",
            **dict(payload or {}),
        },
        schedule={
            "interval_seconds": interval,
            "daily_time": daily_time or DEFAULT_SELF_ITERATION_DAILY_TIME,
            "timezone": timezone or DEFAULT_SELF_ITERATION_TIMEZONE,
        },
        enabled=enabled,
        actor=actor or "aaa-self-iteration",
        source=source or "aaa-self-iteration-plan",
        trigger_id=trigger_id or DEFAULT_SELF_ITERATION_TRIGGER_ID,
    )


def _default_trigger_config(*, spec: str, trigger_id: str) -> dict[str, Any]:
    return {
        "trigger_id": trigger_id,
        "spec": spec,
        "type": "cron",
        "enabled": True,
        "schedule": {
            "interval_seconds": DEFAULT_SELF_ITERATION_INTERVAL_SECONDS,
            "daily_time": DEFAULT_SELF_ITERATION_DAILY_TIME,
            "timezone": DEFAULT_SELF_ITERATION_TIMEZONE,
        },
        "actor": "aaa-self-iteration",
        "source": "aaa-self-iteration-plan",
    }


def _find_trigger(trigger_registry: Mapping[str, Any], trigger_id: str) -> dict[str, Any] | None:
    for item in trigger_registry.get("triggers", []) or []:
        if isinstance(item, Mapping) and item.get("trigger_id") == trigger_id:
            return dict(item)
    return None


def _platform_self_repair_status(trigger_queue: Mapping[str, Any]) -> dict[str, Any]:
    items = [
        dict(item)
        for item in trigger_queue.get("items", []) or []
        if isinstance(item, Mapping) and item.get("spec_id") == DEFAULT_PLATFORM_SELF_REPAIR_SPEC
    ]
    pending = [item for item in items if item.get("status") in {"pending", "claimed", "running"}]
    latest = items[0] if items else None
    return {
        "schema_version": "across-aaa-platform-self-repair-plan/1.0",
        "enabled": True,
        "spec": DEFAULT_PLATFORM_SELF_REPAIR_SPEC,
        "triggered_by": "failed loop-engineering runs classified as validation/runtime/packaging/policy/supervisor platform gaps",
        "promotion_review_required": True,
        "merge_release_signing_blocked": True,
        "queued_count": len(pending),
        "latest_trigger": {
            key: latest.get(key)
            for key in ("trigger_id", "status", "run_id", "completed_at")
            if latest and latest.get(key) is not None
        } if latest else None,
    }


def _check(id_: str, passed: bool, label: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": id_,
        "label": label,
        "status": "passed" if passed else "failed",
    }
    if details:
        item["details"] = dict(details)
    return item


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
